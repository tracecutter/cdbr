"""Tests for illumination-tolerant photograph recognition helpers."""

import cv2
import numpy as np

from cdbr.core.recognition import (
    _block_mask,
    _cell_images,
    _coarse_glyph_feature,
    _digit_glyphs,
    _foreground_binary,
    _relative_margin,
    _select_clue,
    detect_grid_size,
)


def test_grid_geometry_adapts_to_supported_square_sizes() -> None:
    for grid_size in (13, 15):
        grid = np.full((1500, 1500, 3), 245, dtype=np.uint8)
        for position in np.linspace(0, 1499, grid_size + 1).round().astype(int):
            cv2.line(grid, (position, 0), (position, 1499), (0, 0, 0), 3)
            cv2.line(grid, (0, position), (1499, position), (0, 0, 0), 3)

        assert detect_grid_size(grid) == grid_size
        assert len(_cell_images(grid, grid_size)) == grid_size**2


def test_foreground_binary_rejects_smooth_shadow() -> None:
    image = np.full((100, 160), 235, dtype=np.uint8)
    image[:, :90] -= 80
    image = cv2.GaussianBlur(image, (31, 31), 0)
    cv2.putText(image, "14", (50, 65), cv2.FONT_HERSHEY_SIMPLEX, 1.5, 20, 3, cv2.LINE_AA)

    foreground = _foreground_binary(image)

    assert np.mean(foreground[35:70, 50:105]) > 20
    assert np.mean(foreground[:, :30]) < 5
    assert np.mean(foreground[:, 130:]) < 5


def test_coarse_glyph_feature_preserves_six_tail() -> None:
    zero = np.zeros((48, 32), dtype=np.uint8)
    cv2.ellipse(zero, (16, 27), (9, 15), 0, 0, 360, 255, 4)
    six = zero.copy()
    cv2.line(six, (8, 27), (10, 5), 255, 4)

    zero_feature = _coarse_glyph_feature(zero)
    six_feature = _coarse_glyph_feature(six)

    assert six_feature[4] > zero_feature[4]
    assert not np.array_equal(six_feature, zero_feature)


def test_block_mask_tolerates_page_brightness_gradient() -> None:
    expected = [(row + column) % 4 == 1 for row in range(15) for column in range(15)]
    cells = []
    for index, blocked in enumerate(expected):
        row, column = divmod(index, 15)
        paper = 230 - 5 * row
        brightness = round(paper * 0.6) if blocked else paper
        cells.append((row, column, np.full((100, 100, 3), brightness, dtype=np.uint8)))

    assert _block_mask(cells) == expected


def test_digit_glyphs_reassembles_fragmented_one() -> None:
    cell = np.full((100, 100, 3), 255, dtype=np.uint8)
    cv2.rectangle(cell, (15, 10), (26, 23), (0, 0, 0), -1)
    cv2.rectangle(cell, (21, 30), (26, 36), (0, 0, 0), -1)
    cv2.putText(cell, "9", (38, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    assert len(_digit_glyphs(cell)) == 2


def test_select_clue_prefers_agreement_across_ocr_modes() -> None:
    assert _select_clue(["", "PO", "P"]) == "P"
    assert _select_clue(["", "OP", ""]) == "P"
    assert _select_clue(["", "BB", "B"]) == "B"


def test_relative_margin_handles_identical_perfect_matches() -> None:
    assert _relative_margin(0.0, 0.0) == 0.0
    assert _relative_margin(10.0, 20.0) == 0.5
