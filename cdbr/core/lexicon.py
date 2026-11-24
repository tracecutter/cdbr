"""Explicit, ranked lexical sources for Codeword solving."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from wordfreq import iter_wordlist, zipf_frequency


# Publisher-confirmed solution words absent from the packaged British wordlist.
# Keep this small, explicit, and backed by the approved solution corpus.
SUPPLEMENTAL_BRITISH_WORDS = (
    "beetleoff",
    "bullyoff",
    "chewthefat",
    "czechrepublic",
    "elmiest",
    "frizzliest",
    "jumpthegun",
    "lockhorns",
    "lookdownon",
    "mercyproof",
    "nohit",
    "oxfordblue",
    "shemozzle",
    "tuckbox",
)


def word_pattern(values: Iterable[object]) -> tuple[int, ...]:
    seen: dict[object, int] = {}
    return tuple(seen.setdefault(value, len(seen)) for value in values)


@dataclass(frozen=True, kw_only=True)
class LexiconEntry:
    word: str
    score: float
    source: str


class Lexicon:
    def __init__(self, entries: Iterable[LexiconEntry], *, discouraged: Iterable[str] = ()) -> None:
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
        by_length: dict[int, list[LexiconEntry]] = defaultdict(list)
        for entry in best.values():
            by_length[len(entry.word)].append(entry)
        self._by_length = {
            length: tuple(sorted(values, key=lambda item: (-item.score, item.word)))
            for length, values in by_length.items()
        }
        by_position: dict[tuple[int, int, str], list[LexiconEntry]] = defaultdict(list)
        for entry in best.values():
            for position, letter in enumerate(entry.word):
                by_position[(len(entry.word), position, letter)].append(entry)
        self._by_position = {
            key: tuple(sorted(values, key=lambda item: (-item.score, item.word))) for key, values in by_position.items()
        }
        self._entries = tuple(best.values())
        self._discouraged = frozenset(discouraged)

    def candidates(self, symbols: tuple[int, ...]) -> tuple[LexiconEntry, ...]:
        return self._index.get((len(symbols), word_pattern(symbols)), ())

    def entries(self, length: int) -> tuple[LexiconEntry, ...]:
        """Return words of *length*, ranked from familiar to obscure."""

        return self._by_length.get(length, ())

    def matching(self, pattern: tuple[str | None, ...]) -> tuple[LexiconEntry, ...]:
        """Return ranked words matching the letters fixed in *pattern*."""

        fixed = tuple((position, letter) for position, letter in enumerate(pattern) if letter is not None)
        if not fixed:
            return self.entries(len(pattern))
        position, letter = min(
            fixed,
            key=lambda item: len(self._by_position.get((len(pattern), item[0], item[1]), ())),
        )
        candidates = self._by_position.get((len(pattern), position, letter), ())
        return tuple(entry for entry in candidates if all(entry.word[index] == expected for index, expected in fixed))

    def extended(self, entries: Iterable[LexiconEntry]) -> Lexicon:
        """Return a lexicon containing these entries as well as the current vocabulary."""

        return Lexicon((*self._entries, *entries), discouraged=self._discouraged)

    def discouraged(self, word: str) -> bool:
        """Return whether *word* is unsuitable as unrequested puzzle filler."""

        return word in self._discouraged


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
    british_words = british.read_text(encoding="utf-8").splitlines()
    entries.extend(
        _normalized_words(
            british_words,
            "ESDB/SCOWL-2026.02.25-en_GB-70",
        )
    )
    # Human-confirmed publisher answers are evidence that these uncommon words
    # and closed-up phrases are plausible puzzle fill.  Give them a modest
    # score floor so an identical, low-frequency packaged entry does not win
    # merely because it was loaded first.
    entries.extend(
        LexiconEntry(
            word=word.upper(),
            score=max(zipf_frequency(word, "en"), 4.0),
            source="cdbr-british-supplement",
        )
        for word in SUPPLEMENTAL_BRITISH_WORDS
    )
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
    lowercase = {word.strip() for word in british_words if word.strip().islower()}
    proper_only = {
        "".join(character for character in word.strip().upper() if character.isalpha())
        for word in british_words
        if word.strip()[:1].isupper() and word.strip().lower() not in lowercase
    }
    return Lexicon(entries, discouraged=proper_only)
