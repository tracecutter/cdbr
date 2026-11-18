"""Constructed tests for slot extraction and bijective lexical solving."""

from cdbr.core.lexicon import Lexicon, LexiconEntry
from cdbr.core.model import CodewordPuzzle, extract_slots
from cdbr.core.solver import Solution, _solution_quality, decode_grid, solve
from cdbr.core.presentation import solution_rows


def test_extract_slots_and_solve_small_crossing_puzzle():
    grid = (
        (1, 2, 3),
        (None, 4, None),
        (5, 2, 6),
    )
    puzzle = CodewordPuzzle(
        grid=grid,
        clues={1: "C"},
        slots=extract_slots(grid),
    )
    lexicon = Lexicon(
        [
            LexiconEntry(word="CAT", score=5.0, source="test"),
            LexiconEntry(word="CAR", score=4.0, source="test"),
            LexiconEntry(word="AHA", score=5.0, source="test"),
            LexiconEntry(word="EAT", score=5.0, source="test"),
        ]
    )

    result = solve(puzzle, lexicon)

    assert len(result.solutions) == 1
    assert decode_grid(puzzle, result.solutions[0].mapping) == (
        "CAR",
        "#H#",
        "EAT",
    )


def test_solver_reports_contradiction_under_lexicon():
    grid = ((1, 2, 3),)
    puzzle = CodewordPuzzle(grid=grid, clues={1: "Z"}, slots=extract_slots(grid))
    lexicon = Lexicon([LexiconEntry(word="CAT", score=5.0, source="test")])

    result = solve(puzzle, lexicon)

    assert result.solutions == ()
    assert result.exhausted is True
    assert result.best_mapping == {1: "Z"}
    assert solution_rows(puzzle, result.best_mapping) == ("Z??",)


def test_solver_honours_deadline_during_constraint_propagation(monkeypatch):
    grid = ((1, 2, 3),)
    puzzle = CodewordPuzzle(grid=grid, clues={}, slots=extract_slots(grid))
    lexicon = Lexicon([LexiconEntry(word="CAT", score=5.0, source="test")])
    ticks = iter((0.0, 0.0, 2.0))
    monkeypatch.setattr("cdbr.core.solver.time.monotonic", lambda: next(ticks, 2.0))

    result = solve(puzzle, lexicon, deadline=1.0)

    assert result.exhausted is False
    assert result.solutions == ()


def test_solution_quality_prefers_the_stronger_weakest_word():
    common = Solution(
        mapping={},
        words={
            1: LexiconEntry(word="COMMON", score=5.0, source="test"),
            2: LexiconEntry(word="PLAIN", score=4.0, source="test"),
        },
    )
    obscure = Solution(
        mapping={},
        words={
            1: LexiconEntry(word="POPULAR", score=6.0, source="test"),
            2: LexiconEntry(word="ARCANE", score=1.0, source="test"),
        },
    )

    assert _solution_quality(common) > _solution_quality(obscure)
