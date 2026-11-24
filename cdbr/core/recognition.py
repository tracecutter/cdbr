"""Photograph normalization, grid extraction, and conservative cell OCR."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
import subprocess
from collections import Counter
import time

import cv2
import numpy as np

from cdbr.core.photo import detect_photo_format
from cdbr.core.puzzle import BLOCK, UNKNOWN, CellEvidence, CellUncertainty, ClueEvidence, PuzzleObservation


GRID_SIZE = 15
SUPPORTED_GRID_SIZES = (13, 15)
WARP_SIZE = 1500
MIN_OCR_CONFIDENCE = 80.0
MIN_TEMPLATE_MARGIN = 0.15
MIN_WHOLE_NUMBER_MARGIN = 0.20
LOCAL_BACKGROUND_KERNEL = 31
# Across 520 human-reviewed reference cells, obvious blanks contained at most
# 387 foreground pixels while the faintest real clue contained 428.  Keep the
# shelf slightly inside that measured gap so dirt can remain an automatic blank
# without allowing a missed letter to pass silently.
MIN_CLUE_REVIEW_INK_PIXELS = 400


@dataclass(frozen=True, kw_only=True)
class CellReading:
    row: int
    column: int
    text: str
    confidence: float
    trusted: bool = False


@dataclass(kw_only=True)
class RecognitionTrace:
    stage_seconds: dict[str, float] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def record(self, stage: str, started: float) -> None:
        self.stage_seconds[stage] = self.stage_seconds.get(stage, 0.0) + time.perf_counter() - started


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, errors="replace")
    except FileNotFoundError:
        raise ValueError(f"Required image tool is not installed: {command[0]}") from None
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or "unknown error"
        raise ValueError(f"{command[0]} failed: {detail}") from None


def normalize_photo(source: Path, destination: Path, *, maximum_size: int | None = 1600) -> None:
    """Decode a photograph into an orientation-corrected working PNG."""

    command = ["magick", str(source), "-auto-orient"]
    if maximum_size is not None:
        command.extend(["-resize", f"{maximum_size}x{maximum_size}>"])
    command.append(str(destination))
    _run(command)


def _ordered_corners(points: np.ndarray) -> np.ndarray:
    points = points.astype(np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).ravel()
    return np.array(
        [
            points[np.argmin(sums)],
            points[np.argmin(differences)],
            points[np.argmax(sums)],
            points[np.argmax(differences)],
        ],
        dtype=np.float32,
    )


def find_grid_corners(image: np.ndarray) -> np.ndarray:
    """Locate and order the four outer puzzle-grid corners."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        51,
        9,
    )
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = gray.shape[0] * gray.shape[1]
    candidates: list[tuple[float, np.ndarray]] = []

    for contour in contours:
        area = cv2.contourArea(contour)
        area_fraction = area / image_area
        if not 0.12 < area_fraction < 0.65:
            continue
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        points = polygon.reshape(4, 2)
        width, height = cv2.minAreaRect(points)[1]
        if min(width, height) <= 0 or max(width, height) / min(width, height) >= 1.3:
            continue
        candidates.append((area_fraction, points))

    if not candidates:
        raise ValueError("Could not locate a square puzzle grid in the photograph")

    return _ordered_corners(max(candidates, key=lambda candidate: candidate[0])[1])


def extract_grid(image: np.ndarray) -> np.ndarray:
    """Locate the near-square puzzle grid and rectify its perspective."""

    corners = find_grid_corners(image)
    destination = np.array(
        [[0, 0], [WARP_SIZE - 1, 0], [WARP_SIZE - 1, WARP_SIZE - 1], [0, WARP_SIZE - 1]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(corners, destination)
    return cv2.warpPerspective(image, transform, (WARP_SIZE, WARP_SIZE))


def _grid_line_positions(binary: np.ndarray, *, vertical: bool, grid_size: int = GRID_SIZE) -> list[int] | None:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40) if vertical else (40, 1))
    lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    scores = lines.sum(axis=0 if vertical else 1)
    positions: list[int] = []
    spacing = (WARP_SIZE - 1) / grid_size
    tolerance = round(spacing * 0.25)
    for index in range(grid_size + 1):
        expected = round(index * spacing)
        low = max(0, expected - tolerance)
        high = min(WARP_SIZE, expected + tolerance + 1)
        positions.append(low + int(np.argmax(scores[low:high])))
    gaps = np.diff(positions)
    if np.any(gaps < 0.75 * spacing) or np.any(gaps > 1.25 * spacing) or float(np.std(gaps)) >= 0.16 * spacing:
        return None
    return positions


def detect_grid_size(grid: np.ndarray) -> int:
    """Infer a supported square-grid size from its internal rule lines."""

    gray = cv2.cvtColor(grid, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    candidates: list[tuple[float, int]] = []
    for grid_size in SUPPORTED_GRID_SIZES:
        x_positions = _grid_line_positions(binary, vertical=True, grid_size=grid_size)
        y_positions = _grid_line_positions(binary, vertical=False, grid_size=grid_size)
        if x_positions is None or y_positions is None:
            continue
        vertical_lines = cv2.morphologyEx(
            binary,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40)),
        ).sum(axis=0)
        horizontal_lines = cv2.morphologyEx(
            binary,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1)),
        ).sum(axis=1)
        score = float(np.mean(vertical_lines[x_positions]) + np.mean(horizontal_lines[y_positions]))
        candidates.append((score, grid_size))
    if not candidates:
        raise ValueError("Could not determine whether the puzzle grid is 13×13 or 15×15")
    return max(candidates)[1]


