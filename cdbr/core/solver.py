"""Constraint propagation and deterministic backtracking for Codeword puzzles."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
import time

import tomlkit

from cdbr.core.lexicon import Lexicon, LexiconEntry, word_pattern
from cdbr.core.model import CodewordPuzzle, Slot


@dataclass(frozen=True, kw_only=True)
class Solution:
    mapping: dict[int, str]
    words: dict[int, LexiconEntry]


@dataclass(frozen=True, kw_only=True)
class SolveResult:
    solutions: tuple[Solution, ...]
    exhausted: bool
    nodes: int
    best_mapping: dict[int, str]


class _SearchDeadlineReached(Exception):
    """Stop constraint propagation when its wall-clock budget expires."""


def _solution_quality(solution: Solution) -> tuple[float, float]:
    """Rank complete solutions by their weakest and then average vocabulary."""

    scores = [
        entry.score - (0.15 if entry.source.startswith("compound(") else 0.0) for entry in solution.words.values()
    ]
    return (min(scores, default=0.0), sum(scores) / len(scores) if scores else 0.0)


def _compatible(
    symbols: tuple[int, ...],
    word: str,
    mapping: dict[int, str],
    reverse: dict[str, int],
) -> bool:
    for symbol, letter in zip(symbols, word, strict=True):
        assigned = mapping.get(symbol)
        if assigned is not None and assigned != letter:
            return False
        owner = reverse.get(letter)
        if owner is not None and owner != symbol:
            return False
    return True


def _extend_mapping(symbols: tuple[int, ...], word: str, mapping: dict[int, str]) -> dict[int, str] | None:
    extended = dict(mapping)
    reverse = {letter: symbol for symbol, letter in extended.items()}
    if not _compatible(symbols, word, extended, reverse):
        return None
    for symbol, letter in zip(symbols, word, strict=True):
        extended[symbol] = letter
        reverse[letter] = symbol
    return extended


def _slot_candidates(
    slot: Slot,
    lexicon: Lexicon,
    mapping: dict[int, str],
    *,
    deadline: float | None = None,
) -> tuple[LexiconEntry, ...]:
    if deadline is not None and time.monotonic() >= deadline:
        raise _SearchDeadlineReached
    reverse = {letter: symbol for symbol, letter in mapping.items()}
    candidates = tuple(
        entry for entry in lexicon.candidates(slot.symbols) if _compatible(slot.symbols, entry.word, mapping, reverse)
    )
    if candidates or slot.length < 5:
        return candidates
    compounds: dict[str, LexiconEntry] = {}
    for split in range(2, slot.length - 1):
        if deadline is not None and time.monotonic() >= deadline:
            raise _SearchDeadlineReached
        left = tuple(
            entry
            for entry in lexicon.candidates(slot.symbols[:split])
            if _compatible(slot.symbols[:split], entry.word, mapping, reverse)
        )[:1000]
        right = tuple(
            entry
            for entry in lexicon.candidates(slot.symbols[split:])
            if _compatible(slot.symbols[split:], entry.word, mapping, reverse)
        )[:1000]
        for first in left:
            if deadline is not None and time.monotonic() >= deadline:
                raise _SearchDeadlineReached
            for second in right:
                word = first.word + second.word
                if word_pattern(word) != word_pattern(slot.symbols):
                    continue
                if not _compatible(slot.symbols, word, mapping, reverse):
                    continue
                entry = LexiconEntry(
                    word=word,
                    score=(first.score + second.score) / 2,
                    source=f"compound({first.source}; {second.source})",
                )
                previous = compounds.get(word)
                if previous is None or entry.score > previous.score:
                    compounds[word] = entry
    return tuple(sorted(compounds.values(), key=lambda entry: (-entry.score, entry.word)))


def slot_candidates(slot: Slot, lexicon: Lexicon, mapping: dict[int, str]) -> tuple[LexiconEntry, ...]:
    """Return the candidates accepted by the solver for one mapped slot."""

    return _slot_candidates(slot, lexicon, mapping)


def _propagate(
    puzzle: CodewordPuzzle,
    lexicon: Lexicon,
    mapping: dict[int, str],
    on_progress: Callable[[dict[int, str]], None] | None = None,
    deadline: float | None = None,
) -> tuple[dict[int, str], dict[int, tuple[LexiconEntry, ...]]] | None:
    current = dict(mapping)
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            raise _SearchDeadlineReached
        if on_progress is not None:
            on_progress(current)
        candidates: dict[int, tuple[LexiconEntry, ...]] = {}
        for slot in puzzle.slots:
            candidates[slot.index] = _slot_candidates(slot, lexicon, current, deadline=deadline)
        if any(not values for values in candidates.values()):
            return None
        forced: dict[int, str] = {}
        reverse = {letter: symbol for symbol, letter in current.items()}
        for slot in puzzle.slots:
            values = candidates[slot.index]
            for position, symbol in enumerate(slot.symbols):
                letters = {entry.word[position] for entry in values}
                if len(letters) != 1:
                    continue
                letter = next(iter(letters))
                if symbol in current and current[symbol] != letter:
                    return None
                owner = reverse.get(letter)
                if owner is not None and owner != symbol:
                    return None
                if symbol in forced and forced[symbol] != letter:
                    return None
                forced[symbol] = letter
        additions = {symbol: letter for symbol, letter in forced.items() if symbol not in current}
        if not additions:
            return current, candidates
        current.update(additions)


def solve(
    puzzle: CodewordPuzzle,
    lexicon: Lexicon,
    *,
    max_solutions: int = 20,
    max_nodes: int = 100_000,
    deadline: float | None = None,
) -> SolveResult:
    """Find up to max_solutions, reporting whether search was exhaustive."""

    solutions: list[Solution] = []
    nodes = 0
    stopped = False
    best_mapping = dict(puzzle.clues)
    puzzle_symbols = {symbol for row in puzzle.grid for symbol in row if symbol is not None}

    def search(mapping: dict[int, str]) -> None:
        nonlocal nodes, stopped, best_mapping
        if stopped:
            return
        nodes += 1
        if nodes > max_nodes or (deadline is not None and time.monotonic() >= deadline):
            stopped = True
            return

        def record_progress(progress: dict[int, str]) -> None:
            nonlocal best_mapping
            if len(progress) > len(best_mapping):
                best_mapping = dict(progress)

        try:
            propagated = _propagate(puzzle, lexicon, mapping, on_progress=record_progress, deadline=deadline)
        except _SearchDeadlineReached:
            stopped = True
            return
        if propagated is None:
            return
        resolved, candidates = propagated
        record_progress(resolved)
        if puzzle_symbols <= resolved.keys():
            words = {slot.index: candidates[slot.index][0] for slot in puzzle.slots}
            solutions.append(Solution(mapping=resolved, words=words))
            if len(solutions) >= max_solutions:
                stopped = True
            return
        choices = [
            (len(candidates[slot.index]), slot)
            for slot in puzzle.slots
            if len(candidates[slot.index]) > 1 and any(symbol not in resolved for symbol in slot.symbols)
        ]
        if not choices:
            return
        _, slot = min(choices, key=lambda item: (item[0], -item[1].length, item[1].index))
        for entry in candidates[slot.index]:
            extended = _extend_mapping(slot.symbols, entry.word, resolved)
            if extended is not None:
                search(extended)
            if stopped:
                return

    search(dict(puzzle.clues))
    ranked_solutions = tuple(sorted(solutions, key=_solution_quality, reverse=True))
    return SolveResult(
        solutions=ranked_solutions,
        exhausted=not stopped,
        nodes=nodes,
        best_mapping=best_mapping,
    )


def decode_grid(puzzle: CodewordPuzzle, mapping: dict[int, str]) -> tuple[str, ...]:
    return tuple("".join("#" if symbol is None else mapping.get(symbol, "?") for symbol in row) for row in puzzle.grid)


def solve_result_to_toml(puzzle: CodewordPuzzle, result: SolveResult) -> str:
    """Render status, mapping, decoded board, and lexical provenance."""

    document = tomlkit.document()
    document.add("format_version", 1)
    document.add("solutions_found", len(result.solutions))
    document.add("search_exhausted", result.exhausted)
    document.add("search_nodes", result.nodes)
    if not result.solutions:
        status = "no-solution-under-candidates" if result.exhausted else "search-limited"
    elif len(result.solutions) > 1:
        status = "multiple"
    elif result.exhausted:
        status = "unique"
    else:
        status = "provisional"
    document.add("status", status)
    if not result.solutions:
        return tomlkit.dumps(document)

    solution = result.solutions[0]
    mapping = tomlkit.table()
    for symbol, letter in sorted(solution.mapping.items()):
        mapping.add(str(symbol), letter)
    document.add("mapping", mapping)

    decoded = tomlkit.array()
    decoded.multiline(True)
    decoded.extend(decode_grid(puzzle, solution.mapping))
    document.add("decoded", decoded)

    words = tomlkit.aot()
    for slot in puzzle.slots:
        entry = solution.words[slot.index]
        item = tomlkit.table()
        item.add("direction", slot.direction)
        item.add("row", slot.row + 1)
        item.add("column", slot.column + 1)
        item.add("word", entry.word)
        item.add("source", entry.source)
        item.add("score", round(entry.score, 3))
        words.append(item)
    document.add("words", words)
    return tomlkit.dumps(document)
