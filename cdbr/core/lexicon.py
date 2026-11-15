"""Explicit, ranked lexical sources for Codeword solving."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from wordfreq import iter_wordlist, zipf_frequency


SUPPLEMENTAL_BRITISH_WORDS = ("mercyproof",)


def word_pattern(values: Iterable[object]) -> tuple[int, ...]:
    seen: dict[object, int] = {}
    return tuple(seen.setdefault(value, len(seen)) for value in values)


@dataclass(frozen=True, kw_only=True)
class LexiconEntry:
    word: str
    score: float
    source: str


class Lexicon:
    def __init__(self, entries: Iterable[LexiconEntry]) -> None:
        best: dict[str, LexiconEntry] = {}
        for entry in entries:
            current = best.get(entry.word)
            if current is None or entry.score > current.score:
                best[entry.word] = entry
        index: dict[tuple[int, tuple[int, ...]], list[LexiconEntry]] = defaultdict(list)
        for entry in best.values():
            index[(len(entry.word), word_pattern(entry.word))].append(entry)
        self._index = {
            key: tuple(sorted(values, key=lambda item: (-item.score, item.word))) for key, values in index.items()
        }

    def candidates(self, symbols: tuple[int, ...]) -> tuple[LexiconEntry, ...]:
        return self._index.get((len(symbols), word_pattern(symbols)), ())


def _normalized_words(words: Iterable[str], source: str) -> Iterable[LexiconEntry]:
    for raw in words:
        text = raw.strip().upper()
        if any(not character.isalpha() and character not in " -'" for character in text):
            continue
        word = "".join(character for character in text if character.isalpha())
        if 2 <= len(word) <= 15 and word.isascii() and word.isalpha():
            yield LexiconEntry(
                word=word,
                score=zipf_frequency(word.lower(), "en"),
                source=source,
            )


def english_lexicon(
    *,
    system_dictionary: Path = Path("/usr/share/dict/words"),
    additional_wordlists: tuple[Path, ...] = (),
) -> Lexicon:
    """Build ranked English plus packaged British ESDB/SCOWL vocabulary."""

    entries = list(_normalized_words(iter_wordlist("en"), "wordfreq-3.1.1"))
    british = files("cdbr").joinpath("assets/lexicon/en_GB_70.txt")
    entries.extend(
        _normalized_words(
            british.read_text(encoding="utf-8").splitlines(),
            "ESDB/SCOWL-2026.02.25-en_GB-70",
        )
    )
    entries.extend(_normalized_words(SUPPLEMENTAL_BRITISH_WORDS, "cdbr-british-supplement"))
    if system_dictionary.is_file():
        entries.extend(
            _normalized_words(
                system_dictionary.read_text(errors="ignore").splitlines(),
                str(system_dictionary),
            )
        )
    for wordlist in additional_wordlists:
        if wordlist.is_file():
            entries.extend(
                _normalized_words(
                    wordlist.read_text(errors="ignore").splitlines(),
                    str(wordlist),
                )
            )
    return Lexicon(entries)
