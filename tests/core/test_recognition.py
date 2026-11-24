"""Tests for illumination-tolerant photograph recognition helpers."""

from pathlib import Path

import cv2
import numpy as np

from cdbr.core.recognition import (
    CellReading,
    _adjudicate_clue_topology,
    _adjudicate_counter_family,
    _adjudicate_nine_nineteen,
    _block_mask,
    _cell_images,
    _coarse_glyph_feature,
    _classify_whole_number,
    _digit_glyphs,
    _foreground_binary,
    _relative_margin,
    _number_feature,
    _reviewed_number_vote,
    _select_clue,
    clue_ink_pixels,
    detect_grid_size,
    needs_hil_review,
    recognize_photo,
)


def test_hil_review_keeps_low_margin_counter_family_readings_visible() -> None:
    assert needs_hil_review(CellReading(row=1, column=1, text="6", confidence=67.9, trusted=True))
    assert not needs_hil_review(CellReading(row=1, column=1, text="6", confidence=68.0, trusted=True))
    assert not needs_hil_review(CellReading(row=1, column=1, text="23", confidence=60.0, trusted=True))
    assert needs_hil_review(CellReading(row=1, column=1, text="23", confidence=90.0, trusted=False))


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


def test_clue_ink_measure_ignores_a_clean_cell_but_keeps_handwriting() -> None:
    blank = np.full((100, 100, 3), 245, dtype=np.uint8)
    written = blank.copy()
    cv2.putText(written, "A", (25, 82), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (20, 20, 20), 5, cv2.LINE_AA)

    assert clue_ink_pixels(blank) < 400
    assert clue_ink_pixels(written) >= 400


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


def test_clue_topology_separates_a_from_x() -> None:
    letter_a = np.full((80, 80), 255, dtype=np.uint8)
    letter_x = letter_a.copy()
    cv2.putText(letter_a, "A", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 2.0, 0, 7, cv2.LINE_AA)
    cv2.putText(letter_x, "X", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 2.0, 0, 7, cv2.LINE_AA)

    assert _adjudicate_clue_topology(letter_a, "A") == "A"
    assert _adjudicate_clue_topology(letter_x, "A") == "X"


def test_clue_topology_recognises_narrow_i_after_ocr_miss() -> None:
    letter_i = np.full((80, 80), 255, dtype=np.uint8)
    cv2.rectangle(letter_i, (37, 15), (43, 65), 0, -1)

    assert _adjudicate_clue_topology(letter_i, None) == "I"
    assert _adjudicate_clue_topology(letter_i, "O") == "I"


def test_relative_margin_handles_identical_perfect_matches() -> None:
    assert _relative_margin(0.0, 0.0) == 0.0
    assert _relative_margin(10.0, 20.0) == 0.5


def test_counter_family_adjudicator_ignores_unrelated_digits() -> None:
    glyph = np.zeros((48, 32), dtype=np.uint8)

    assert _adjudicate_counter_family(glyph, "4", [(1.0, "4"), (2.0, "5")]) == "4"


def test_counter_family_adjudicator_demotes_one_counter_eight_to_six() -> None:
    glyph = np.zeros((48, 32), dtype=np.uint8)
    cv2.ellipse(glyph, (16, 30), (9, 11), 0, 0, 360, 255, 4)
    cv2.line(glyph, (8, 30), (12, 7), 255, 4)

    assert _adjudicate_counter_family(glyph, "8", [(1.0, "8"), (1.1, "6")]) == "6"


