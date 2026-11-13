"""Plain-text and photographic presentation of solved puzzles."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cdbr.core.model import CodewordPuzzle
from cdbr.core.recognition import (
    GRID_SIZE,
    WARP_SIZE,
    _grid_line_positions,
    find_grid_corners,
    find_reference_corners,
    normalize_photo,
)

_FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf"),
    Path("/System/Library/Fonts/Noteworthy.ttc"),
    Path("/System/Library/Fonts/MarkerFelt.ttc"),
    Path("/Library/Fonts/Comic Sans MS.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


def solution_rows(puzzle: CodewordPuzzle, mapping: dict[int, str]) -> tuple[str, ...]:
    """Render the mundane one-character-per-cell solution."""

    return tuple("".join("#" if symbol is None else mapping.get(symbol, "?") for symbol in row) for row in puzzle.grid)


def _measured_lines(grid: np.ndarray) -> tuple[list[int], list[int]]:
    gray = cv2.cvtColor(grid, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    fallback = [round(index * (WARP_SIZE - 1) / GRID_SIZE) for index in range(GRID_SIZE + 1)]
    return (
        _grid_line_positions(binary, vertical=True) or fallback,
        _grid_line_positions(binary, vertical=False) or fallback,
    )


@lru_cache(maxsize=16)
def _handwriting_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if path.exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _letter_layer(
    size: tuple[int, int],
    cells: Sequence[tuple[str, float, float, int]],
) -> tuple[np.ndarray, np.ndarray]:
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for letter, x, y, font_size in cells:
        draw.text(
            (x, y),
            letter,
            font=_handwriting_font(font_size),
            fill=(20, 55, 150, 230),
            anchor="mm",
        )
    rgba = np.asarray(canvas)
    return cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2BGR), rgba[:, :, 3]


def _project_layer(
    ink: np.ndarray,
    mask: np.ndarray,
    source_corners: np.ndarray,
    destination_corners: np.ndarray,
    output_size: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    transform = cv2.getPerspectiveTransform(source_corners, destination_corners)
    return (
        cv2.warpPerspective(ink, transform, output_size),
        cv2.warpPerspective(mask, transform, output_size),
    )


def write_solution_photo(
    source: Path,
    destination: Path,
    puzzle: CodewordPuzzle,
    mapping: dict[int, str],
    work_dir: Path,
) -> None:
    """Inverse-project handwritten answers onto the original photograph."""

    original_path = work_dir / "presentation-source.png"
    normalize_photo(source, original_path, maximum_size=None)
    original = cv2.imread(str(original_path))
    if original is None:
        raise ValueError(f"Could not decode photograph for presentation: {source}")

    corners = find_grid_corners(original)
    canonical_corners = np.array(
        [
            [0, 0],
            [WARP_SIZE - 1, 0],
            [WARP_SIZE - 1, WARP_SIZE - 1],
            [0, WARP_SIZE - 1],
        ],
        dtype=np.float32,
    )
    forward = cv2.getPerspectiveTransform(corners, canonical_corners)
    rectified = cv2.warpPerspective(original, forward, (WARP_SIZE, WARP_SIZE))
    x_lines, y_lines = _measured_lines(rectified)

    board_cells: list[tuple[str, float, float, int]] = []
    for row in range(GRID_SIZE):
        for column in range(GRID_SIZE):
            symbol = puzzle.grid[row][column]
            if symbol is None or symbol not in mapping:
                continue
            letter = mapping[symbol]
            left, right = x_lines[column], x_lines[column + 1]
            top, bottom = y_lines[row], y_lines[row + 1]
            cell_height = bottom - top
            board_cells.append(
                (
                    letter,
                    (left + right) / 2,
                    top + cell_height * 0.68,
                    max(22, round(cell_height * 0.54)),
                )
            )

    ink, mask = _letter_layer((WARP_SIZE, WARP_SIZE), board_cells)

    output_size = (original.shape[1], original.shape[0])
    projected_ink, projected_mask = _project_layer(ink, mask, canonical_corners, corners, output_size)

    reference_cells = [
        (
            letter,
            ((symbol - 1) % 13) * 100 + 50,
            (0 if symbol <= 13 else 100) + 68,
            45,
        )
        for symbol, letter in sorted(mapping.items())
        if 1 <= symbol <= 26 and symbol not in puzzle.clues
    ]
    reference_ink, reference_mask = _letter_layer((1300, 200), reference_cells)
    reference_source = np.array([[0, 0], [1299, 0], [1299, 199], [0, 199]], dtype=np.float32)
    reference_corners = find_reference_corners(original)
    projected_reference_ink, projected_reference_mask = _project_layer(
        reference_ink,
        reference_mask,
        reference_source,
        reference_corners,
        output_size,
    )
    reference_pixels = projected_reference_mask > projected_mask
    projected_ink[reference_pixels] = projected_reference_ink[reference_pixels]
    projected_mask = np.maximum(projected_mask, projected_reference_mask)

    alpha = (projected_mask.astype(np.float32) / 255.0)[..., None]
    composed = (original.astype(np.float32) * (1.0 - alpha) + projected_ink.astype(np.float32) * alpha).astype(np.uint8)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.suffix.lower() in {".heic", ".heif"}:
        intermediate = work_dir / "solution-output.png"
        if not cv2.imwrite(str(intermediate), composed):
            raise ValueError(f"Could not prepare solution image: {destination}")
        result = subprocess.run(
            ["magick", str(intermediate), str(destination)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            detail = result.stderr.strip() or "ImageMagick conversion failed"
            raise ValueError(f"Could not write solution image: {destination}: {detail}")
    elif not cv2.imwrite(str(destination), composed):
        raise ValueError(f"Could not write solution image: {destination}")
