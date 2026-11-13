"""Tests for canonical puzzle observations."""

from pathlib import Path

import pytest
import tomlkit

from cdbr.core.puzzle import BLOCK, UNKNOWN, CellUncertainty, PuzzleObservation, puzzle_to_toml


def test_puzzle_to_toml_preserves_uncertainty():
    puzzle = PuzzleObservation(
        source=Path("puzzle.heic"),
        source_format="HEIF",
        grid=((BLOCK, 5), (UNKNOWN, 10)),
        clues={5: "s"},
        uncertainties=(CellUncertainty(row=2, column=1, reading="8", confidence=42.5),),
    )

    document = tomlkit.parse(puzzle_to_toml(puzzle))

    assert document["grid"] == ["## 05", "?? 10"]
    assert document["complete"] is False
    assert document["clues"]["5"] == "S"
    assert document["uncertainties"][0]["reading"] == "8"


def test_puzzle_rejects_symbol_outside_codeword_range():
    puzzle = PuzzleObservation(
        source=Path("puzzle.png"),
        source_format="PNG",
        grid=((27,),),
        clues={},
        uncertainties=(),
    )

    with pytest.raises(ValueError, match="Invalid puzzle cell value"):
        puzzle_to_toml(puzzle)
