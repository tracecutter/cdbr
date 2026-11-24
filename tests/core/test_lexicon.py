"""Tests for the packaged British English lexicon."""

from pathlib import Path

from cdbr.core.lexicon import english_lexicon, word_pattern


def test_publisher_confirmed_supplemental_words_are_available() -> None:
    lexicon = english_lexicon(system_dictionary=Path("/does/not/exist"))

    for word in (
        "BEETLEOFF",
        "BULLYOFF",
        "CHEWTHEFAT",
        "CZECHREPUBLIC",
        "ELMIEST",
        "FRIZZLIEST",
        "JUMPTHEGUN",
        "LOCKHORNS",
        "LOOKDOWNON",
        "MERCYPROOF",
        "NOHIT",
        "OXFORDBLUE",
        "SHEMOZZLE",
        "TUCKBOX",
    ):
        symbols = tuple(word)
        candidates = lexicon.candidates(symbols)
        assert word_pattern(symbols) == word_pattern(word)
        assert any(entry.word == word and entry.source == "cdbr-british-supplement" for entry in candidates)