def test_reviewed_number_vote_respects_puzzle_exclusion(monkeypatch) -> None:
    cell = np.full((100, 100, 3), 255, dtype=np.uint8)
    cv2.putText(cell, "6", (8, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.1, 0, 3, cv2.LINE_AA)
    feature = cv2.resize(_number_feature(cell), (20, 30), interpolation=cv2.INTER_AREA)
    features = np.stack((feature, feature, feature, 255 - feature))
    labels = np.array((6, 6, 6, 8), dtype=np.uint8)
    puzzle_ids = np.array((37, 37, 38, 39), dtype=np.uint8)
    monkeypatch.setattr(
        "cdbr.core.recognition._reviewed_number_templates",
        lambda: (features, labels, puzzle_ids),
    )

    assert _reviewed_number_vote(cell, frozenset((6, 8))) == 6
    assert _reviewed_number_vote(cell, frozenset((6, 8)), excluded_puzzle_id=37) == 6


def test_whole_token_pipeline_keeps_reviewed_family_audit_enabled(monkeypatch) -> None:
    from cdbr.core.recognition import CellReading, _audit_reviewed_number_families

    cell = np.full((100, 100, 3), 255, dtype=np.uint8)
    monkeypatch.setattr("cdbr.core.recognition._reviewed_number_assessment", lambda *_args, **_kwargs: (8, 0.9))

    audited = _audit_reviewed_number_families(
        [CellReading(row=0, column=0, text="6", confidence=95.0, trusted=True)],
        {(0, 0): cell},
    )

    assert audited[0].text == "6"
    assert audited[0].trusted is False


def test_reviewed_family_audit_revokes_weak_agreement(monkeypatch) -> None:
    from cdbr.core.recognition import CellReading, _audit_reviewed_number_families

    cell = np.full((100, 100, 3), 255, dtype=np.uint8)
    monkeypatch.setattr("cdbr.core.recognition._reviewed_number_assessment", lambda *_args, **_kwargs: (6, 0.08))

    audited = _audit_reviewed_number_families(
        [CellReading(row=0, column=0, text="6", confidence=90.0, trusted=True)],
        {(0, 0): cell},
    )

    assert audited[0].trusted is False


def test_reviewed_family_audit_revokes_token_arity_disagreement(monkeypatch) -> None:
    from cdbr.core.recognition import CellReading, _audit_reviewed_number_families

    cell = np.full((100, 100, 3), 255, dtype=np.uint8)
    monkeypatch.setattr("cdbr.core.recognition._reviewed_number_assessment", lambda *_args, **_kwargs: (6, 0.9))
    monkeypatch.setattr(
        "cdbr.core.recognition._digit_glyphs",
        lambda *_args, **_kwargs: [np.zeros((2, 2)), np.zeros((2, 2))],
    )

    audited = _audit_reviewed_number_families(
        [CellReading(row=0, column=0, text="6", confidence=90.0, trusted=True)],
        {(0, 0): cell},
    )

    assert audited[0].trusted is False


def test_reviewed_family_audit_revokes_extreme_quadrant_disagreement(monkeypatch) -> None:
    from cdbr.core.recognition import CellReading, _audit_reviewed_number_families

    cell = np.full((100, 100, 3), 255, dtype=np.uint8)
    monkeypatch.setattr("cdbr.core.recognition._reviewed_number_assessment", lambda *_args, **_kwargs: (6, 0.9))
    monkeypatch.setattr("cdbr.core.recognition._digit_glyphs", lambda *_args, **_kwargs: [np.zeros((2, 2))])
    monkeypatch.setattr("cdbr.core.recognition._reviewed_six_eight_quadrant_vote", lambda *_args, **_kwargs: 8)

    audited = _audit_reviewed_number_families(
        [CellReading(row=0, column=0, text="6", confidence=90.0, trusted=True)],
        {(0, 0): cell},
    )

    assert audited[0].trusted is False


def test_nine_nineteen_adjudicator_removes_false_leading_one(monkeypatch) -> None:
    cell = np.full((100, 100, 3), 255, dtype=np.uint8)
    reading = CellReading(row=2, column=3, text="19", confidence=54.0, trusted=False)
    monkeypatch.setattr(
        "cdbr.core.recognition._digit_glyphs",
        lambda *_args, **_kwargs: [np.zeros((2, 2))],
    )
    monkeypatch.setattr(
        "cdbr.core.recognition._reviewed_number_assessment",
        lambda *_args, **_kwargs: (9, 0.24),
    )
    monkeypatch.setattr("cdbr.core.recognition._number_ink_pixels", lambda _cell: 400)

    corrected = _adjudicate_nine_nineteen(reading, cell)

    assert corrected.text == "9"
    assert corrected.trusted is True
    assert not needs_hil_review(corrected)


def test_nine_nineteen_adjudicator_keeps_heavy_borderline_nineteen(monkeypatch) -> None:
    cell = np.full((100, 100, 3), 255, dtype=np.uint8)
    reading = CellReading(row=2, column=3, text="19", confidence=72.0, trusted=True)
    monkeypatch.setattr(
        "cdbr.core.recognition._digit_glyphs",
        lambda *_args, **_kwargs: [np.zeros((2, 2))],
    )
    monkeypatch.setattr(
        "cdbr.core.recognition._reviewed_number_assessment",
        lambda *_args, **_kwargs: (9, 0.24),
    )
    monkeypatch.setattr("cdbr.core.recognition._number_ink_pixels", lambda _cell: 520)

    assert _adjudicate_nine_nineteen(reading, cell) == reading


def test_whole_number_classifier_uses_complete_token_margin() -> None:
    cell = np.full((100, 100, 3), 255, dtype=np.uint8)
    cv2.putText(cell, "16", (8, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.1, 0, 3, cv2.LINE_AA)
    feature = cv2.resize(_number_feature(cell), (20, 30), interpolation=cv2.INTER_AREA)
    prototypes = np.stack((feature, 255 - feature))
    labels = np.array((16, 18), dtype=np.uint8)

    reading = _classify_whole_number((2, 4, cell), prototypes, labels)

    assert reading.text == "16"
    assert reading.trusted is True


def test_puzzle_35_fragmented_eight_is_not_read_as_six(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[2]

    observation = recognize_photo(project_root / "corpus" / "puzzle_035.jpg", tmp_path)

    assert observation.grid[7][2] == 8


def test_puzzle_34_weak_six_eight_vote_is_sent_to_hil(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[2]

    observation = recognize_photo(
        project_root / "corpus" / "puzzle_034.jpg",
        tmp_path,
        template_exclusion=34,
    )
    evidence = {(item.row, item.column): item for item in observation.evidence}

    assert evidence[(11, 5)].reading == "6"
    assert evidence[(11, 5)].trusted is False
    assert needs_hil_review(evidence[(11, 5)])


def test_puzzle_59_lost_leading_one_is_corrected_by_publisher_canon(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[2]

    observation = recognize_photo(project_root / "corpus" / "puzzle_059.jpg", tmp_path)
    evidence = {(item.row, item.column): item for item in observation.evidence}

    assert evidence[(2, 5)].reading == "19"
    assert evidence[(2, 5)].trusted is True


def test_puzzle_36_counter_family_errors_are_corrected_without_hil(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[2]

    observation = recognize_photo(project_root / "corpus" / "puzzle_036.jpg", tmp_path)
    evidence = {(item.row, item.column): item for item in observation.evidence}

    assert evidence[(1, 4)].reading == "18"
    assert not needs_hil_review(evidence[(1, 4)])
    assert evidence[(1, 7)].reading == "8"
    assert not needs_hil_review(evidence[(1, 7)])


def test_puzzle_44_open_five_is_not_read_as_eight(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[2]

    observation = recognize_photo(project_root / "corpus" / "puzzle_044.jpg", tmp_path)

    assert observation.grid[0][6] == 5


def test_puzzle_48_joined_twenty_splits_between_digits(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[2]

    observation = recognize_photo(project_root / "corpus" / "puzzle_048.jpg", tmp_path)

    for row, column in ((2, 3), (7, 6), (11, 4), (13, 2), (13, 7), (13, 8)):
        assert observation.grid[row - 1][column - 1] == 20
