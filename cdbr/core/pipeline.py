"""Reusable photograph-to-solution pipeline shared by CLI and services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cdbr.core.lexicon import Lexicon, english_lexicon
from cdbr.core.model import CodewordPuzzle
from cdbr.core.puzzle import PuzzleObservation
from cdbr.core.recognition import recognize_photo
from cdbr.core.solver import SolveResult, solve


@dataclass(frozen=True, kw_only=True)
class SolvedPuzzle:
    observation: PuzzleObservation
    puzzle: CodewordPuzzle
    result: SolveResult
    mapping: dict[int, str]

    @property
    def complete(self) -> bool:
        return bool(self.result.solutions)


def solve_observation(observation: PuzzleObservation, lexicon: Lexicon | None = None) -> SolvedPuzzle:
    """Solve a recognised observation without depending on a user interface."""

    puzzle = CodewordPuzzle.from_observation(observation)
    result = solve(puzzle, lexicon or english_lexicon())
    mapping = result.solutions[0].mapping if result.solutions else result.best_mapping
    return SolvedPuzzle(
        observation=observation,
        puzzle=puzzle,
        result=result,
        mapping=mapping,
    )


def solve_photo(source: Path, work_dir: Path, lexicon: Lexicon | None = None) -> SolvedPuzzle:
    """Recognise and solve one photograph using caller-owned temporary storage."""

    return solve_observation(recognize_photo(source, work_dir), lexicon)
