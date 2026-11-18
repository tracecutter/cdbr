"""Generation and independent solver-certification tests."""

import random

from cdbr.core.generator import (
    FIRST_WORD_SQUARE,
    construct_crossword,
    fill_topology,
    generate_first_puzzle,
    generate_topology,
    generated_puzzle_to_toml,
    valid_topology,
)
from cdbr.core.lexicon import Lexicon, LexiconEntry
from cdbr.core.solver import decode_grid


def _square_lexicon() -> Lexicon:
    return Lexicon(
        LexiconEntry(word=word, score=5.0, source="test")
        for word in (*FIRST_WORD_SQUARE, "HEATS", "ENTER", "AMUSE", "RERUN", "STAND")
    )


def test_generate_first_puzzle_is_reproducible_and_certified():
    generated = generate_first_puzzle(_square_lexicon(), seed=42)

    assert generated.certification.exhausted is True
    assert len(generated.certification.solutions) == 1
    assert len(generated.puzzle.clues) == 3
    assert decode_grid(generated.puzzle, generated.certification.solutions[0].mapping) == FIRST_WORD_SQUARE

    repeated = generate_first_puzzle(_square_lexicon(), seed=42)
    assert repeated.puzzle == generated.puzzle


def test_generated_toml_records_certification_without_answer():
    text = generated_puzzle_to_toml(generate_first_puzzle(_square_lexicon(), seed=7))

    assert 'status = "unique"' in text
    assert "search_exhausted = true" in text
    assert "HEART" not in text


def test_generate_realistic_topology_obeys_structural_limits():
    topology = generate_topology(
        random.Random(19),
        size=15,
        blocks=42,
        max_block_run=2,
        max_word_length=10,
        tries=100,
    )

    assert topology is not None
    assert sum(map(sum, topology)) == 42
    assert valid_topology(topology, max_block_run=2, max_word_length=10)


def test_fill_topology_constructs_crossing_words():
    topology = (
        (False, False, False),
        (False, True, False),
        (False, False, False),
    )
    lexicon = Lexicon(LexiconEntry(word=word, score=5.0, source="test") for word in ("CAT", "RED", "CAR", "TED"))

    answer, nodes = fill_topology(
        topology,
        lexicon,
        random.Random(3),
        minimum_score=0,
        max_nodes=1_000,
    )

    assert answer == ("CAT", "A#E", "RED")
    assert nodes > 0


def test_construct_crossword_places_short_explicit_theme_word():
    lexicon = Lexicon(LexiconEntry(word=word, score=5.0, source="test") for word in ("PERFECT", "FOR"))

    answer, _ = construct_crossword(
        lexicon,
        random.Random(7),
        size=9,
        required_words=("PERFECT", "FOR"),
        target_slots=2,
        minimum_word_length=4,
        max_word_length=9,
        minimum_score=0,
        max_nodes=100,
    )

    assert answer is not None
    rows_and_columns = (*answer, *("".join(row[column] for row in answer) for column in range(9)))
    entries = {word for line in rows_and_columns for word in line.split("#") if len(word) >= 2}
    assert {"PERFECT", "FOR"} <= entries


def test_lexicon_matches_fixed_crossing_letters():
    lexicon = Lexicon(
        LexiconEntry(word=word, score=5.0, source="test") for word in ("PERFECT", "PREFECT", "PERCENT", "PRESENT")
    )

    matches = lexicon.matching(("P", "E", None, "F", None, "C", "T"))

    assert tuple(entry.word for entry in matches) == ("PERFECT",)
