"""Photograph normalization, grid extraction, and conservative cell OCR."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import subprocess
from collections import Counter

import cv2
import numpy as np

from cdbr.core.photo import detect_photo_format
from cdbr.core.puzzle import BLOCK, UNKNOWN, CellUncertainty, PuzzleObservation


GRID_SIZE = 15
WARP_SIZE = 1500
CELL_SIZE = WARP_SIZE // GRID_SIZE
MIN_OCR_CONFIDENCE = 80.0
MIN_TEMPLATE_MARGIN = 0.15


@dataclass(frozen=True, kw_only=True)
class CellReading:
    row: int
    column: int
    text: str
    confidence: float
    trusted: bool = False


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise ValueError(f"Required image tool is not installed: {command[0]}") from None
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip() or "unknown error"
        raise ValueError(f"{command[0]} failed: {detail}") from None


def normalize_photo(source: Path, destination: Path) -> None:
    """Decode a photograph into an orientation-corrected working PNG."""

    _run(
        [
            "magick",
            str(source),
            "-auto-orient",
            "-resize",
            "1600x1600>",
            str(destination),
        ]
    )


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


def extract_grid(image: np.ndarray) -> np.ndarray:
    """Locate the near-square puzzle grid and rectify its perspective."""

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

    corners = _ordered_corners(max(candidates, key=lambda candidate: candidate[0])[1])
    destination = np.array(
        [[0, 0], [WARP_SIZE - 1, 0], [WARP_SIZE - 1, WARP_SIZE - 1], [0, WARP_SIZE - 1]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(corners, destination)
    return cv2.warpPerspective(image, transform, (WARP_SIZE, WARP_SIZE))


def _grid_line_positions(binary: np.ndarray, *, vertical: bool) -> list[int] | None:
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40) if vertical else (40, 1))
    lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    scores = lines.sum(axis=0 if vertical else 1)
    positions: list[int] = []
    for index in range(GRID_SIZE + 1):
        expected = round(index * (WARP_SIZE - 1) / GRID_SIZE)
        low = max(0, expected - 25)
        high = min(WARP_SIZE, expected + 26)
        positions.append(low + int(np.argmax(scores[low:high])))
    gaps = np.diff(positions)
    if np.any(gaps < 85) or np.any(gaps > 115) or float(np.std(gaps)) >= 5.0:
        return None
    return positions


def normalize_grid_lattice(grid: np.ndarray) -> np.ndarray:
    """Map measured internal grid lines onto an exact square lattice."""

    gray = cv2.cvtColor(grid, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    x_positions = _grid_line_positions(binary, vertical=True)
    y_positions = _grid_line_positions(binary, vertical=False)
    target = np.linspace(0, WARP_SIZE - 1, GRID_SIZE + 1)
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


def _cell_images(grid: np.ndarray) -> list[tuple[int, int, np.ndarray]]:
    return [
        (
            row,
            column,
            grid[
                row * CELL_SIZE : (row + 1) * CELL_SIZE,
                column * CELL_SIZE : (column + 1) * CELL_SIZE,
            ],
        )
        for row in range(GRID_SIZE)
        for column in range(GRID_SIZE)
    ]


def _block_mask(cells: list[tuple[int, int, np.ndarray]]) -> list[bool]:
    medians = np.array([np.median(cell[15:92, 15:92]) for _, _, cell in cells], dtype=np.uint8)
    threshold, _ = cv2.threshold(medians, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return [bool(median <= threshold) for median in medians]


def _clean_number(cell: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    region = gray[5:70, 5:70]
    binary = cv2.threshold(region, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    count, labels, statistics, _ = cv2.connectedComponentsWithStats(binary)
    cleaned = np.full_like(binary, 255)
    for index in range(1, count):
        x, y, width, height, area = statistics[index]
        if 5 <= width <= 25 and 15 <= height <= 42 and 50 <= area <= 500:
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


def extract_reference_grid(image: np.ndarray) -> np.ndarray:
    """Locate and rectify the two-row 1–26 reference strip."""

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
    corners = _ordered_corners(max(candidates, key=lambda candidate: candidate[0])[1])
    destination = np.array([[0, 0], [1299, 0], [1299, 199], [0, 199]], dtype=np.float32)
    transform = cv2.getPerspectiveTransform(corners, destination)
    return cv2.warpPerspective(image, transform, (1300, 200))


def _number_feature(cell: np.ndarray) -> np.ndarray:
    cleaned = _clean_number(cell)
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


def _digit_glyphs(cell: np.ndarray) -> list[np.ndarray]:
    """Segment one or two glyphs, including digits joined by thresholding."""

    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    region = gray[5:70, 5:70]
    binary = cv2.threshold(region, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    count, labels, statistics, _ = cv2.connectedComponentsWithStats(binary)
    glyphs: list[tuple[int, np.ndarray]] = []
    for index in range(1, count):
        x, y, width, height, area = statistics[index]
        if not (5 <= width <= 48 and 15 <= height <= 42 and 50 <= area <= 800):
            continue
        mask = (labels[y : y + height, x : x + width] == index).astype(np.uint8) * 255
        chunks = [(x, mask)]
        if width > 26:
            projection = np.sum(mask > 0, axis=0)
            low = int(width * 0.3)
            high = int(width * 0.7)
            split = low + int(np.argmin(projection[low : high + 1]))
            chunks = [(x, mask[:, :split]), (x + split, mask[:, split:])]
        for position, glyph in chunks:
            glyph = cv2.copyMakeBorder(glyph, 3, 3, 3, 3, cv2.BORDER_CONSTANT, value=0)
            glyph = cv2.resize(glyph, (32, 48), interpolation=cv2.INTER_NEAREST)
            glyphs.append((position, glyph))
    return [glyph for _, glyph in sorted(glyphs, key=lambda item: item[0])]


def _digit_templates(reference_grid: np.ndarray) -> dict[str, list[np.ndarray]]:
    templates: dict[str, list[np.ndarray]] = {str(digit): [] for digit in range(10)}
    for value in range(1, 27):
        row = 0 if value <= 13 else 1
        column = (value - 1) % 13
        cell = reference_grid[
            row * 100 : (row + 1) * 100,
            column * 100 : (column + 1) * 100,
        ].copy()
        cell[43:] = 255  # Exclude supplied clue letters below the printed number.
        glyphs = _digit_glyphs(cell)
        if len(glyphs) != len(str(value)):
            continue
        for digit, glyph in zip(str(value), glyphs, strict=True):
            templates[digit].append(glyph)
    if any(not samples for samples in templates.values()):
        raise ValueError("Reference grid did not provide templates for every digit")
    return templates


def _classify_from_reference(
    item: tuple[int, int, np.ndarray],
    work_dir: Path,
    templates: dict[str, list[np.ndarray]],
    minimum_margin: float = MIN_TEMPLATE_MARGIN,
) -> CellReading:
    row, column, cell = item
    cv2.imwrite(str(work_dir / f"cell-{row + 1}-{column + 1}.png"), _clean_number(cell))
    glyphs = _digit_glyphs(cell)
    if not 1 <= len(glyphs) <= 2:
        return CellReading(row=row, column=column, text="", confidence=0.0)
    digits: list[str] = []
    margins: list[float] = []
    for glyph in glyphs:
        glyph_float = glyph.astype(np.float32)
        scores = sorted(
            (
                min(float(np.mean((glyph_float - sample.astype(np.float32)) ** 2)) for sample in samples),
                digit,
            )
            for digit, samples in templates.items()
        )
        best_score, digit = scores[0]
        second_score = scores[1][0]
        margin = (second_score - best_score) / second_score if second_score else 0.0
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


def create_review_sheet(
    grid_image: np.ndarray,
    uncertainties: list[CellUncertainty],
    work_dir: Path,
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
        original = grid_image[
            row * CELL_SIZE : (row + 1) * CELL_SIZE,
            column * CELL_SIZE : (column + 1) * CELL_SIZE,
        ]
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


def recognize_photo(source: Path, work_dir: Path) -> PuzzleObservation:
    """Convert a photographed 15×15 puzzle into a conservative observation."""

    normalized_path = work_dir / "normalized.png"
    normalize_photo(source, normalized_path)
    image = cv2.imread(str(normalized_path))
    if image is None:
        raise ValueError(f"Could not decode photograph: {source}")
    grid_image = normalize_grid_lattice(extract_grid(image))
    cv2.imwrite(str(work_dir / "grid.png"), grid_image)
    try:
        reference_grid = extract_reference_grid(image)
    except ValueError:
        templates = None
        digit_templates = None
    else:
        cv2.imwrite(str(work_dir / "reference-grid.png"), reference_grid)
        templates = _reference_templates(reference_grid)
        digit_templates = _digit_templates(reference_grid)

    cells = _cell_images(grid_image)
    blocks = _block_mask(cells)
    playable = [cell for cell, blocked in zip(cells, blocks, strict=True) if not blocked]
    if digit_templates is not None:
        with ThreadPoolExecutor(max_workers=8) as executor:
            readings = list(
                executor.map(
                    lambda cell: _classify_from_reference(cell, work_dir, digit_templates),
                    playable,
                )
            )
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
    else:
        with ThreadPoolExecutor(max_workers=8) as executor:
            readings = list(executor.map(lambda cell: _read_cell(cell, work_dir), playable))
    retry = [reading for reading in readings if not reading.trusted]
    if retry:
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
    readings_by_position = {(item.row, item.column): item for item in readings}

    rows: list[tuple[int | str, ...]] = []
    uncertainties: list[CellUncertainty] = []
    for row in range(GRID_SIZE):
        values: list[int | str] = []
        for column in range(GRID_SIZE):
            index = row * GRID_SIZE + column
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

    create_review_sheet(grid_image, uncertainties, work_dir)
    photo_format = detect_photo_format(source)
    return PuzzleObservation(
        source=source,
        source_format=photo_format.display_name,
        grid=tuple(rows),
        clues={},
        uncertainties=tuple(uncertainties),
    )
