"""Validated Codeword puzzle model and word-slot extraction."""

from __future__ import annotations

from dataclasses import dataclass

from cdbr.core.puzzle import BLOCK, UNKNOWN, PuzzleObservation


@dataclass(frozen=True, kw_only=True)
class Slot:
    index: int
    direction: str
    row: int
    column: int
    symbols: tuple[int, ...]

    @property
    def length(self) -> int:
        return len(self.symbols)


@dataclass(frozen=True, kw_only=True)
class CodewordPuzzle:
    grid: tuple[tuple[int | None, ...], ...]
    clues: dict[int, str]
    slots: tuple[Slot, ...]

    @classmethod
    def from_observation(cls, observation: PuzzleObservation) -> CodewordPuzzle:
        observation.validate()
        if observation.uncertainties:
            raise ValueError("Cannot solve a puzzle with unresolved OCR cells")
        grid: list[tuple[int | None, ...]] = []
        for row in observation.grid:
            values: list[int | None] = []
            for value in row:
                if value == BLOCK:
                    values.append(None)
                elif value == UNKNOWN:
                    raise ValueError("Cannot solve a puzzle with unresolved OCR cells")
                else:
                    assert isinstance(value, int)
                    values.append(value)
            grid.append(tuple(values))
        normalized = tuple(grid)
        clues = {symbol: letter.upper() for symbol, letter in observation.clues.items()}
        if len(set(clues.values())) != len(clues):
            raise ValueError("Supplied clues violate the letter bijection")
        return cls(grid=normalized, clues=clues, slots=extract_slots(normalized))


def extract_slots(grid: tuple[tuple[int | None, ...], ...], *, minimum_length: int = 2) -> tuple[Slot, ...]:
    """Extract horizontal then vertical runs in stable reading order."""

    height = len(grid)
    width = len(grid[0])
    pending: list[tuple[str, int, int, tuple[int, ...]]] = []
    for row in range(height):
        column = 0
        while column < width:
            if grid[row][column] is None:
                column += 1
                continue
            start = column
            symbols: list[int] = []
            while column < width and grid[row][column] is not None:
                value = grid[row][column]
                assert value is not None
                symbols.append(value)
                column += 1
            if len(symbols) >= minimum_length:
                pending.append(("across", row, start, tuple(symbols)))
    for column in range(width):
        row = 0
        while row < height:
            if grid[row][column] is None:
                row += 1
                continue
            start = row
            symbols = []
            while row < height and grid[row][column] is not None:
                value = grid[row][column]
                assert value is not None
                symbols.append(value)
                row += 1
            if len(symbols) >= minimum_length:
                pending.append(("down", start, column, tuple(symbols)))
    return tuple(
        Slot(
            index=index,
            direction=direction,
            row=row,
            column=column,
            symbols=symbols,
        )
        for index, (direction, row, column, symbols) in enumerate(pending)
    )