def normalize_grid_lattice(grid: np.ndarray, grid_size: int = GRID_SIZE) -> np.ndarray:
    """Map measured internal grid lines onto an exact square lattice."""

    gray = cv2.cvtColor(grid, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    x_positions = _grid_line_positions(binary, vertical=True, grid_size=grid_size)
    y_positions = _grid_line_positions(binary, vertical=False, grid_size=grid_size)
    target = np.linspace(0, WARP_SIZE - 1, grid_size + 1)
    coordinates = np.arange(WARP_SIZE, dtype=np.float32)
    source_x = (
        np.interp(coordinates, target, x_positions).astype(np.float32) if x_positions is not None else coordinates
    )
    source_y = (
        np.interp(coordinates, target, y_positions).astype(np.float32) if y_positions is not None else coordinates
    )
    map_x, map_y = np.meshgrid(source_x, source_y)
    return cv2.remap(
        grid,
        map_x,
        map_y,
        cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _cell_images(grid: np.ndarray, grid_size: int = GRID_SIZE) -> list[tuple[int, int, np.ndarray]]:
    y_edges = np.linspace(0, grid.shape[0], grid_size + 1).round().astype(int)
    x_edges = np.linspace(0, grid.shape[1], grid_size + 1).round().astype(int)
    return [
        (
            row,
            column,
            grid[
                y_edges[row] : y_edges[row + 1],
                x_edges[column] : x_edges[column + 1],
            ],
        )
        for row in range(grid_size)
        for column in range(grid_size)
    ]


def _block_mask(cells: list[tuple[int, int, np.ndarray]], grid_size: int = GRID_SIZE) -> list[bool]:
    medians = np.array(
        [np.median(cell[15 : cell.shape[0] - 8, 15 : cell.shape[1] - 8]) for _, _, cell in cells],
        dtype=np.float32,
    ).reshape(grid_size, grid_size)
    local_paper = cv2.dilate(medians, np.ones((3, 3), dtype=np.uint8))
    relative = np.clip(255.0 * medians / np.maximum(local_paper, 1.0), 0, 255).astype(np.uint8)
    threshold, _ = cv2.threshold(relative, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return [bool(value <= threshold) for value in relative.ravel()]


def _foreground_binary(gray: np.ndarray) -> np.ndarray:
    """Extract dark ink while suppressing smooth illumination changes."""

    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (LOCAL_BACKGROUND_KERNEL, LOCAL_BACKGROUND_KERNEL),
    )
    ink = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    return cv2.threshold(ink, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]


def _clean_number(cell: np.ndarray, *, suppress_illumination: bool = False) -> np.ndarray:
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    region = gray[5:70, 5:70]
    binary = (
        _foreground_binary(region)
        if suppress_illumination
        else cv2.threshold(region, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    )
    count, labels, statistics, _ = cv2.connectedComponentsWithStats(binary)
    cleaned = np.full_like(binary, 255)
    for index in range(1, count):
        x, y, width, height, area = statistics[index]
        # Perspective normalization and thresholding often join the two digits
        # of values such as 20 and 26.  Preserve that complete number for the
        # whole-number and Tesseract fallbacks; the height limit still rejects
        # the surrounding grid lines.
        if 5 <= width <= 48 and 15 <= height <= 42 and 50 <= area <= 800:
            cleaned[labels == index] = 0
    cleaned = cv2.copyMakeBorder(cleaned, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return cv2.resize(cleaned, None, fx=5, fy=5, interpolation=cv2.INTER_NEAREST)


def _read_cell(item: tuple[int, int, np.ndarray], work_dir: Path) -> CellReading:
    row, column, cell = item
    image_path = work_dir / f"cell-{row + 1}-{column + 1}.png"
    cv2.imwrite(str(image_path), _clean_number(cell))
    return _ocr_image(image_path, row=row, column=column, page_segmentation_mode=7)


def _ocr_image(image_path: Path, *, row: int, column: int, page_segmentation_mode: int) -> CellReading:
    result = _run(
        [
            "tesseract",
            str(image_path),
            "stdout",
            "--psm",
            str(page_segmentation_mode),
            "-l",
            "eng",
            "-c",
            "tessedit_char_whitelist=0123456789",
            "tsv",
        ]
    )
    readings = []
    for line in result.stdout.splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) == 12 and fields[0] == "5" and fields[11].strip():
            readings.append((fields[11].strip(), float(fields[10])))
    if not readings:
        return CellReading(row=row, column=column, text="", confidence=0.0)
    text, confidence = max(readings, key=lambda reading: reading[1])
    return CellReading(row=row, column=column, text=text, confidence=confidence)


def _retry_cell(reading: CellReading, work_dir: Path, template_value: int | None) -> CellReading:
    """Retry an uncertain glyph and require agreement across OCR layouts."""

    image_path = work_dir / f"cell-{reading.row + 1}-{reading.column + 1}.png"
    attempts = [reading]
    attempts.extend(
        _ocr_image(
            image_path,
            row=reading.row,
            column=reading.column,
            page_segmentation_mode=mode,
        )
        for mode in (6, 8, 10, 13)
    )
    valid = [attempt for attempt in attempts if attempt.text.isdigit() and 1 <= int(attempt.text) <= 26]
    if not valid:
        return max(attempts, key=lambda attempt: attempt.confidence)
    winner, votes = Counter(attempt.text for attempt in valid).most_common(1)[0]
    agreeing = [attempt for attempt in valid if attempt.text == winner]
    if votes >= 3 and template_value is not None and int(winner) == template_value:
        return CellReading(
            row=reading.row,
            column=reading.column,
            text=winner,
            confidence=max(MIN_OCR_CONFIDENCE, sum(item.confidence for item in agreeing) / votes),
        )
    return max(attempts, key=lambda attempt: attempt.confidence)


def find_reference_corners(image: np.ndarray) -> np.ndarray:
    """Return the ordered corners of the two-row 1–26 reference strip."""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 9)
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = gray.shape[0] * gray.shape[1]
    candidates: list[tuple[float, np.ndarray]] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        area_fraction = area / image_area
        if not 0.01 < area_fraction < 0.15:
            continue
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        points = polygon.reshape(4, 2)
        width, height = cv2.minAreaRect(points)[1]
        if min(width, height) <= 0:
            continue
        aspect = max(width, height) / min(width, height)
        if 4.5 < aspect < 8.0:
            candidates.append((area_fraction, points))
    if not candidates:
        raise ValueError("Could not locate the numbered reference grid")
    return _ordered_corners(max(candidates, key=lambda candidate: candidate[0])[1])


def extract_reference_grid(image: np.ndarray) -> np.ndarray:
    """Locate and rectify the two-row 1–26 reference strip."""

    corners = find_reference_corners(image)
    destination = np.array([[0, 0], [1299, 0], [1299, 199], [0, 199]], dtype=np.float32)
    transform = cv2.getPerspectiveTransform(corners, destination)
    return cv2.warpPerspective(image, transform, (1300, 200))


def _number_feature(cell: np.ndarray, *, suppress_illumination: bool = False) -> np.ndarray:
    cleaned = _clean_number(cell, suppress_illumination=suppress_illumination)
    y_coordinates, x_coordinates = np.where(cleaned < 128)
    feature = np.full((80, 120), 255, dtype=np.uint8)
    if not len(x_coordinates):
        return feature
    x_values = [int(value) for value in x_coordinates]
    y_values = [int(value) for value in y_coordinates]
    crop = cleaned[
        min(y_values) : max(y_values) + 1,
        min(x_values) : max(x_values) + 1,
    ]
    scale = min(100 / crop.shape[1], 60 / crop.shape[0])
    resized = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    y = (feature.shape[0] - resized.shape[0]) // 2
    x = (feature.shape[1] - resized.shape[1]) // 2
    feature[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return feature


def _reference_templates(reference_grid: np.ndarray) -> dict[int, np.ndarray]:
    return {
        value: _number_feature(
            reference_grid[
                (0 if value <= 13 else 1) * 100 : (1 if value <= 13 else 2) * 100,
                ((value - 1) % 13) * 100 : ((value - 1) % 13 + 1) * 100,
            ]
        )
        for value in range(1, 27)
    }


def _template_value(cell: np.ndarray, templates: dict[int, np.ndarray]) -> int:
    feature = _number_feature(cell).astype(np.float32)
    return min(
        templates,
        key=lambda value: float(np.mean((feature - templates[value].astype(np.float32)) ** 2)),
    )


def _template_scores(feature: np.ndarray, templates: dict[int, list[np.ndarray]]) -> list[tuple[float, int]]:
    return sorted(
        (
            min(float(np.mean((feature - sample.astype(np.float32)) ** 2)) for sample in samples),
            value,
        )
        for value, samples in templates.items()
        if samples
    )


def _relative_margin(best_score: float, second_score: float) -> float:
    return (second_score - best_score) / second_score if second_score else 0.0


def _digit_glyphs(cell: np.ndarray, *, suppress_illumination: bool = False) -> list[np.ndarray]:
    """Segment one or two glyphs, including digits joined by thresholding."""

    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    region = gray[5:70, 5:70]
    binary = (
        _foreground_binary(region)
        if suppress_illumination
        else cv2.threshold(region, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    )
    count, labels, statistics, _ = cv2.connectedComponentsWithStats(binary)
    components: list[tuple[int, int, int, int, int, int]] = []
    for index in range(1, count):
        x, y, width, height, area = (int(value) for value in statistics[index])
        if 5 <= width <= 48 and 5 <= height <= 42 and 20 <= area <= 800:
            components.append((index, x, y, width, height, area))

    merged: list[tuple[int, int, int, int, np.ndarray]] = []
    used: set[int] = set()
    for first, (_, x, y, width, height, _) in enumerate(components):
        if first in used:
            continue
        matching: int | None = None
        for second in range(first + 1, len(components)):
            if second in used:
                continue
            _, other_x, other_y, other_width, other_height, _ = components[second]
            overlap = min(x + width, other_x + other_width) - max(x, other_x)
            vertical_gap = max(y, other_y) - min(y + height, other_y + other_height)
            combined_height = max(y + height, other_y + other_height) - min(y, other_y)
            if overlap >= min(width, other_width) // 2 and vertical_gap <= 7 and combined_height <= 42:
                matching = second
                break
        indices = [components[first][0]]
        bounds = [x, y, x + width, y + height]
        if matching is not None:
            used.add(matching)
            index, other_x, other_y, other_width, other_height, _ = components[matching]
            indices.append(index)
            bounds = [
                min(bounds[0], other_x),
                min(bounds[1], other_y),
                max(bounds[2], other_x + other_width),
                max(bounds[3], other_y + other_height),
            ]
        used.add(first)
        x1, y1, x2, y2 = bounds
        mask = np.isin(labels[y1:y2, x1:x2], indices).astype(np.uint8) * 255
        merged.append((x1, y1, x2 - x1, y2 - y1, mask))

    glyphs: list[tuple[int, np.ndarray]] = []
    for x, y, width, height, mask in merged:
        if x <= 10 and y == 0 and height >= 35:
            continue
        if not (5 <= width <= 48 and 15 <= height <= 42):
            continue
        chunks = [(x, mask)]
        if width > 26:
            projection = np.sum(mask > 0, axis=0)
            # Joined digits have a seam near the centre.  Searching too far
            # right can mistake the empty counter inside 0 for that seam,
            # turning a printed 20 into two 3-like glyphs.
            low = int(width * 0.35)
            high = int(width * 0.55)
            split = low + int(np.argmin(projection[low : high + 1]))
            chunks = [(x, mask[:, :split]), (x + split, mask[:, split:])]
        for position, glyph in chunks:
            bordered: np.ndarray = cv2.copyMakeBorder(glyph, 3, 3, 3, 3, cv2.BORDER_CONSTANT, value=0)
            normalized: np.ndarray = cv2.resize(bordered, (32, 48), interpolation=cv2.INTER_NEAREST)
            glyphs.append((position, normalized))
    return [glyph for _, glyph in sorted(glyphs, key=lambda item: item[0])]


def _digit_templates(reference_grid: np.ndarray) -> dict[str, list[np.ndarray]]:
    for suppress_illumination in (False, True):
        templates: dict[str, list[np.ndarray]] = {str(digit): [] for digit in range(10)}
        for value in range(1, 27):
            row = 0 if value <= 13 else 1
            column = (value - 1) % 13
            cell = reference_grid[
                row * 100 : (row + 1) * 100,
                column * 100 : (column + 1) * 100,
            ].copy()
            cell[43:] = 255
            glyphs = _digit_glyphs(cell, suppress_illumination=suppress_illumination)
            if len(glyphs) != len(str(value)):
                continue
            for digit, glyph in zip(str(value), glyphs, strict=True):
                templates[digit].append(glyph)
        if all(templates.values()):
            return templates
    raise ValueError("Reference grid did not provide templates for every digit")


def _coarse_glyph_feature(glyph: np.ndarray) -> np.ndarray:
    """Describe ink distribution without depending on exact pixel alignment."""

    ink = glyph.astype(np.float32) / 255.0
    return np.array(
        [
            float(np.mean(ink[y : y + 12, x : x + 8]))
            for y in range(0, glyph.shape[0], 12)
            for x in range(0, glyph.shape[1], 8)
        ],
        dtype=np.float32,
    )


def _enclosed_counter_count(glyph: np.ndarray, close_size: int) -> int:
    """Count substantial enclosed white regions inside a digit glyph."""

    ink: np.ndarray = np.where(glyph > 127, 255, 0).astype(np.uint8)
    if close_size:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_size, close_size))
        ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel)
    background = np.where(ink == 0, 255, 0).astype(np.uint8)
    count, _, statistics, _ = cv2.connectedComponentsWithStats(background)
    height, width = background.shape
    enclosed = 0
    for index in range(1, count):
        x, y, component_width, component_height, area = (int(value) for value in statistics[index])
        touches_edge = x == 0 or y == 0 or x + component_width == width or y + component_height == height
        if not touches_edge and area >= 8:
            enclosed += 1
    return enclosed


def _adjudicate_counter_family(
    glyph: np.ndarray,
    digit: str,
    pixel_scores: list[tuple[float, str]],
) -> str:
    """Use stable enclosed counters to adjudicate plausible 5/6/8 readings."""

    if digit not in {"5", "6", "8"}:
        return digit
    counters = tuple(_enclosed_counter_count(glyph, size) for size in (0, 2, 3, 4))
    top_two = {candidate for _, candidate in pixel_scores[:2]}
    if digit in {"6", "8"} and "5" in top_two and max(counters) == 0:
        return "5"
    if digit == "6" and "8" in top_two and min(counters[:3]) >= 3 and counters[3] == 2:
        return "8"
    return digit


def _classify_digit(glyph: np.ndarray, templates: dict[str, list[np.ndarray]]) -> tuple[str, float]:
    glyph_float = glyph.astype(np.float32)
    pixel_scores = sorted(
        (
            min(float(np.mean((glyph_float - sample.astype(np.float32)) ** 2)) for sample in samples),
            digit,
        )
        for digit, samples in templates.items()
    )
    best_score, digit = pixel_scores[0]
    second_score = pixel_scores[1][0]
    margin = _relative_margin(best_score, second_score)
    if digit == "0":
        feature = _coarse_glyph_feature(glyph)
        coarse_scores = sorted(
            (
                min(float(np.mean((feature - _coarse_glyph_feature(sample)) ** 2)) for sample in samples),
                candidate,
            )
            for candidate, samples in templates.items()
        )
        coarse_by_digit = {candidate: score for score, candidate in coarse_scores}
        if coarse_scores[0][1] == "6" and coarse_by_digit["0"] >= 2.0 * coarse_scores[0][0]:
            digit = "6"
    digit = _adjudicate_counter_family(glyph, digit, pixel_scores)
    return digit, margin


def _select_clue(attempts: list[str]) -> str | None:
    candidates = [text[-1] for text in attempts if text and text[-1].isalpha()]
    if not candidates:
        return None
    appearances = Counter(character for text in attempts for character in set(text) if character.isalpha())
    winner, votes = appearances.most_common(1)[0]
    return winner if votes > 1 else candidates[0]


def clue_ink_pixels(cell: np.ndarray) -> int:
    """Measure letter-like foreground away from reference-cell borders and numbers."""

    region = cell[30:92, 8:92]
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    return int(np.count_nonzero(_foreground_binary(gray)))


def extract_clues(
    reference_grid: np.ndarray,
    work_dir: Path,
    evidence: list[ClueEvidence] | None = None,
) -> dict[int, str]:
    """Read the large handwritten letters from the numbered reference cells."""

    clues: dict[int, str] = {}
    for value in range(1, 27):
        row = 0 if value <= 13 else 1
        column = (value - 1) % 13
        cell = reference_grid[
            row * 100 : (row + 1) * 100,
            column * 100 : (column + 1) * 100,
        ]
        region = cell[32:98, 5:98]
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        binary = _foreground_binary(gray)
        count, labels, statistics, _ = cv2.connectedComponentsWithStats(binary)
        cleaned = np.full_like(binary, 255)
        found = False
        for index in range(1, count):
            _, _, width, height, area = statistics[index]
            if height >= 25 and 8 <= width < 60 and area >= 100:
                cleaned[labels == index] = 0
                found = True
        if not found:
            continue
        cv2.imwrite(str(work_dir / f"clue-source-{value}.jpg"), cell)
        cleaned = cv2.copyMakeBorder(cleaned, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        cleaned = cv2.resize(cleaned, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
        image_path = work_dir / f"clue-{value}.png"
        cv2.imwrite(str(image_path), cleaned)
        with ThreadPoolExecutor(max_workers=3) as executor:
            attempts = list(
                executor.map(
                    lambda mode, image_path=image_path: _run(
                        [
                            "tesseract",
                            str(image_path),
                            "stdout",
                            "--psm",
                            str(mode),
                            "-l",
                            "eng",
                            "-c",
                            "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                        ]
                    )
                    .stdout.strip()
                    .upper(),
                    (10, 13, 6),
                )
            )
        clue = _select_clue(attempts)
        if evidence is not None:
            agreement = sum(clue in set(attempt) for attempt in attempts) / len(attempts) if clue is not None else 0.0
            evidence.append(
                ClueEvidence(
                    symbol=value,
                    reading=clue or "",
                    confidence=100.0 * agreement,
                )
            )
        if clue is not None:
            clues[value] = clue
    if len(set(clues.values())) != len(clues):
        raise ValueError("Recognised reference clues violate the letter bijection")
    return clues


def _classify_from_reference(
    item: tuple[int, int, np.ndarray],
    work_dir: Path,
    templates: dict[str, list[np.ndarray]],
    minimum_margin: float = MIN_TEMPLATE_MARGIN,
) -> CellReading:
    row, column, cell = item
    glyphs = _digit_glyphs(cell)
    if not 1 <= len(glyphs) <= 2:
        return CellReading(row=row, column=column, text="", confidence=0.0)
    digits: list[str] = []
    margins: list[float] = []
    for glyph in glyphs:
        digit, margin = _classify_digit(glyph, templates)
        digits.append(digit)
        margins.append(margin)
    text = "".join(digits)
    margin = min(margins)
    valid = text.isdigit() and 1 <= int(text) <= 26
    return CellReading(
        row=row,
        column=column,
        text=text,
        confidence=50.0 + 50.0 * margin,
        trusted=valid and margin >= minimum_margin,
    )


def _coarse_scores(glyph: np.ndarray, templates: dict[str, list[np.ndarray]]) -> list[tuple[float, str]]:
    feature = _coarse_glyph_feature(glyph)
    return sorted(
        (
            min(float(np.mean((feature - _coarse_glyph_feature(sample)) ** 2)) for sample in samples),
            digit,
        )
        for digit, samples in templates.items()
        if samples
    )


def _classify_from_board(
    item: tuple[int, int, np.ndarray],
    board_templates: dict[str, list[np.ndarray]],
    reference_templates: dict[str, list[np.ndarray]],
) -> CellReading:
    row, column, cell = item
    glyphs = _digit_glyphs(cell)
    if not 1 <= len(glyphs) <= 2:
        return CellReading(row=row, column=column, text="", confidence=0.0)
    digits: list[str] = []
    margins: list[float] = []
    for glyph in glyphs:
        board_scores = _coarse_scores(glyph, board_templates)
        reference_scores = _coarse_scores(glyph, reference_templates)
        if len(board_scores) < 2 or not reference_scores:
            return CellReading(row=row, column=column, text="", confidence=0.0)
        best_score, digit = board_scores[0]
        second_score = board_scores[1][0]
        margin = _relative_margin(best_score, second_score)
        if margin < MIN_TEMPLATE_MARGIN and reference_scores[0][1] != digit:
            return CellReading(row=row, column=column, text="", confidence=50.0 * margin)
        digits.append(digit)
        margins.append(margin)
    text = "".join(digits)
    valid = text.isdigit() and 1 <= int(text) <= 26
    return CellReading(
        row=row,
        column=column,
        text=text,
        confidence=50.0 + 50.0 * min(margins),
        trusted=valid,
    )


def _audit_confident_readings(
    readings: list[CellReading],
    cells_by_position: dict[tuple[int, int], np.ndarray],
    reference_templates: dict[str, list[np.ndarray]],
) -> list[CellReading]:
    samples: dict[str, list[tuple[tuple[int, int], np.ndarray]]] = {str(digit): [] for digit in range(10)}
    glyphs_by_position: dict[tuple[int, int], list[np.ndarray]] = {}
    for reading in readings:
        if not reading.trusted:
            continue
        position = (reading.row, reading.column)
        glyphs = _digit_glyphs(cells_by_position[position])
        glyphs_by_position[position] = glyphs
        if len(glyphs) == len(reading.text):
            for digit, glyph in zip(reading.text, glyphs, strict=True):
                samples[digit].append((position, _coarse_glyph_feature(glyph)))

    reference_features = {
        digit: [_coarse_glyph_feature(sample) for sample in digit_samples]
        for digit, digit_samples in reference_templates.items()
    }

    replacements: dict[tuple[int, int], CellReading] = {}
    for reading in readings:
        if not reading.trusted:
            continue
        position = (reading.row, reading.column)
        glyphs = glyphs_by_position[position]
        if len(glyphs) != len(reading.text):
            continue
        candidate_digits: list[str] = []
        margins: list[float] = []
        for glyph in glyphs:
            feature = _coarse_glyph_feature(glyph)
            board_scores = sorted(
                (
                    min(
                        float(np.mean((feature - sample_feature) ** 2))
                        for sample_position, sample_feature in digit_samples
                        if sample_position != position
                    ),
                    digit,
                )
                for digit, digit_samples in samples.items()
                if len(digit_samples) >= 5 and any(sample_position != position for sample_position, _ in digit_samples)
            )
            reference_scores = sorted(
                (
                    min(float(np.mean((feature - sample_feature) ** 2)) for sample_feature in digit_samples),
                    digit,
                )
                for digit, digit_samples in reference_features.items()
                if digit_samples
            )
            if len(board_scores) < 2:
                break
            margin = _relative_margin(board_scores[0][0], board_scores[1][0])
            if margin < MIN_TEMPLATE_MARGIN or reference_scores[0][1] != board_scores[0][1]:
                break
            candidate_digits.append(board_scores[0][1])
            margins.append(margin)
        if len(candidate_digits) != len(glyphs):
            continue
        candidate = int("".join(candidate_digits))
        if 1 <= candidate <= 26 and candidate != int(reading.text):
            replacements[position] = CellReading(
                row=reading.row,
                column=reading.column,
                text=str(candidate),
                confidence=50.0 + 50.0 * min(margins),
                trusted=True,
            )
    return [replacements.get((item.row, item.column), item) for item in readings]


def create_review_sheet(
    grid_image: np.ndarray,
    uncertainties: list[CellUncertainty],
    work_dir: Path,
    grid_size: int = GRID_SIZE,
) -> Path:
    """Create a coordinate-labelled contact sheet for unresolved cells."""

    columns = 4
    tile_width = 420
    tile_height = 220
    rows = max(1, (len(uncertainties) + columns - 1) // columns)
    sheet = np.full((rows * tile_height, columns * tile_width, 3), 245, dtype=np.uint8)
    for index, item in enumerate(uncertainties):
        row = item.row - 1
        column = item.column - 1
        y_edges = np.linspace(0, grid_image.shape[0], grid_size + 1).round().astype(int)
        x_edges = np.linspace(0, grid_image.shape[1], grid_size + 1).round().astype(int)
        original = grid_image[y_edges[row] : y_edges[row + 1], x_edges[column] : x_edges[column + 1]]
        original = cv2.resize(original, (190, 190), interpolation=cv2.INTER_CUBIC)
        cleaned = cv2.imread(str(work_dir / f"cell-{item.row}-{item.column}.png"))
        if cleaned is None:
            cleaned = np.full((190, 190, 3), 255, dtype=np.uint8)
        else:
            cleaned = cv2.resize(cleaned, (190, 190), interpolation=cv2.INTER_NEAREST)
        tile_row, tile_column = divmod(index, columns)
        y = tile_row * tile_height
        x = tile_column * tile_width
        sheet[y + 30 : y + 220, x : x + 190] = original
        sheet[y + 30 : y + 220, x + 200 : x + 390] = cleaned
        label = f"r{item.row:02d}c{item.column:02d}  OCR={item.reading or '--'}  {item.confidence:.0f}%"
        cv2.putText(sheet, label, (x + 4, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1, cv2.LINE_AA)
    destination = work_dir / "review.png"
    cv2.imwrite(str(destination), sheet)
    return destination


def recognize_photo(
    source: Path,
    work_dir: Path,
    *,
    trace: RecognitionTrace | None = None,
) -> PuzzleObservation:
    """Convert a supported square photographed puzzle into a conservative observation."""

    recognition_started = time.perf_counter()
    started = time.perf_counter()
    normalized_path = work_dir / "normalized.png"
    normalize_photo(source, normalized_path)
    image = cv2.imread(str(normalized_path))
    if image is None:
        raise ValueError(f"Could not decode photograph: {source}")
    if trace is not None:
        trace.record("decode", started)

    started = time.perf_counter()
    extracted_grid = extract_grid(image)
    grid_size = detect_grid_size(extracted_grid)
    grid_image = normalize_grid_lattice(extracted_grid, grid_size)
    cv2.imwrite(str(work_dir / "grid.png"), grid_image)
    if trace is not None:
        trace.record("grid", started)

    started = time.perf_counter()
    try:
        reference_grid = extract_reference_grid(image)
    except ValueError:
        templates = None
        digit_templates = None
        clues: dict[int, str] = {}
        clue_evidence: list[ClueEvidence] = []
    else:
        cv2.imwrite(str(work_dir / "reference-grid.png"), reference_grid)
        templates = _reference_templates(reference_grid)
        digit_templates = _digit_templates(reference_grid)
        clue_evidence = []
        clues = extract_clues(reference_grid, work_dir, clue_evidence)
    if trace is not None:
        trace.record("reference", started)

    started = time.perf_counter()
    cells = _cell_images(grid_image, grid_size)
    blocks = _block_mask(cells, grid_size)
    playable = [cell for cell, blocked in zip(cells, blocks, strict=True) if not blocked]
    if trace is not None:
        trace.record("topology", started)

    started = time.perf_counter()
    if digit_templates is not None:
        classification_stage = time.perf_counter()
        with ThreadPoolExecutor(max_workers=8) as executor:
            readings = list(
                executor.map(
                    lambda cell: _classify_from_reference(cell, work_dir, digit_templates),
                    playable,
                )
            )
        if trace is not None:
            trace.record("classify.reference", classification_stage)
        cells_by_position = {(row, column): cell for row, column, cell in playable}
        expanded_templates = {digit: list(samples) for digit, samples in digit_templates.items()}
        for reading in readings:
            if not reading.trusted:
                continue
            glyphs = _digit_glyphs(cells_by_position[(reading.row, reading.column)])
            if len(glyphs) == len(reading.text):
                for digit, glyph in zip(reading.text, glyphs, strict=True):
                    expanded_templates[digit].append(glyph)
        second_pass = [reading for reading in readings if not reading.trusted]
        if second_pass:
            classification_stage = time.perf_counter()
            with ThreadPoolExecutor(max_workers=8) as executor:
                reconsidered = list(
                    executor.map(
                        lambda item: _classify_from_reference(
                            (
                                item.row,
                                item.column,
                                cells_by_position[(item.row, item.column)],
                            ),
                            work_dir,
                            expanded_templates,
                            0.30,
                        ),
                        second_pass,
                    )
                )
            replacements = {(item.row, item.column): item for item in reconsidered}
            readings = [replacements.get((item.row, item.column), item) for item in readings]
            if trace is not None:
                trace.record("classify.expanded", classification_stage)
        classification_stage = time.perf_counter()
        for _ in range(2):
            unresolved = [reading for reading in readings if not reading.trusted]
            if not unresolved:
                break
            board_glyph_templates: dict[str, list[np.ndarray]] = {str(digit): [] for digit in range(10)}
            for reading in readings:
                if not reading.trusted:
                    continue
                glyphs = _digit_glyphs(cells_by_position[(reading.row, reading.column)])
                if len(glyphs) == len(reading.text):
                    for digit, glyph in zip(reading.text, glyphs, strict=True):
                        board_glyph_templates[digit].append(glyph)
            reconsidered = [
                _classify_from_board(
                    (
                        item.row,
                        item.column,
                        cells_by_position[(item.row, item.column)],
                    ),
                    board_glyph_templates,
                    digit_templates,
                )
                for item in unresolved
            ]
            replacements = {(item.row, item.column): item for item in reconsidered if item.trusted}
            readings = [replacements.get((item.row, item.column), item) for item in readings]
        if trace is not None:
            trace.record("classify.board", classification_stage)
        classification_stage = time.perf_counter()
        readings = _audit_confident_readings(readings, cells_by_position, digit_templates)
        if trace is not None:
            trace.record("classify.audit", classification_stage)
    else:
        classification_stage = time.perf_counter()
        with ThreadPoolExecutor(max_workers=8) as executor:
            readings = list(executor.map(lambda cell: _read_cell(cell, work_dir), playable))
        if trace is not None:
            trace.record("classify.tesseract", classification_stage)
    retry = [reading for reading in readings if not reading.trusted]
    if retry:
        classification_stage = time.perf_counter()
        cells_by_position = {(row, column): cell for row, column, cell in playable}
        with ThreadPoolExecutor(max_workers=8) as executor:
            first_ocr = list(
                executor.map(
                    lambda item: _read_cell(
                        (
                            item.row,
                            item.column,
                            cells_by_position[(item.row, item.column)],
                        ),
                        work_dir,
                    ),
                    retry,
                )
            )
        with ThreadPoolExecutor(max_workers=8) as executor:
            retried = list(
                executor.map(
                    lambda item: _retry_cell(
                        item,
                        work_dir,
                        (
                            _template_value(cells_by_position[(item.row, item.column)], templates)
                            if templates is not None
                            else None
                        ),
                    ),
                    first_ocr,
                )
            )
        original_by_position = {(item.row, item.column): item for item in retry}
        retried = [
            (
                CellReading(
                    row=item.row,
                    column=item.column,
                    text=item.text,
                    confidence=max(
                        item.confidence,
                        original_by_position[(item.row, item.column)].confidence,
                    ),
                    trusted=True,
                )
                if item.text.isdigit()
                and 1 <= int(item.text) <= 26
                and item.text == original_by_position[(item.row, item.column)].text
                and item.confidence >= 50.0
                else item
            )
            for item in retried
        ]
        replacements = {(item.row, item.column): item for item in retried}
        readings = [replacements.get((item.row, item.column), item) for item in readings]
        if trace is not None:
            trace.record("classify.tesseract", classification_stage)

    if templates is not None:
        classification_stage = time.perf_counter()
        cells_by_position = {(row, column): cell for row, column, cell in playable}
        board_templates: dict[int, list[np.ndarray]] = {}
        for reading in readings:
            if reading.trusted and reading.text.isdigit():
                board_templates.setdefault(int(reading.text), []).append(
                    _number_feature(cells_by_position[(reading.row, reading.column)])
                )
        reference_templates = {value: [feature] for value, feature in templates.items()}
        replacements = {}
        for reading in readings:
            if reading.trusted:
                continue
            feature = _number_feature(cells_by_position[(reading.row, reading.column)]).astype(np.float32)
            reference_scores = _template_scores(feature, reference_templates)
            board_scores = _template_scores(feature, board_templates)
            if len(reference_scores) < 2 or not board_scores:
                continue
            reference_margin = _relative_margin(reference_scores[0][0], reference_scores[1][0])
            reference_value = reference_scores[0][1]
            if reference_margin >= MIN_WHOLE_NUMBER_MARGIN and board_scores[0][1] == reference_value:
                replacements[(reading.row, reading.column)] = CellReading(
                    row=reading.row,
                    column=reading.column,
                    text=str(reference_value),
                    confidence=max(MIN_OCR_CONFIDENCE, 50.0 + 50.0 * reference_margin),
                    trusted=True,
                )
        readings = [replacements.get((item.row, item.column), item) for item in readings]
        if trace is not None:
            trace.record("classify.whole", classification_stage)
    if trace is not None:
        trace.record("classify", started)
    readings_by_position = {(item.row, item.column): item for item in readings}

    rows: list[tuple[int | str, ...]] = []
    uncertainties: list[CellUncertainty] = []
    for row in range(grid_size):
        values: list[int | str] = []
        for column in range(grid_size):
            index = row * grid_size + column
            if blocks[index]:
                values.append(BLOCK)
                continue
            reading = readings_by_position[(row, column)]
            try:
                value = int(reading.text)
            except ValueError:
                value = 0
            if 1 <= value <= 26 and (reading.trusted or reading.confidence >= MIN_OCR_CONFIDENCE):
                values.append(value)
            else:
                values.append(UNKNOWN)
                uncertainties.append(
                    CellUncertainty(
                        row=row + 1,
                        column=column + 1,
                        reading=reading.text,
                        confidence=reading.confidence,
                        reason=(
                            "OCR value outside 1-26" if reading.text and not 1 <= value <= 26 else "low OCR confidence"
                        ),
                    )
                )
        rows.append(tuple(values))

    create_review_sheet(grid_image, uncertainties, work_dir, grid_size)
    photo_format = detect_photo_format(source)
    observation = PuzzleObservation(
        source=source,
        source_format=photo_format.display_name,
        grid=tuple(rows),
        clues=clues,
        uncertainties=tuple(uncertainties),
        evidence=tuple(
            CellEvidence(
                row=reading.row + 1,
                column=reading.column + 1,
                reading=reading.text,
                confidence=reading.confidence,
                trusted=reading.trusted,
            )
            for reading in readings
        ),
        clue_evidence=tuple(clue_evidence),
    )
    if trace is not None:
        trace.elapsed_seconds = time.perf_counter() - recognition_started
    return observation
