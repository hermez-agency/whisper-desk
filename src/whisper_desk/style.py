"""Writing styles: how formally a dictation is capitalised and punctuated.

Wispr Flow's Styles, rebuilt by rules: "formal" writes the text as Whisper
punctuates it; "casual" drops the full stop that ends the dictation, as in a
chat message; "very_casual" drops it too and writes the sentences without the
capital they open on.
"""

from __future__ import annotations

import re
from typing import Any

from .punctuation import separator

STYLES = ("formal", "casual", "very_casual")
DEFAULT = "formal"

# Words a full stop follows without ending the sentence: it is part of them.
_ABBREVIATIONS = {
    "m", "mm", "mme", "mmes", "mlle", "mlles", "dr", "pr", "st", "ste", "etc", "cf",
    "ex", "mr", "mrs", "ms", "jr", "sr", "vs", "inc", "ltd", "e.g", "i.e",
}
# English "I" and its contractions are written with a capital anywhere.
_ALWAYS_CAPITAL = re.compile(r"^I(?:['’](?:m|ll|ve|d|s))?$")
# The word a sentence opens on: at the start, after a sentence's end, after a
# line break — past the quote or bracket closed after it, an opening one, and
# a list item's number.
_SENTENCE_START = re.compile(
    r"(?:\A|(?:(?<=[.!?…])|(?<=[.!?…][»\"”)])|(?<=[.!?…] »))[ \t]+|\n)"
    r"[ \t«\"“(]*(?:\d+\.[ \t]+)?(?P<word>[^\W\d_][\w'’.-]*)"
)
_LAST_WORD = re.compile(r"([\w'’.-]*)\.\Z")


def resolve(config: dict[str, Any]) -> str:
    """The configured style; an unknown one is the formal style, as before styles."""
    value = str(config["model"].get("style", DEFAULT)).strip().lower().replace(" ", "_")
    return value if value in STYLES else DEFAULT


def names(config: dict[str, Any]) -> set[str]:
    """The words whose capital is the user's spelling, not a sentence's start."""
    terms = [term for term in str(config["model"].get("vocabulary", "")).split(",")]
    terms += [value for value in config.get("replacements", {}).values() if isinstance(value, str)]
    return {word for term in terms for word in term.split() if word[:1].isupper()}


def _abbreviation(word: str) -> bool:
    """A full stop after this word belongs to it: "M.", "etc.", an initial."""
    word = word.lower()
    return word in _ABBREVIATIONS or (len(word) == 1 and word.isalpha())


def _kept(word: str, keep: set[str]) -> bool:
    """A capital that is not a sentence's: a name, an acronym, "I", "GitHub"."""
    bare = word.rstrip(".")
    return (
        bare in keep
        or bool(_ALWAYS_CAPITAL.match(bare))
        or any(letter.isupper() for letter in bare[1:])
    )


def lower_starts(text: str, keep: set[str] = frozenset()) -> str:
    """The text with the sentences opening on a small letter, names left alone."""
    out = []
    position = 0
    for match in _SENTENCE_START.finditer(text):
        word = match["word"]
        start = match.start("word")
        if not word[0].isupper() or _kept(word, keep):
            continue
        before = _LAST_WORD.search(text[:match.start()].rstrip(" \t"))
        if before and _abbreviation(before[1]):
            continue
        out.append(text[position:start])
        out.append(word[0].lower())
        position = start + 1
    out.append(text[position:])
    return "".join(out)


def hold_full_stop(text: str) -> tuple[str, str]:
    """The text without the full stop it ends on, and that full stop ("" if none).

    An ellipsis, an abbreviation's or an initial's full stop stays: they say
    something the end of a message does not make plain.
    """
    end = _LAST_WORD.search(text)
    if not end or text.endswith("..") or _abbreviation(end[1]) or not end[1]:
        return text, ""
    return text[:-1], "."


def rejoin(held: str, text: str) -> str:
    """The full stop held back from the last sentence, put back before the next one.

    A sentence that opens on a mark of its own ("Virgule, …" said after a pause)
    takes the place of the full stop.
    """
    if not held or not text or text[0] in ",;:.!?…)":
        return text
    return held + separator(held, text) + text
