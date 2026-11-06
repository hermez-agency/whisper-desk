"""Replacements: a spelling Whisper keeps writing is swapped for the one meant."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("whisper-desk.replacements")

# A word keeps its inner apostrophe: "don't" is one word, to be replaced whole.
_WORD = re.compile(r"\w+(?:['’]\w+)*")
# Whisper writes a two-word name spaced or hyphenated: "Mac OS", "mac-os".
_GAP = r"[\s-]+"


def _words(text: str) -> list[str]:
    return [word.casefold().replace("’", "'") for word in _WORD.findall(text)]


def misspelling_key(text: str) -> str:
    """What a misspelling comes down to: two with the same key are one entry."""
    return " ".join(_words(text))


def _pattern(key: str) -> str:
    return _GAP.join(re.escape(word).replace("'", "['’]") for word in key.split())


class Replacements:
    """The entries of a [replacements] section, compiled into one pattern."""

    def __init__(self, table: dict[str, Any]):
        self.spellings: dict[str, str] = {}
        for misspelling, spelling in table.items():
            if not isinstance(spelling, str):
                logger.warning("Replacement %r ignored: its spelling is not a string.",
                               misspelling)
                continue
            key, spelling = misspelling_key(misspelling), spelling.strip()
            # An empty spelling is how an entry is switched off without losing it.
            if key and spelling:
                self.spellings[key] = spelling
        # The longest misspelling first: "mac os x" wins over "mac os".
        keys = sorted(self.spellings, key=lambda k: (-len(k.split()), -len(k)))
        # Never inside a word, nor before the "'t" of a contraction: "can" is
        # not in "can't" — but "animal link's" is a possessive to keep.
        self.pattern = re.compile(
            rf"(?<!\w)(?:{'|'.join(map(_pattern, keys))})(?!\w)(?!['’]t\b)",
            re.IGNORECASE,
        ) if keys else None

    def _spelling(self, match: re.Match[str]) -> str:
        spelling = self.spellings[misspelling_key(match.group())]
        # A spelling saved in lowercase is an ordinary word: it takes the
        # capital Whisper gave a sentence start ("Don't" -> "Do not"). One
        # with a capital of its own is written exactly so: "macOS", "iPhone".
        if spelling.islower() and match.group()[0].isupper():
            return spelling[0].upper() + spelling[1:]
        return spelling

    def apply(self, text: str) -> str:
        """The text with every misspelling replaced by its spelling."""
        if self.pattern is None:
            return text
        return self.pattern.sub(self._spelling, text)


def apply(text: str, table: dict[str, Any]) -> str:
    """The text with the entries of `table` (misspelling -> spelling) applied."""
    return Replacements(table).apply(text)
