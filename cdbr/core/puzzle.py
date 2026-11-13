"""Puzzle observations and their canonical TOML representation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tomlkit


BLOCK = "."
UNKNOWN = "?"
GridValue = int | str


@dataclass(frozen=True, kw_only=True)
class CellUncertainty:
    row: int
    column: int
    confidence: float
    reading: str = ""
    reason: str = "low OCR confidence"


@dataclass(frozen=True, kw_only=True)
class PuzzleObservation:
    source: Path
    source_format: str
    grid: tuple[tuple[GridValue, ...], ...]
    clues: dict[int, str]
    uncertainties: tuple[CellUncertainty, ...]

    @property
    def width(self) -> int:
        return len(self.grid[0])

    @property
    def height(self) -> int:
        return len(self.grid)

    @property
    def complete(self) -> bool:
        return not self.uncertainties

    def validate(self) -> None:
        if not self.grid or not self.grid[0]:
            raise ValueError("Puzzle grid is empty")
        if any(len(row) != self.width for row in self.grid):
            raise ValueError("Puzzle grid rows have inconsistent widths")
        for row in self.grid:
            for value in row:
                if value not in (BLOCK, UNKNOWN) and not (isinstance(value, int) and 1 <= value <= 26):
                    raise ValueError(f"Invalid puzzle cell value: {value!r}")
        for symbol, letter in self.clues.items():
            if not 1 <= symbol <= 26 or len(letter) != 1 or not letter.isalpha():
                raise ValueError(f"Invalid supplied clue: {symbol}={letter!r}")


def puzzle_to_toml(puzzle: PuzzleObservation) -> str:
    """Serialize an observation without promoting uncertain OCR to facts."""

    puzzle.validate()
    document = tomlkit.document()
    document.add("format_version", 1)
    document.add("width", puzzle.width)
    document.add("height", puzzle.height)
    document.add("complete", puzzle.complete)
    grid = tomlkit.array()
    grid.multiline(True)
    grid.extend(
        " ".join("##" if value == BLOCK else "??" if value == UNKNOWN else f"{value:02d}" for value in row)
        for row in puzzle.grid
    )
    document.add("grid", grid)

    source = tomlkit.table()
    source.add("image", str(puzzle.source))
    source.add("image_format", puzzle.source_format)
    document.add("source", source)

    clues = tomlkit.table()
    for symbol, letter in sorted(puzzle.clues.items()):
        clues.add(str(symbol), letter.upper())
    document.add("clues", clues)

    uncertainties = tomlkit.aot()
    for item in puzzle.uncertainties:
        entry = tomlkit.table()
        entry.add("row", item.row)
        entry.add("column", item.column)
        if item.reading:
            entry.add("reading", item.reading)
        entry.add("confidence", round(item.confidence, 2))
        entry.add("reason", item.reason)
        uncertainties.append(entry)
    if uncertainties:
        document.add("uncertainties", uncertainties)

    return tomlkit.dumps(document)
