"""Offline construction and certification of Codeword puzzles."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
import random
import string
import time

import tomlkit

from cdbr.core.lexicon import Lexicon, LexiconEntry
from cdbr.core.model import CodewordPuzzle, extract_slots
from cdbr.core.solver import SolveResult, solve


FIRST_WORD_SQUARE = ("HEART", "EMBER", "ABUSE", "RESIN", "TREND")
Position = tuple[int, int]
Topology = tuple[tuple[bool, ...], ...]  # True means blocked.
Progress = Callable[[str], None]


@dataclass(frozen=True, kw_only=True)
class GenerationLimits:
    size: int = 15
    blocks: int = 48
    max_block_run: int = 2
    max_word_length: int = 14
    minimum_word_length: int = 4
    target_slots: int = 28
    minimum_score: float = 3.5
    fill_nodes: int = 500
    certify_nodes: int = 50_000
    clue_count: int = 3
    attempts: int = 100
    seconds: float = 0.0


@dataclass(frozen=True, kw_only=True)
class GeneratedPuzzle:
    puzzle: CodewordPuzzle
    answer: tuple[str, ...]
    mapping: dict[int, str]
    certification: SolveResult
    seed: int
    fill_nodes: int = 0
    attempts: int = 1
    theme_words: tuple[str, ...] = ()


def _runs(values: tuple[bool, ...], target: bool) -> tuple[int, ...]:
    lengths: list[int] = []
    length = 0
    for value in (*values, not target):
        if value is target:
            length += 1
        elif length:
            lengths.append(length)
            length = 0
    return tuple(lengths)


def _connected(topology: Topology) -> bool:
    open_cells = {
        (row, column) for row, values in enumerate(topology) for column, blocked in enumerate(values) if not blocked
    }
    if not open_cells:
        return False
    pending = [next(iter(open_cells))]
    reached: set[Position] = set()
    while pending:
        row, column = pending.pop()
        if (row, column) in reached or (row, column) not in open_cells:
            continue
        reached.add((row, column))
        pending.extend(((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1)))
    return reached == open_cells


def valid_topology(topology: Topology, *, max_block_run: int, max_word_length: int) -> bool:
    """Check the cheap structural rules used by the first constructor."""

    size = len(topology)
    if size < 3 or any(len(row) != size for row in topology):
        return False
    if any(
        topology[row][column] != topology[size - row - 1][size - column - 1]
        for row in range(size)
        for column in range(size)
    ):
        return False
    columns = tuple(tuple(topology[row][column] for row in range(size)) for column in range(size))
    for line in (*topology, *columns):
        if any(length > max_block_run for length in _runs(line, True)):
            return False
        if any(length == 1 or length > max_word_length for length in _runs(line, False)):
            return False
    return _connected(topology)


def generate_topology(
    rng: random.Random,
    *,
    size: int,
    blocks: int,
    max_block_run: int,
    max_word_length: int,
    tries: int = 20_000,
) -> Topology | None:
    """Generate a rotationally symmetric square block layout."""

    target = min(blocks, size * size - 4)
    for _ in range(tries):
        cells = [[False] * size for _ in range(size)]
        representatives = [
            (row, column)
            for row in range(size)
            for column in range(size)
            if (row, column) <= (size - row - 1, size - column - 1)
        ]
        rng.shuffle(representatives)
        count = 0
        for row, column in representatives:
            partner = (size - row - 1, size - column - 1)
            addition = 1 if partner == (row, column) else 2
            if count + addition > target:
                continue
            cells[row][column] = True
            cells[partner[0]][partner[1]] = True
            partial = tuple(tuple(values) for values in cells)
            if not valid_topology(
                partial,
                max_block_run=max_block_run,
                max_word_length=size,
            ):
                cells[row][column] = False
                cells[partner[0]][partner[1]] = False
                continue
            count += addition
            if count == target:
                break
        topology = tuple(tuple(row) for row in cells)
        if count == target and valid_topology(
            topology,
            max_block_run=max_block_run,
            max_word_length=max_word_length,
        ):
            return topology
    return None


def _answer_run_lengths(topology: Topology) -> tuple[int, ...]:
    size = len(topology)
    columns = tuple(tuple(topology[row][column] for row in range(size)) for column in range(size))
    return tuple(length for line in (*topology, *columns) for length in _runs(line, False) if length >= 2)


def _slot_shape_valid(
    topology: Topology,
    *,
    minimum_word_length: int,
    max_word_length: int,
    allowed_short: Counter[int],
    required_lengths: Counter[int],
    target_slots: int,
) -> bool:
    lengths = _answer_run_lengths(topology)
    counts = Counter(lengths)
    if len(lengths) > target_slots:
        return False
    if any(length > max_word_length for length in lengths):
        return False
    if any(length < minimum_word_length and counts[length] > allowed_short[length] for length in counts):
        return False
    return all(counts[length] >= count for length, count in required_lengths.items())


def generate_slot_topology(
    rng: random.Random,
    *,
    size: int,
    required_lengths: tuple[int, ...],
    target_slots: int,
    minimum_word_length: int,
    max_word_length: int,
    tries: int = 500,
) -> Topology | None:
    """Grow a sparse criss-cross topology from answer slots, not random blocks."""

    allowed_short = Counter(length for length in required_lengths if length < minimum_word_length)
    ordinary_lengths = tuple(range(minimum_word_length, max_word_length + 1))
    # Favour the 6-10 character answers prevalent in the supplied puzzles.
    weighted_lengths = tuple(length for length in ordinary_lengths for _ in range(max(1, 8 - abs(7 - length))))
    for _ in range(tries):
        cells = [[True] * size for _ in range(size)]
        placed_required: Counter[int] = Counter()
        pending = sorted(required_lengths, reverse=True)
        failed = False
        while pending or len(_answer_run_lengths(tuple(tuple(row) for row in cells))) < target_slots:
            required_length = pending[0] if pending else None
            added = False
            for _candidate in range(2_000):
                length = required_length if required_length is not None else rng.choice(weighted_lengths)
                direction = rng.choice(("across", "down"))
                if direction == "across":
                    row = rng.randrange(size)
                    column = rng.randrange(size - length + 1)
                    positions = tuple((row, column + offset) for offset in range(length))
                else:
                    row = rng.randrange(size - length + 1)
                    column = rng.randrange(size)
                    positions = tuple((row + offset, column) for offset in range(length))
                open_count = sum(not cells[r][c] for r, c in positions)
                any_open = any(not value for line in cells for value in line)
                if required_length is not None:
                    # Reserve explicit theme entries independently. Ordinary
                    # slots added below will connect the components.
                    if open_count:
                        continue
                elif not any_open or open_count in (0, length):
                    continue
                trial = [line.copy() for line in cells]
                for r, c in positions:
                    trial[r][c] = False
                topology = tuple(tuple(line) for line in trial)
                trial_required = placed_required.copy()
                if required_length is not None:
                    trial_required[required_length] += 1
                if not _slot_shape_valid(
                    topology,
                    minimum_word_length=minimum_word_length,
                    max_word_length=max_word_length,
                    allowed_short=allowed_short,
                    required_lengths=trial_required,
                    target_slots=target_slots,
                ):
                    continue
                cells = trial
                placed_required = trial_required
                if required_length is not None:
                    pending.pop(0)
                added = True
                break
            if not added:
                failed = True
                break
        topology = tuple(tuple(row) for row in cells)
        if not failed and len(_answer_run_lengths(topology)) == target_slots and _connected(topology):
            return topology
    return None


def _slot_positions(topology: Topology) -> tuple[tuple[Position, ...], ...]:
    numbered = tuple(tuple(None if blocked else 1 for blocked in row) for row in topology)
    return tuple(
        tuple(
            (slot.row, slot.column + offset) if slot.direction == "across" else (slot.row + offset, slot.column)
            for offset in range(slot.length)
        )
        for slot in extract_slots(numbered)
    )


def fill_topology(
    topology: Topology,
    lexicon: Lexicon,
    rng: random.Random,
    *,
    minimum_score: float,
    max_nodes: int,
    deadline: float | None = None,
    required_words: tuple[str, ...] = (),
) -> tuple[tuple[str, ...] | None, int]:
    """Fill a topology by minimum-remaining-values backtracking."""

    slots = _slot_positions(topology)
    entries = {
        length: tuple(entry for entry in lexicon.entries(length) if entry.score >= minimum_score)
        for length in {len(slot) for slot in slots}
    }
    board: list[list[str | None]] = [["#" if blocked else None for blocked in row] for row in topology]
    remaining = set(range(len(slots)))
    used: set[str] = set()
    nodes = 0

    def place_required(pending: tuple[str, ...]) -> bool:
        if not pending:
            return True
        word = pending[0]
        choices = [index for index in remaining if len(slots[index]) == len(word)]
        rng.shuffle(choices)
        for index in choices:
            if any(
                board[row][column] not in (None, letter)
                for (row, column), letter in zip(slots[index], word, strict=True)
            ):
                continue
            changed: list[Position] = []
            for (row, column), letter in zip(slots[index], word, strict=True):
                if board[row][column] is None:
                    board[row][column] = letter
                    changed.append((row, column))
            remaining.remove(index)
            used.add(word)
            if place_required(pending[1:]):
                return True
            used.remove(word)
            remaining.add(index)
            for row, column in changed:
                board[row][column] = None
        return False

    if not place_required(tuple(sorted(required_words, key=lambda word: (-len(word), word)))):
        return None, 0
    if any(not entries[len(slots[index])] for index in remaining):
        return None, 0
    domains: dict[int, list[LexiconEntry]] = {}
    for index in remaining:
        slot = slots[index]
        values = list(entries[len(slot)])
        pattern = tuple(board[row][column] for row, column in slot)
        values = [
            entry
            for entry in values
            if entry.word not in used
            and all(
                letter is None or letter == candidate for letter, candidate in zip(pattern, entry.word, strict=True)
            )
        ]
        values.sort(key=lambda entry: entry.score + rng.random() * 0.35, reverse=True)
        domains[index] = values
    cell_slots: dict[Position, set[int]] = {}
    for index, slot in enumerate(slots):
        for position in slot:
            cell_slots.setdefault(position, set()).add(index)

    def search() -> bool:
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes or (deadline is not None and time.monotonic() >= deadline):
            return False
        if not remaining:
            return True
        index = min(
            remaining,
            key=lambda candidate_index: (
                len(domains[candidate_index]),
                -len(slots[candidate_index]),
                candidate_index,
            ),
        )
        values = domains[index]
        if not values:
            return False
        remaining.remove(index)
        for entry in values:
            if entry.word in used:
                continue
            changed: list[Position] = []
            for (row, column), letter in zip(slots[index], entry.word, strict=True):
                if board[row][column] is None:
                    board[row][column] = letter
                    changed.append((row, column))
            used.add(entry.word)
            affected = {
                affected_index
                for position in slots[index]
                for affected_index in cell_slots[position]
                if affected_index in remaining
            }
            saved_domains = {affected_index: domains[affected_index] for affected_index in affected}
            viable = True
            for affected_index in affected:
                pattern = tuple(board[row][column] for row, column in slots[affected_index])
                domains[affected_index] = [
                    candidate
                    for candidate in domains[affected_index]
                    if candidate.word not in used
                    and all(
                        letter is None or letter == candidate_letter
                        for letter, candidate_letter in zip(pattern, candidate.word, strict=True)
                    )
                ]
                if not domains[affected_index]:
                    viable = False
                    break
            if viable and search():
                return True
            domains.update(saved_domains)
            used.remove(entry.word)
            for row, column in changed:
                board[row][column] = None
            if nodes > max_nodes or (deadline is not None and time.monotonic() >= deadline):
                break
        remaining.add(index)
        return False

    if not search():
        return None, nodes
    return tuple("".join(value or "?" for value in row) for row in board), nodes


def construct_crossword(
    lexicon: Lexicon,
    rng: random.Random,
    *,
    size: int,
    required_words: tuple[str, ...],
    target_slots: int,
    minimum_word_length: int,
    max_word_length: int,
    minimum_score: float,
    max_nodes: int,
    deadline: float | None = None,
    excluded_words: frozenset[str] = frozenset(),
) -> tuple[tuple[str, ...] | None, int]:
    """Grow a connected criss-cross fill around required theme entries."""

    board: list[list[str | None]] = [[None] * size for _ in range(size)]
    directions = [[0] * size for _ in range(size)]  # across=1, down=2
    used: set[str] = set()
    nodes = 0

    def placements(word: str, *, require_crossing: bool) -> list[tuple[str, int, int, int]]:
        found: list[tuple[str, int, int, int]] = []
        for direction, bit, row_step, column_step in (("across", 1, 0, 1), ("down", 2, 1, 0)):
            anchors = (
                (
                    (row, column, offset)
                    for row in range(size)
                    for column in range(size)
                    for offset, letter in enumerate(word)
                    if board[row][column] == letter
                )
                if require_crossing
                else ((row, column, 0) for row in range(size) for column in range(size) if board[row][column] is None)
            )
            for row, column, offset in anchors:
                start_row = row - offset * row_step
                start_column = column - offset * column_step
                end_row = start_row + (len(word) - 1) * row_step
                end_column = start_column + (len(word) - 1) * column_step
                if min(start_row, start_column) < 0 or end_row >= size or end_column >= size:
                    continue
                before = (start_row - row_step, start_column - column_step)
                after = (end_row + row_step, end_column + column_step)
                if 0 <= before[0] < size and 0 <= before[1] < size and board[before[0]][before[1]] is not None:
                    continue
                if 0 <= after[0] < size and 0 <= after[1] < size and board[after[0]][after[1]] is not None:
                    continue
                crossings = 0
                valid = True
                for index, candidate_letter in enumerate(word):
                    r = start_row + index * row_step
                    c = start_column + index * column_step
                    current = board[r][c]
                    if current is not None:
                        if current != candidate_letter or directions[r][c] & bit:
                            valid = False
                            break
                        crossings += 1
                        continue
                    neighbours = ((r - 1, c), (r + 1, c)) if bit == 1 else ((r, c - 1), (r, c + 1))
                    if any(0 <= nr < size and 0 <= nc < size and board[nr][nc] is not None for nr, nc in neighbours):
                        valid = False
                        break
                if valid and (crossings > 0 or not require_crossing):
                    found.append((direction, start_row, start_column, crossings))
        return list(dict.fromkeys(found))

    def place(word: str, location: tuple[str, int, int, int]) -> None:
        direction, row, column, _ = location
        bit = 1 if direction == "across" else 2
        row_step, column_step = (0, 1) if bit == 1 else (1, 0)
        for index, letter in enumerate(word):
            r = row + index * row_step
            c = column + index * column_step
            board[r][c] = letter
            directions[r][c] |= bit
        used.add(word)

    def unplace(word: str, location: tuple[str, int, int, int]) -> None:
        direction, row, column, _ = location
        bit = 1 if direction == "across" else 2
        row_step, column_step = (0, 1) if bit == 1 else (1, 0)
        for index in range(len(word)):
            r = row + index * row_step
            c = column + index * column_step
            directions[r][c] &= ~bit
            if directions[r][c] == 0:
                board[r][c] = None
        used.remove(word)

    themes = tuple(sorted(required_words, key=lambda word: (-len(word), word)))
    if themes:
        first = themes[0]
        direction = rng.choice(("across", "down"))
        if direction == "across":
            first_location = (direction, size // 2, (size - len(first)) // 2, 0)
        else:
            first_location = (direction, (size - len(first)) // 2, size // 2, 0)
        place(first, first_location)
        for word in themes[1:]:
            choices = placements(word, require_crossing=True)
            if not choices:
                return None, nodes
            choices.sort(key=lambda item: (item[3], rng.random()), reverse=True)
            place(word, choices[0])

    def open_slots() -> list[tuple[tuple[str | None, ...], tuple[str, int, int, int]]]:
        """Return geometrically viable slots and their currently fixed letters."""

        found: list[tuple[tuple[str | None, ...], tuple[str, int, int, int]]] = []
        for length in range(minimum_word_length, max_word_length + 1):
            for direction, bit, row_step, column_step in (("across", 1, 0, 1), ("down", 2, 1, 0)):
                row_limit = size - (length - 1) * row_step
                column_limit = size - (length - 1) * column_step
                for row in range(row_limit):
                    for column in range(column_limit):
                        end_row = row + (length - 1) * row_step
                        end_column = column + (length - 1) * column_step
                        before = (row - row_step, column - column_step)
                        after = (end_row + row_step, end_column + column_step)
                        if 0 <= before[0] < size and 0 <= before[1] < size and board[before[0]][before[1]] is not None:
                            continue
                        if 0 <= after[0] < size and 0 <= after[1] < size and board[after[0]][after[1]] is not None:
                            continue
                        pattern: list[str | None] = []
                        crossings = 0
                        valid = True
                        for index in range(length):
                            r = row + index * row_step
                            c = column + index * column_step
                            current = board[r][c]
                            pattern.append(current)
                            if current is not None:
                                if directions[r][c] & bit:
                                    valid = False
                                    break
                                crossings += 1
                                continue
                            neighbours = ((r - 1, c), (r + 1, c)) if bit == 1 else ((r, c - 1), (r, c + 1))
                            if any(
                                0 <= nr < size and 0 <= nc < size and board[nr][nc] is not None for nr, nc in neighbours
                            ):
                                valid = False
                                break
                        if valid and crossings:
                            found.append(
                                (
                                    tuple(pattern),
                                    (direction, row, column, crossings),
                                )
                            )
        return found

    def search() -> bool:
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes or (deadline is not None and time.monotonic() >= deadline):
            return False
        if len(used) >= target_slots:
            return True

        viable_options: list[tuple[LexiconEntry, tuple[str, int, int, int]]] = []
        for pattern, location in open_slots():
            eligible = [
                entry
                for entry in lexicon.matching(pattern)
                if entry.score >= minimum_score
                and entry.word not in used
                and entry.word not in excluded_words
                and not lexicon.discouraged(entry.word)
            ]
            # Retain lexical quality while allowing a little seeded variety.
            sample = eligible[:32]
            if len(eligible) > 32:
                sample.extend(rng.sample(eligible[32:], min(8, len(eligible) - 32)))
            for entry in sample:
                viable_options.append((entry, location))
        # Explore a bounded sample only after impossible words and placements
        # have been removed. This keeps attempts varied without gambling on
        # unrelated words from the full lexicon.
        sample_options = rng.sample(viable_options, min(len(viable_options), 80))
        options: list[tuple[float, LexiconEntry, tuple[str, int, int, int]]] = []
        for entry, location in sample_options:
            newly_opened = len(entry.word) - location[3]
            # Completion and lexical quality are hard constraints. Black cell
            # reduction remains a modest hill-climbing preference.
            score = location[3] * 5 + newly_opened * 0.2 + entry.score + rng.random() * 0.5
            options.append((score, entry, location))
        options.sort(key=lambda item: item[0], reverse=True)
        for _, entry, location in options[:8]:
            place(entry.word, location)
            if search():
                return True
            unplace(entry.word, location)
            if nodes > max_nodes or (deadline is not None and time.monotonic() >= deadline):
                break
        return False

    if not search():
        return None, nodes
    return tuple("".join(letter or "#" for letter in row) for row in board), nodes


def _encode(answer: tuple[str, ...], seed: int) -> tuple[tuple[tuple[int | None, ...], ...], dict[int, str]]:
    letters = list(string.ascii_uppercase)
    numbers = list(range(1, 27))
    random.Random(seed).shuffle(numbers)
    letter_to_symbol = dict(zip(letters, numbers, strict=True))
    mapping = {symbol: letter for letter, symbol in letter_to_symbol.items()}
    grid = tuple(tuple(None if letter == "#" else letter_to_symbol[letter] for letter in row) for row in answer)
    return grid, mapping


def _certify_with_directed_clues(
    grid: tuple[tuple[int | None, ...], ...],
    full_mapping: dict[int, str],
    lexicon: Lexicon,
    *,
    max_nodes: int,
    deadline: float | None = None,
    clue_count: int = 3,
) -> tuple[CodewordPuzzle, SolveResult] | None:
    """Choose exactly *clue_count* mappings and certify uniqueness."""

    used_symbols = {symbol for row in grid for symbol in row if symbol is not None}
    ranked_symbols = sorted(
        used_symbols,
        key=lambda symbol: (-sum(row.count(symbol) for row in grid), symbol),
    )
    if clue_count > len(used_symbols):
        return None
    clues: dict[int, str] = {}
    while len(clues) < clue_count:
        if deadline is not None and time.monotonic() >= deadline:
            return None
        puzzle = CodewordPuzzle(grid=grid, clues=dict(clues), slots=extract_slots(grid))
        result = solve(puzzle, lexicon, max_solutions=2, max_nodes=max_nodes, deadline=deadline)
        if result.exhausted and len(result.solutions) == 1:
            for symbol in ranked_symbols:
                if symbol not in clues:
                    clues[symbol] = full_mapping[symbol]
                    if len(clues) == clue_count:
                        break
            break
        if len(result.solutions) < 2:
            return None
        first, second = result.solutions[:2]
        choices = [symbol for symbol in sorted(used_symbols) if first.mapping.get(symbol) != second.mapping.get(symbol)]
        if not choices:
            return None
        symbol = max(choices, key=lambda value: sum(row.count(value) for row in grid))
        clues[symbol] = full_mapping[symbol]

    puzzle = CodewordPuzzle(grid=grid, clues=dict(clues), slots=extract_slots(grid))
    result = solve(puzzle, lexicon, max_solutions=2, max_nodes=max_nodes, deadline=deadline)
    if result.exhausted and len(result.solutions) == 1:
        return puzzle, result
    return None


def generate_first_puzzle(lexicon: Lexicon, *, seed: int = 0) -> GeneratedPuzzle:
    """Encode the compact first fill and certify it with directed clues."""

    grid, full_mapping = _encode(FIRST_WORD_SQUARE, seed)
    certified = _certify_with_directed_clues(grid, full_mapping, lexicon, max_nodes=250_000)
    if certified is None:
        raise ValueError("Could not certify the generated puzzle as unique")
    puzzle, result = certified
    return GeneratedPuzzle(
        puzzle=puzzle,
        answer=FIRST_WORD_SQUARE,
        mapping=full_mapping,
        certification=result,
        seed=seed,
    )


def generate_puzzle(
    lexicon: Lexicon,
    *,
    seed: int,
    limits: GenerationLimits,
    progress: Progress | None = None,
    required_words: Iterable[str] = (),
    excluded_words: Iterable[str] = (),
) -> GeneratedPuzzle:
    """Try independent 15x15 topologies and fills within explicit limits."""

    theme_words = tuple(
        "".join(character for character in raw.upper() if character.isalpha()) for raw in required_words
    )
    if any(not word.isascii() or not word.isalpha() for word in theme_words):
        raise ValueError("Included words must use the letters A-Z")
    if len(set(theme_words)) != len(theme_words):
        raise ValueError("Included words must be distinct")
    if any(not 2 <= len(word) <= limits.max_word_length for word in theme_words):
        raise ValueError(f"Included words must contain 2-{limits.max_word_length} letters")
    exclusions = frozenset(
        "".join(character for character in raw.upper() if character.isalpha()) for raw in excluded_words
    )
    if any(not word.isascii() or not word.isalpha() for word in exclusions):
        raise ValueError("Excluded words must use the letters A-Z")
    conflict = exclusions.intersection(theme_words)
    if conflict:
        raise ValueError(f"Words cannot be both included and excluded: {', '.join(sorted(conflict))}")
    active_lexicon = lexicon.extended(LexiconEntry(word=word, score=9.0, source="user-theme") for word in theme_words)
    rng = random.Random(seed)
    deadline = time.monotonic() + limits.seconds if limits.seconds > 0 else None
    for attempt in range(1, limits.attempts + 1):
        attempt_started = time.monotonic()
        if deadline is not None and time.monotonic() >= deadline:
            break
        if theme_words:
            if progress is not None:
                progress(f"attempt {attempt}/{limits.attempts}: growing themed fill")
            answer, fill_nodes = construct_crossword(
                active_lexicon,
                rng,
                size=limits.size,
                required_words=theme_words,
                target_slots=limits.target_slots,
                minimum_word_length=limits.minimum_word_length,
                max_word_length=limits.max_word_length,
                minimum_score=limits.minimum_score,
                max_nodes=limits.fill_nodes,
                deadline=deadline,
                excluded_words=exclusions,
            )
        else:
            if progress is not None:
                progress(f"attempt {attempt}/{limits.attempts}: constructing topology")
            topology = generate_slot_topology(
                rng,
                size=limits.size,
                required_lengths=(),
                target_slots=limits.target_slots,
                minimum_word_length=limits.minimum_word_length,
                max_word_length=limits.max_word_length,
            )
            if topology is None:
                continue
            if progress is not None:
                progress(f"attempt {attempt}/{limits.attempts}: filling grid")
            answer, fill_nodes = fill_topology(
                topology,
                active_lexicon,
                rng,
                minimum_score=limits.minimum_score,
                max_nodes=limits.fill_nodes,
                deadline=deadline,
            )
        if answer is None:
            if progress is not None:
                elapsed = time.monotonic() - attempt_started
                progress(
                    f"attempt {attempt}/{limits.attempts}: fill rejected after " f"{fill_nodes} nodes ({elapsed:.1f}s)"
                )
            continue
        grid, mapping = _encode(answer, rng.randrange(2**63))
        if progress is not None:
            elapsed = time.monotonic() - attempt_started
            progress(
                f"attempt {attempt}/{limits.attempts}: fill complete after "
                f"{fill_nodes} nodes ({elapsed:.1f}s); certifying uniqueness"
            )
        certified = _certify_with_directed_clues(
            grid,
            mapping,
            active_lexicon,
            max_nodes=limits.certify_nodes,
            deadline=deadline,
            clue_count=limits.clue_count,
        )
        if certified is None:
            continue
        puzzle, result = certified
        return GeneratedPuzzle(
            puzzle=puzzle,
            answer=answer,
            mapping=mapping,
            certification=result,
            seed=seed,
            fill_nodes=fill_nodes,
            attempts=attempt,
            theme_words=theme_words,
        )
    raise ValueError("No certified puzzle found within the generation limits")


def generated_puzzle_to_toml(generated: GeneratedPuzzle, *, include_answer: bool = False) -> str:
    """Serialize a generated puzzle and its reproducible certification."""

    document = tomlkit.document()
    document.add("format_version", 1)
    document.add("width", len(generated.puzzle.grid[0]))
    document.add("height", len(generated.puzzle.grid))
    grid = tomlkit.array()
    grid.multiline(True)
    grid.extend(
        " ".join("##" if symbol is None else f"{symbol:02d}" for symbol in row) for row in generated.puzzle.grid
    )
    document.add("grid", grid)

    clues = tomlkit.table()
    for symbol, letter in sorted(generated.puzzle.clues.items()):
        clues.add(str(symbol), letter)
    document.add("clues", clues)

    generation = tomlkit.table()
    generation.add("seed", generated.seed)
    generation.add("status", "unique")
    generation.add("search_exhausted", generated.certification.exhausted)
    generation.add("search_nodes", generated.certification.nodes)
    generation.add("fill_nodes", generated.fill_nodes)
    generation.add("attempts", generated.attempts)
    generation.add("supplied_clues", len(generated.puzzle.clues))
    document.add("generation", generation)
    if generated.theme_words:
        theme = tomlkit.table()
        requested = tomlkit.array()
        requested.extend(generated.theme_words)
        theme.add("requested", requested)
        document.add("theme", theme)
    if include_answer:
        answer = tomlkit.array()
        answer.multiline(True)
        answer.extend(generated.answer)
        document.add("answer", answer)
    return tomlkit.dumps(document)
