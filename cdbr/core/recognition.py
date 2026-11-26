"""Photograph normalization, grid extraction, and conservative cell OCR."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from functools import lru_cache
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
MIN_REVIEWED_FAMILY_MARGIN = 0.10
MIN_NINE_NINETEEN_PROMOTION_MARGIN = 0.23
STRONG_NINE_NINETEEN_PROMOTION_MARGIN = 0.30
MAX_SINGLE_NINE_INK_PIXELS = 450
HIL_REVIEW_CONFIDENCE = 68.0
HIL_AMBIGUOUS_NUMBERS = frozenset((5, 6, 8, 9, 16, 18, 19))
WHOLE_TOKEN_PIPELINE = "whole-token"
LEGACY_PIPELINE = "legacy"
TESSERACT_PIPELINE = "tesseract"
OCR_PIPELINES = (TESSERACT_PIPELINE, LEGACY_PIPELINE, WHOLE_TOKEN_PIPELINE)
WHOLE_TOKEN_PROFILE = "book-15x15-v1"
LOCAL_BACKGROUND_KERNEL = 31
# Across 520 human-reviewed reference cells, obvious blanks contained at most
# 387 foreground pixels while the faintest real clue contained 428.  Keep the
# shelf slightly inside that measured gap so dirt can remain an automatic blank
# without allowing a missed letter to pass silently.
MIN_CLUE_REVIEW_INK_PIXELS = 420


@dataclass(frozen=True, kw_only=True)
class CellReading:
    row: int
    column: int
    text: str
    confidence: float
    trusted: bool = False


def needs_hil_review(reading: CellReading | CellEvidence) -> bool:
    """Return whether gameplay should ask a human to confirm this fresh reading."""

    if not reading.trusted:
        return True
    text = reading.text if isinstance(reading, CellReading) else reading.reading
    return reading.confidence < HIL_REVIEW_CONFIDENCE and text.isdigit() and int(text) in HIL_AMBIGUOUS_NUMBERS


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


def find_grid_corners(image: np.ndarray, *, reference: np.ndarray | None = None) -> np.ndarray:
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
        if reference is not None and not _board_above_reference(points, reference):
            continue
        width, height = cv2.minAreaRect(points)[1]
        if min(width, height) <= 0 or max(width, height) / min(width, height) >= 1.3:
            continue
        candidates.append((area_fraction, points))

    if not candidates:
        # Smaller or foreshortened grids can fail the fast contour filters.
        # Require internal lattice evidence before accepting a relaxed contour.
        global_binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        for mask in (binary, global_binary):
            contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            for contour in sorted(contours, key=cv2.contourArea, reverse=True):
                fraction = cv2.contourArea(contour) / image_area
                if fraction < 0.06:
                    break
                if fraction >= 0.65:
                    continue
                polygon = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
                if len(polygon) != 4 or not cv2.isContourConvex(polygon):
                    continue
                corners = _ordered_corners(polygon.reshape(4, 2))
                if reference is not None and not _board_above_reference(corners, reference):
                    continue
                try:
                    detect_grid_size(_warp_grid(image, corners))
                except ValueError:
                    continue
                return corners
        raise ValueError("Could not locate a square puzzle grid in the photograph")

    return _ordered_corners(max(candidates, key=lambda candidate: candidate[0])[1])


def extract_grid(image: np.ndarray, *, padding: int = 0) -> np.ndarray:
    """Locate the near-square puzzle grid and rectify its perspective."""

    return _warp_grid(image, find_grid_corners(image), padding=padding)


def _warp_grid(image: np.ndarray, corners: np.ndarray, *, padding: int = 0) -> np.ndarray:
    destination = np.array(
        [[0, 0], [WARP_SIZE - 1, 0], [WARP_SIZE - 1, WARP_SIZE - 1], [0, WARP_SIZE - 1]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(corners, destination + padding)
    size = WARP_SIZE + 2 * padding
    return cv2.warpPerspective(image, transform, (size, size))


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


def _adaptive_lattice_mask(gray: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 71, 15)


def _detect_grid_size(binary: np.ndarray) -> int | None:
    """Infer a supported square-grid size from its internal rule lines."""

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
    return max(candidates)[1] if candidates else None


def detect_grid_size(grid: np.ndarray) -> int:
    """Infer a supported square-grid size from its internal rule lines."""

    gray = cv2.cvtColor(grid, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    size = _detect_grid_size(binary) or _detect_grid_size(_adaptive_lattice_mask(gray))
    if size is None:
        raise ValueError("Could not determine whether the puzzle grid is 13×13 or 15×15")
    return size


def normalize_grid_lattice(grid: np.ndarray, grid_size: int = GRID_SIZE) -> np.ndarray:
    """Map measured internal grid lines onto an exact square lattice."""

    gray = cv2.cvtColor(grid, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    x_positions = _grid_line_positions(binary, vertical=True, grid_size=grid_size)
    y_positions = _grid_line_positions(binary, vertical=False, grid_size=grid_size)
    if x_positions is None or y_positions is None:
        adaptive = _adaptive_lattice_mask(gray)
        x_positions = x_positions or _grid_line_positions(adaptive, vertical=True, grid_size=grid_size)
        y_positions = y_positions or _grid_line_positions(adaptive, vertical=False, grid_size=grid_size)
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


def _cell_edges(length: int, grid_size: int) -> np.ndarray:
    return np.linspace(0, length, grid_size + 1).round().astype(int)


def _trace_grid_rules(gray: np.ndarray, grid_size: int, padding: int) -> np.ndarray:
    """Estimate the curved row rules from locally visible dark lines."""

    spacing = (WARP_SIZE - 1) / grid_size
    radius = round(spacing * 0.30)
    # Thin rules and edges where a white cell meets a solid block both provide
    # boundary evidence. A flat black interior contributes neither.
    offset = 7
    contrast = np.zeros_like(gray)
    contrast[offset:-offset] = cv2.subtract(np.minimum(gray[: -2 * offset], gray[2 * offset :]), gray[offset:-offset])
    steps = np.zeros_like(gray)
    steps[2:-2] = cv2.absdiff(gray[:-4], gray[4:])
    contrast = cv2.blur(cv2.max(contrast, steps), (41, 3))
    columns = np.arange(padding + 20, padding + WARP_SIZE - 20, 24)
    coordinates = np.arange(padding, padding + WARP_SIZE)
    rules = []
    for expected in np.linspace(padding, padding + WARP_SIZE - 1, grid_size + 1):
        low, high = round(expected) - radius, round(expected) + radius + 1
        samples = contrast[low:high, columns]
        best = np.argmax(samples, axis=0)
        valid = samples[best, np.arange(len(columns))] >= 20
        x = columns[valid]
        y = low + best[valid]
        if len(x) >= 10 and np.ptp(x) >= WARP_SIZE * 0.45:
            for _ in range(3):
                fit = np.polynomial.Polynomial.fit(x, y, 2)
                keep = np.abs(y - fit(x)) <= 8
                if keep.all() or np.count_nonzero(keep) < 10:
                    break
                x, y = x[keep], y[keep]
            curve = np.clip(fit(coordinates), expected - radius, expected + radius)
        else:
            curve = np.full(WARP_SIZE, expected)
        rules.append(curve)
    observed = np.asarray(rules)
    nominal = np.linspace(padding, padding + WARP_SIZE - 1, grid_size + 1)[:, None]
    offsets = observed - nominal
    # Adjacent rules bend together. A median across nearby offsets prevents
    # a weak rule from crowding its neighbor without imposing uniform spacing.
    supported = np.asarray([np.median(offsets[max(0, k - 2) : k + 3], axis=0) for k in range(grid_size + 1)])
    return nominal + 0.65 * offsets + 0.35 * supported


def _grid_vertices(board: np.ndarray, grid_size: int, padding: int) -> np.ndarray:
    """Intersect curved row and column rules on the padded source board."""
    gray = cv2.cvtColor(board, cv2.COLOR_BGR2GRAY)
    horizontal = _trace_grid_rules(gray, grid_size, padding)
    vertical = _trace_grid_rules(gray.T, grid_size, padding)
    source = np.arange(padding, padding + WARP_SIZE)
    x, y = np.meshgrid(
        np.linspace(source[0], source[-1], grid_size + 1), np.linspace(source[0], source[-1], grid_size + 1)
    )
    for _ in range(4):
        y = np.asarray([np.interp(row, source, rule) for row, rule in zip(x, horizontal, strict=True)])
        x = np.asarray([np.interp(column, source, rule) for column, rule in zip(y.T, vertical, strict=True)]).T
    return np.stack((x, y), axis=-1)


def _dewarp_vertex_mesh(board: np.ndarray, vertices: np.ndarray) -> np.ndarray:
    """Sample each Cartesian locker from its four shared source vertices."""

    grid_size = len(vertices) - 1
    target = np.linspace(0, WARP_SIZE - 1, grid_size + 1)
    pixels = np.arange(WARP_SIZE)
    maps = []
    for axis in range(2):
        rows = np.asarray([np.interp(pixels, target, row) for row in vertices[:, :, axis]])
        maps.append(np.asarray([np.interp(pixels, target, column) for column in rows.T], dtype=np.float32).T)
    return cv2.remap(board, maps[0], maps[1], cv2.INTER_LINEAR)


def _cell_images(grid: np.ndarray, grid_size: int = GRID_SIZE) -> list[tuple[int, int, np.ndarray]]:
    y_edges = _cell_edges(grid.shape[0], grid_size)
    x_edges = _cell_edges(grid.shape[1], grid_size)
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


def _number_region(shape: tuple[int, ...]) -> slice:
    return slice(0, 75) if min(shape[:2]) >= 110 else slice(5, 70)


def _number_ink_mask(cell: np.ndarray, *, suppress_illumination: bool, adaptive_crop: bool = False) -> np.ndarray:
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    # The 13×13 lattice yields wider cells. Its printed digits can touch the
    # top or left rule inside the usual fixed inset.
    wide_cell = min(gray.shape) >= 110
    bounds = slice(0, 75) if adaptive_crop else _number_region(gray.shape)
    region = gray[bounds, bounds]
    binary = (
        _foreground_binary(region)
        if suppress_illumination
        else cv2.threshold(region, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    )
    if wide_cell or adaptive_crop:
        # Retain short glyph strokes while removing rules that span the crop.
        # Count only strokes inside the crop. OpenCV's neutral default border
        # can let a short stroke touching the edge pass the long-rule filter.
        horizontal = cv2.morphologyEx(
            binary, cv2.MORPH_OPEN, np.ones((1, 50), dtype=np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0
        )
        vertical = cv2.morphologyEx(
            binary, cv2.MORPH_OPEN, np.ones((50, 1), dtype=np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0
        )
        if adaptive_crop:
            # A joined pair can have a long baseline. Away from the top,
            # remove only strokes wider than the allowed joined-glyph crop.
            horizontal[8:] = cv2.morphologyEx(
                binary[8:],
                cv2.MORPH_OPEN,
                np.ones((1, 61), dtype=np.uint8),
                borderType=cv2.BORDER_CONSTANT,
                borderValue=0,
            )
            vertical[:, 8:] = 0
        binary = cv2.subtract(binary, cv2.bitwise_or(horizontal, vertical))
    if adaptive_crop:
        # A partial top rule can survive the full-length rule filter.
        top = binary[:8]
        rule = cv2.morphologyEx(
            top, cv2.MORPH_OPEN, np.ones((1, 28), dtype=np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0
        )
        binary[: len(top)] = cv2.subtract(top, rule)
    return binary


def _clean_number(cell: np.ndarray, *, suppress_illumination: bool = False, adaptive_crop: bool = False) -> np.ndarray:
    binary = _number_ink_mask(cell, suppress_illumination=suppress_illumination, adaptive_crop=adaptive_crop)
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
    if adaptive_crop or (min(cell.shape[:2]) >= 110 and np.all(cleaned == 255)):
        # Retain the second glyph even when the first already passed the stricter filter.
        for index, (x, y, width, height, area) in enumerate(statistics[1:], 1):
            if x <= 50 and y <= 18 and 8 <= width <= 60 and 15 <= height <= 48 and 50 <= area <= 1100:
                cleaned[labels == index] = 0
    if adaptive_crop:
        # A broken leading 1 can have two short pieces stacked in the same column.
        for top, (x, y, width, height, area) in enumerate(statistics[1:], 1):
            if not (x <= 38 and y <= 18 and 5 <= width <= 22 and 7 <= height < 15 and area >= 35):
                continue
            for bottom, (bx, by, bw, bh, ba) in enumerate(statistics[1:], 1):
                overlap = min(x + width, bx + bw) - max(x, bx)
                if 0 <= by - (y + height) <= 6 and overlap >= 3 and 4 <= bw <= 18 and 7 <= bh <= 16 and ba >= 30:
                    cleaned[(labels == top) | (labels == bottom)] = 0
        x, y, width, height = cv2.boundingRect(cv2.bitwise_not(cleaned))
        if width and height:
            cleaned = cleaned[y : y + height, x : x + width]
        cleaned = cv2.resize(cleaned, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
        if width and height:
            cleaned = _separate_number_glyphs(_remove_top_overhang(cleaned))
        return cv2.copyMakeBorder(cleaned, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
    cleaned = cv2.copyMakeBorder(cleaned, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return cv2.resize(cleaned, None, fx=5, fy=5, interpolation=cv2.INTER_NEAREST)


def _remove_top_overhang(glyph: np.ndarray) -> np.ndarray:
    """Remove thin horizontal extensions attached near the top of the ink."""
    ink = cv2.bitwise_not(glyph)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    opened = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)
    removed = cv2.subtract(ink, opened)
    _, labels, statistics, _ = cv2.connectedComponentsWithStats(removed)
    attached = cv2.dilate(opened, np.ones((3, 3), dtype=np.uint8))
    glyph = glyph.copy()
    for index, (x, y, width, height, _) in enumerate(statistics[1:], 1):
        if y > 4 or width < 12 or height > glyph.shape[0] * 0.45:
            continue
        component = labels[y : y + height, x : x + width] == index
        # A long, thin top run can turn down at the edge of the grid.
        if np.count_nonzero(component[:4], axis=1).max() >= 12 and np.any(
            component & (attached[y : y + height, x : x + width] != 0)
        ):
            glyph[labels == index] = 255
    return glyph


def _separate_number_glyphs(glyph: np.ndarray) -> np.ndarray:
    height, width = glyph.shape
    if width < height * 0.95:
        return glyph
    ink = (glyph < 128).astype(np.uint8)
    projection = ink.sum(axis=0)
    lo, hi = max(1, int(width * 0.26)), min(width - 1, int(width * 0.65))
    if lo > hi:
        return glyph
    split = min(
        range(lo, hi + 1),
        key=lambda i: (projection[i - 1] + projection[i]) / 2 + abs(i - width * 0.46) * 0.08,
    )
    left = cv2.boundingRect(ink[:, :split])
    right = cv2.boundingRect(ink[:, split:])
    if (
        min(left[3], right[3]) < height * 0.72
        or min(left[2], right[2]) < width * 0.19
        or (width < height * 1.18 and projection[split - 1] + projection[split] > height * 0.12)
    ):
        return glyph
    gap = np.full((height, 8), 255, dtype=glyph.dtype)
    return np.concatenate((glyph[:, :split], gap, glyph[:, split:]), axis=1)


def _read_cell(item: tuple[int, int, np.ndarray], work_dir: Path) -> CellReading:
    row, column, cell = item
    image_path = work_dir / f"cell-{row + 1}-{column + 1}.png"
    cv2.imwrite(str(image_path), _clean_number(cell, adaptive_crop=True))
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


def _retry_cell(
    reading: CellReading, work_dir: Path, template_value: int | None, cell: np.ndarray | None = None
) -> CellReading:
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
    if valid:
        winner, votes = Counter(attempt.text for attempt in valid).most_common(1)[0]
        if votes >= 3 and template_value is not None and int(winner) == template_value:
            agreeing = [attempt for attempt in valid if attempt.text == winner]
            return CellReading(
                row=reading.row,
                column=reading.column,
                text=winner,
                confidence=max(MIN_OCR_CONFIDENCE, sum(item.confidence for item in agreeing) / votes),
            )
    if (
        cell is not None
        and min(cell.shape[:2]) >= 110
        and all(attempt.confidence < MIN_OCR_CONFIDENCE for attempt in valid)
    ):
        # Retry without the top rule only after the full crop has had a chance.
        masked = cell.copy()
        masked[:6] = 255
        trimmed_path = image_path.with_stem(f"{image_path.stem}-top-trim")
        cv2.imwrite(str(trimmed_path), _clean_number(masked, adaptive_crop=True))
        trimmed = _ocr_image(trimmed_path, row=reading.row, column=reading.column, page_segmentation_mode=6)
        if trimmed.text.isdigit() and 1 <= int(trimmed.text) <= 26 and trimmed.confidence >= MIN_OCR_CONFIDENCE:
            return trimmed
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


def _board_above_reference(board: np.ndarray, reference: np.ndarray) -> bool:
    board_center = np.mean(board, axis=0)
    reference_center = np.mean(reference, axis=0)
    strip_width = float(np.ptp(reference[:, 0]))
    return bool(
        np.max(board[:, 1]) < reference_center[1] and abs(board_center[0] - reference_center[0]) < strip_width / 3
    )


def _orient_photo_grid(image: np.ndarray, *, padding: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """For a sideways reference strip, test both quarter-turns for its board."""

    try:
        strip = find_reference_corners(image)
    except ValueError:
        return image, extract_grid(image, padding=padding)
    if np.ptp(strip[:, 0]) >= np.ptp(strip[:, 1]):
        return image, extract_grid(image, padding=padding)
    for turn in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
        turned = cv2.rotate(image, turn)
        try:
            reference = find_reference_corners(turned)
            grid = _warp_grid(turned, find_grid_corners(turned, reference=reference), padding=padding)
            board = slice(padding, padding + WARP_SIZE)
            detect_grid_size(grid[board, board])
        except ValueError:
            continue
        return turned, grid
    raise ValueError("Could not locate a square puzzle grid above the sideways reference strip")


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


def _reviewed_number_feature(cell: np.ndarray) -> np.ndarray:
    """Return the compact feature used by the reviewed ambiguity bank."""

    return cv2.resize(_number_feature(cell), (20, 30), interpolation=cv2.INTER_AREA)


def _review_with_scan_matches(
    readings: list[CellReading], cells: dict[tuple[int, int], np.ndarray]
) -> list[CellReading]:
    """Use repeated numbers from this photograph as evidence for review."""
    features = (
        np.asarray(
            [_reviewed_number_feature(cells[item.row, item.column]).ravel() for item in readings], dtype=np.float32
        )
        / 255
    )
    if not len(features):
        return readings
    has_ink = np.any(features < 1, axis=1)
    anchors = np.asarray(
        [i for i, item in enumerate(readings) if item.trusted and item.confidence >= 90 and has_ink[i]], dtype=np.intp
    )
    if len(anchors) < 3:
        return readings
    samples = features[anchors]
    squared = np.sum(features * features, axis=1)
    distances = (squared[:, None] + squared[anchors] - 2 * features @ samples.T) / features.shape[1]
    distances[anchors, np.arange(len(anchors))] = np.inf
    reviewed = list(readings)
    for i, item in enumerate(readings):
        if not has_ink[i]:
            continue
        nearest = np.argsort(distances[i])
        best, corroborating = nearest[:2]
        proposed = readings[anchors[best]].text
        if proposed == item.text or readings[anchors[corroborating]].text != proposed:
            continue
        other = next(
            (j for j in nearest if readings[anchors[j]].text != proposed and np.isfinite(distances[i, j])), None
        )
        distance = max(0.0, float(distances[i, corroborating]))
        if other is None or distance > 0.025 or _relative_margin(distance, float(distances[i, other])) < 0.35:
            continue
        reviewed[i] = CellReading(
            row=item.row,
            column=item.column,
            text=item.text if item.trusted else proposed,
            confidence=item.confidence if item.trusted else 0.0,
            trusted=False,
        )
    return reviewed


@lru_cache(maxsize=1)
def _whole_number_banks() -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    source = Path(__file__).parents[1] / "assets" / "ocr" / "number-tokens.npz"
    if not source.is_file():
        return (
            np.empty((0, 0, 30, 20), dtype=np.uint8),
            np.empty(0, dtype=np.uint8),
            np.empty(0, dtype=np.uint8),
            "",
        )
    with np.load(source) as archive:
        return (
            archive["features"],
            archive["labels"],
            archive["exclusions"],
            str(archive["profile"]),
        )


def _whole_number_templates(excluded_puzzle_id: int | None) -> tuple[np.ndarray, np.ndarray]:
    banks, labels, exclusions, profile = _whole_number_banks()
    if profile != WHOLE_TOKEN_PROFILE:
        return np.empty((0, 30, 20), dtype=np.uint8), labels
    requested = excluded_puzzle_id or 0
    matches = np.flatnonzero(exclusions == requested)
    if not len(matches):
        matches = np.flatnonzero(exclusions == 0)
    if not len(matches):
        return np.empty((0, 30, 20), dtype=np.uint8), labels
    return banks[int(matches[0])], labels


def _classify_whole_number(
    item: tuple[int, int, np.ndarray],
    prototypes: np.ndarray,
    labels: np.ndarray,
) -> CellReading:
    """Classify the complete printed number before attempting digit segmentation."""

    row, column, cell = item
    if not len(prototypes):
        return CellReading(row=row, column=column, text="", confidence=0.0)
    feature = _reviewed_number_feature(cell).astype(np.float32)
    if np.all(feature == 255):
        return CellReading(row=row, column=column, text="", confidence=0.0)
    distances = np.mean((prototypes.astype(np.float32) - feature) ** 2, axis=(1, 2))
    class_scores = sorted((float(np.min(distances[labels == value])), int(value)) for value in np.unique(labels))
    best_score, value = class_scores[0]
    margin = _relative_margin(best_score, class_scores[1][0])
    return CellReading(
        row=row,
        column=column,
        text=str(value),
        confidence=50.0 + 50.0 * margin,
        trusted=margin >= MIN_WHOLE_NUMBER_MARGIN,
    )


@lru_cache(maxsize=1)
def _reviewed_number_templates() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    source = Path(__file__).parents[1] / "assets" / "ocr" / "number-ambiguities.npz"
    if not source.is_file():
        return (
            np.empty((0, 30, 20), dtype=np.uint8),
            np.empty(0, dtype=np.uint8),
            np.empty(0, dtype=np.uint8),
        )
    with np.load(source) as archive:
        return archive["features"], archive["labels"], archive["puzzle_ids"]


def _reviewed_number_assessment(
    cell: np.ndarray,
    family: frozenset[int],
    *,
    excluded_puzzle_id: int | None = None,
) -> tuple[int, float] | None:
    features, labels, puzzle_ids = _reviewed_number_templates()
    eligible = np.isin(labels, tuple(family))
    if excluded_puzzle_id is not None:
        eligible &= puzzle_ids != excluded_puzzle_id
    candidate_features = features[eligible]
    candidate_labels = labels[eligible]
    if not len(candidate_labels):
        return None
    feature = _reviewed_number_feature(cell).astype(np.float32)
    distances = np.mean((candidate_features.astype(np.float32) - feature) ** 2, axis=(1, 2))
    scores = sorted(
        (float(np.min(distances[candidate_labels == value])), int(value)) for value in np.unique(candidate_labels)
    )
    margin = _relative_margin(scores[0][0], scores[1][0]) if len(scores) > 1 else 1.0
    return scores[0][1], margin


def _reviewed_number_vote(
    cell: np.ndarray,
    family: frozenset[int],
    *,
    excluded_puzzle_id: int | None = None,
) -> int | None:
    """Return the closest reviewed family label for diagnostics and tests."""

    assessment = _reviewed_number_assessment(cell, family, excluded_puzzle_id=excluded_puzzle_id)
    return assessment[0] if assessment is not None else None


def _quadrant_ink_share(feature: np.ndarray) -> float:
    """Measure upper-right ink mass after whole-glyph alignment."""

    ink = 1.0 - feature.astype(np.float32) / 255.0
    height, width = ink.shape
    return float(np.sum(ink[: height // 2, width // 2 :]) / max(float(np.sum(ink)), 1e-6))


@lru_cache(maxsize=64)
def _reviewed_six_eight_quadrant_thresholds(excluded_puzzle_id: int | None) -> tuple[float, float] | None:
    features, labels, puzzle_ids = _reviewed_number_templates()
    eligible = np.isin(labels, (6, 8))
    if excluded_puzzle_id is not None:
        eligible &= puzzle_ids != excluded_puzzle_id
    six = features[eligible & (labels == 6)]
    eight = features[eligible & (labels == 8)]
    if not len(six) or not len(eight):
        return None
    lower = float(np.percentile([_quadrant_ink_share(item) for item in eight], 1.0))
    upper = float(np.percentile([_quadrant_ink_share(item) for item in six], 99.0))
    return lower, upper


def _reviewed_six_eight_quadrant_vote(
    cell: np.ndarray,
    *,
    excluded_puzzle_id: int | None = None,
) -> int | None:
    """Return only an extreme, corpus-calibrated 6/8 quadrant vote."""

    thresholds = _reviewed_six_eight_quadrant_thresholds(excluded_puzzle_id)
    if thresholds is None:
        return None
    lower, upper = thresholds
    share = _quadrant_ink_share(_reviewed_number_feature(cell))
    if share < lower:
        return 6
    if share > upper:
        return 8
    return None


def _number_ink_pixels(cell: np.ndarray) -> int:
    """Measure raw printed-number weight before glyph resizing loses scale."""

    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)[5:70, 5:70]
    return int(np.count_nonzero(_foreground_binary(gray)))


def _adjudicate_nine_nineteen(
    reading: CellReading,
    cell: np.ndarray,
    *,
    excluded_puzzle_id: int | None = None,
) -> CellReading:
    """Promote only strongly corroborated false leading ones in the 9/19 family."""

    if reading.text != "19":
        return reading
    token_arities = {
        len(_digit_glyphs(cell)),
        len(_digit_glyphs(cell, suppress_illumination=True)),
    }
    if token_arities != {1}:
        return reading
    assessment = _reviewed_number_assessment(
        cell,
        frozenset((9, 19)),
        excluded_puzzle_id=excluded_puzzle_id,
    )
    if assessment is None:
        return reading
    vote, margin = assessment
    light_single_glyph = (
        margin >= MIN_NINE_NINETEEN_PROMOTION_MARGIN and _number_ink_pixels(cell) <= MAX_SINGLE_NINE_INK_PIXELS
    )
    if vote != 9 or not (margin >= STRONG_NINE_NINETEEN_PROMOTION_MARGIN or light_single_glyph):
        return reading
    return CellReading(
        row=reading.row,
        column=reading.column,
        text="9",
        confidence=max(reading.confidence, HIL_REVIEW_CONFIDENCE),
        trusted=True,
    )


def _audit_reviewed_number_families(
    readings: list[CellReading],
    cells_by_position: dict[tuple[int, int], np.ndarray],
    *,
    excluded_puzzle_id: int | None = None,
) -> list[CellReading]:
    """Revoke trust when reviewed examples dispute a known OCR ambiguity."""

    families = (frozenset((6, 8, 16, 18)), frozenset((9, 19)))
    reviewed = []
    for reading in readings:
        cell = cells_by_position[(reading.row, reading.column)]
        reading = _adjudicate_nine_nineteen(
            reading,
            cell,
            excluded_puzzle_id=excluded_puzzle_id,
        )
        if not reading.trusted or not reading.text.isdigit():
            reviewed.append(reading)
            continue
        value = int(reading.text)
        family = next((item for item in families if value in item), None)
        if family is None:
            reviewed.append(reading)
            continue
        assessment = _reviewed_number_assessment(
            cells_by_position[(reading.row, reading.column)],
            family,
            excluded_puzzle_id=excluded_puzzle_id,
        )
        vote, margin = assessment if assessment is not None else (None, 1.0)
        token_arities = {
            len(_digit_glyphs(cell)),
            len(_digit_glyphs(cell, suppress_illumination=True)),
        }
        arity_agrees = len(token_arities) == 1 and 0 not in token_arities
        arity_matches = not arity_agrees or token_arities == {len(reading.text)}
        quadrant_vote = (
            _reviewed_six_eight_quadrant_vote(cell, excluded_puzzle_id=excluded_puzzle_id)
            if value in {6, 8} and token_arities == {1}
            else None
        )
        quadrant_matches = quadrant_vote is None or quadrant_vote == value
        reviewed.append(
            CellReading(
                row=reading.row,
                column=reading.column,
                text=reading.text,
                confidence=reading.confidence,
                trusted=(vote is None or vote == value)
                and margin >= MIN_REVIEWED_FAMILY_MARGIN
                and arity_matches
                and quadrant_matches,
            )
        )
    return reviewed


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


def _template_value(cell: np.ndarray, templates: dict[int, np.ndarray]) -> int | None:
    feature = _number_feature(cell).astype(np.float32)
    if np.all(feature == 255):
        return None
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

    binary = _number_ink_mask(cell, suppress_illumination=suppress_illumination)
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
    if digit == "8" and "6" in top_two and max(counters) <= 1:
        return "6"
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


def _adjudicate_clue_topology(cleaned: np.ndarray, clue: str | None) -> str | None:
    """Correct OCR readings contradicted by simple printed-glyph topology."""

    points = np.argwhere(cleaned < 128)
    if len(points):
        y_min, x_min = points.min(axis=0)
        y_max, x_max = points.max(axis=0)
        width = int(x_max - x_min + 1)
        height = int(y_max - y_min + 1)
        if height >= 25 and width / height <= 0.25:
            return "I"
    if clue != "A":
        return clue
    ink = 255 - cleaned
    counters = tuple(_enclosed_counter_count(ink, size) for size in (0, 2, 3, 4))
    return "X" if max(counters) == 0 else clue


def clue_ink_pixels(cell: np.ndarray) -> int:
    """Measure printed clue-letter foreground away from borders and numbers."""

    region = cell[30:92, 8:92]
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    return int(np.count_nonzero(_foreground_binary(gray)))


def extract_clues(
    reference_grid: np.ndarray,
    work_dir: Path,
    evidence: list[ClueEvidence] | None = None,
) -> dict[int, str]:
    """Read the large printed letters from the numbered reference cells."""

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
            if height >= 25 and 4 <= width <= 70 and area >= 100:
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
        clue = _adjudicate_clue_topology(cleaned, _select_clue(attempts))
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
    counts = Counter(clues.values())
    return {symbol: letter for symbol, letter in clues.items() if counts[letter] == 1}


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


def _write_grid_diagnostics(work_dir: Path, corner_warp: np.ndarray, grid: np.ndarray, grid_size: int) -> None:
    """Save the pre-crop stages and draw the exact sampling windows."""

    cv2.imwrite(str(work_dir / "grid-corner-warp.png"), corner_warp)
    overlay = grid.copy()
    rows = _cell_edges(grid.shape[0], grid_size).tolist()
    columns = _cell_edges(grid.shape[1], grid_size).tolist()
    for row, (top, bottom) in enumerate(zip(rows[:-1], rows[1:], strict=True), 1):
        for column, (left, right) in enumerate(zip(columns[:-1], columns[1:], strict=True), 1):
            cv2.rectangle(overlay, (left, top), (right - 1, bottom - 1), (240, 210, 0), 1)
            start, stop, _ = _number_region((bottom - top, right - left)).indices(min(bottom - top, right - left))
            cv2.rectangle(overlay, (left + start, top + start), (left + stop - 1, top + stop - 1), (0, 165, 255), 1)
            cv2.putText(
                overlay,
                f"{row:02}/{column:02}",
                (left + 7, bottom - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (240, 210, 0),
                1,
                cv2.LINE_AA,
            )
    cv2.imwrite(str(work_dir / "grid-crop-overlay.png"), overlay)


def recognize_photo(
    source: Path,
    work_dir: Path,
    *,
    trace: RecognitionTrace | None = None,
    template_exclusion: int | None = None,
    ocr_pipeline: str = TESSERACT_PIPELINE,
    geometry_debug: bool = False,
    grid_mesh: bool = True,
) -> PuzzleObservation:
    """Convert a supported square photographed puzzle into a conservative observation."""

    if ocr_pipeline not in OCR_PIPELINES:
        raise ValueError(f"Unknown OCR pipeline: {ocr_pipeline}")
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
    if geometry_debug or grid_mesh:
        padding = WARP_SIZE // 20
        image, padded_grid = _orient_photo_grid(image, padding=padding)
        board = slice(padding, padding + WARP_SIZE)
        extracted_grid = padded_grid[board, board]
    else:
        image, extracted_grid = _orient_photo_grid(image)
    grid_size = detect_grid_size(extracted_grid)
    if grid_mesh:
        vertices = _grid_vertices(padded_grid, grid_size, padding)
        grid_image = _dewarp_vertex_mesh(padded_grid, vertices)
    else:
        grid_image = normalize_grid_lattice(extracted_grid, grid_size)
    cv2.imwrite(str(work_dir / "grid.png"), grid_image)
    if trace is not None:
        trace.record("grid", started)
    if geometry_debug:
        _write_grid_diagnostics(work_dir, extracted_grid, grid_image, grid_size)
        cv2.imwrite(str(work_dir / "grid-padded-warp.png"), padded_grid)
        annotated = padded_grid.copy()
        edge = padding + WARP_SIZE - 1
        cv2.rectangle(annotated, (padding, padding), (edge, edge), (255, 174, 0), 2)
        cv2.imwrite(str(work_dir / "grid-padded-outline.png"), annotated)
        if not grid_mesh:
            vertices = _grid_vertices(padded_grid, grid_size, padding)
        mesh = padded_grid.copy()
        points = np.rint(vertices).astype(np.int32)
        for row, column in zip(points, np.swapaxes(points, 0, 1), strict=True):
            cv2.polylines(mesh, [row, np.ascontiguousarray(column)], False, (255, 210, 0), 1, cv2.LINE_AA)
        for x, y in points.reshape(-1, 2).tolist():
            cv2.circle(mesh, (x, y), 3, (0, 180, 255), -1, cv2.LINE_AA)
        cv2.imwrite(str(work_dir / "grid-vertex-mesh.png"), mesh)
        cv2.imwrite(
            str(work_dir / "grid-mesh-dewarped.png"),
            grid_image if grid_mesh else _dewarp_vertex_mesh(padded_grid, vertices),
        )

    # The packaged number banks were built for the original 15×15 book.
    use_templates = grid_size == GRID_SIZE and ocr_pipeline != TESSERACT_PIPELINE
    templates = None
    digit_templates = None
    started = time.perf_counter()
    try:
        reference_grid = extract_reference_grid(image)
    except ValueError:
        clues: dict[int, str] = {}
        clue_evidence: list[ClueEvidence] = []
    else:
        cv2.imwrite(str(work_dir / "reference-grid.png"), reference_grid)
        if use_templates:
            templates = _reference_templates(reference_grid)
            try:
                digit_templates = _digit_templates(reference_grid)
            except ValueError:
                pass
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
    if use_templates and digit_templates is not None:
        classification_stage = time.perf_counter()
        if ocr_pipeline == WHOLE_TOKEN_PIPELINE:
            prototypes, prototype_labels = _whole_number_templates(template_exclusion)
            with ThreadPoolExecutor(max_workers=8) as executor:
                readings = list(
                    executor.map(
                        lambda cell: _classify_whole_number(cell, prototypes, prototype_labels),
                        playable,
                    )
                )
            if trace is not None:
                trace.record("classify.whole-token", classification_stage)
            unresolved = [reading for reading in readings if not reading.trusted]
            if unresolved:
                cells_by_position = {(row, column): cell for row, column, cell in playable}
                reconsidered = [
                    _classify_from_reference(
                        (item.row, item.column, cells_by_position[(item.row, item.column)]),
                        work_dir,
                        digit_templates,
                    )
                    for item in unresolved
                ]
                replacements = {
                    (item.row, item.column): item
                    for item in reconsidered
                    if item.trusted
                    and item.text
                    == next(
                        original.text
                        for original in unresolved
                        if (original.row, original.column) == (item.row, item.column)
                    )
                }
                readings = [replacements.get((item.row, item.column), item) for item in readings]
        else:
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
        second_pass = (
            [reading for reading in readings if not reading.trusted] if ocr_pipeline == LEGACY_PIPELINE else []
        )
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
        for _ in range(2 if ocr_pipeline == LEGACY_PIPELINE else 0):
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
        if ocr_pipeline == LEGACY_PIPELINE:
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
    cells_by_position = {(row, column): cell for row, column, cell in playable}
    if use_templates and ocr_pipeline == WHOLE_TOKEN_PIPELINE:
        # Give disputed template readings an OCR pass before they can become unknowns.
        readings = _audit_reviewed_number_families(
            readings,
            cells_by_position,
            excluded_puzzle_id=template_exclusion,
        )
    retry = [
        reading
        for reading in readings
        if not reading.trusted
        and (
            use_templates
            or not reading.text.isdigit()
            or not 1 <= int(reading.text) <= 26
            or reading.confidence < MIN_OCR_CONFIDENCE
        )
    ]
    if retry:
        classification_stage = time.perf_counter()
        first_ocr = retry
        if use_templates:
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
                            if use_templates and templates is not None
                            else None
                        ),
                        cells_by_position[(item.row, item.column)],
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
        if use_templates and ocr_pipeline == WHOLE_TOKEN_PIPELINE:
            retried = [
                (
                    item
                    if item.text == original_by_position[(item.row, item.column)].text
                    or (
                        not first.text
                        and item.text.isdigit()
                        and 1 <= int(item.text) <= 26
                        and item.confidence >= MIN_OCR_CONFIDENCE
                        # A blank first read cannot corroborate dropping a digit.
                        and len(item.text) >= len(original_by_position[(item.row, item.column)].text)
                    )
                    else original_by_position[(item.row, item.column)]
                )
                for first, item in zip(first_ocr, retried, strict=True)
            ]
        replacements = {(item.row, item.column): item for item in retried}
        readings = [replacements.get((item.row, item.column), item) for item in readings]
        if trace is not None:
            trace.record("classify.tesseract", classification_stage)

    if use_templates and templates is not None and ocr_pipeline == LEGACY_PIPELINE:
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
    cells_by_position = {(row, column): cell for row, column, cell in playable}
    if use_templates:
        readings = _audit_reviewed_number_families(
            readings,
            cells_by_position,
            excluded_puzzle_id=template_exclusion,
        )
    else:
        readings = [
            CellReading(
                row=item.row,
                column=item.column,
                text=item.text,
                confidence=item.confidence,
                trusted=(item.text.isdigit() and 1 <= int(item.text) <= 26 and item.confidence >= MIN_OCR_CONFIDENCE),
            )
            for item in readings
        ]
        readings = _review_with_scan_matches(readings, cells_by_position)
    for reading in readings:
        if not reading.trusted:
            cv2.imwrite(
                str(work_dir / f"cell-{reading.row + 1}-{reading.column + 1}.png"),
                cells_by_position[(reading.row, reading.column)],
            )
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
