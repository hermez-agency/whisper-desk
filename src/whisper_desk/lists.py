"""Numbered lists said aloud: "un, des œufs, deux, du lait" is written as a list."""

from __future__ import annotations

import re

from .punctuation import join

# Markers that number an item on their own: no pause needed after them.
_ORDINALS: dict[str, int] = {
    "premièrement": 1, "deuxièmement": 2, "secondement": 2, "troisièmement": 3,
    "quatrièmement": 4, "cinquièmement": 5, "sixièmement": 6, "septièmement": 7,
    "huitièmement": 8, "neuvièmement": 9, "dixièmement": 10,
    "primo": 1, "secundo": 2, "secondo": 2, "tertio": 3, "quarto": 4,
    "firstly": 1, "secondly": 2, "thirdly": 3, "fourthly": 4, "fifthly": 5,
    "sixthly": 6, "seventhly": 7, "eighthly": 8, "ninthly": 9, "tenthly": 10,
}
# Markers that are ordinary words too: an item number for certain only when the
# speaker paused right after them — the comma or full stop Whisper writes for it.
_WORDS: dict[str, int] = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
    "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
_FRENCH = {
    "premièrement", "deuxièmement", "secondement", "troisièmement", "quatrièmement",
    "cinquièmement", "sixièmement", "septièmement", "huitièmement", "neuvièmement",
    "dixièmement", "un", "une", "deux", "trois", "quatre", "cinq", "sept", "huit",
    "neuf", "dix", "numéro", "primo", "secundo", "secondo", "tertio", "quarto",
}
_NUMBER = "numéro|number|n°"
_MARKER = re.compile(
    rf"(?<![\w'’-])(?i:(?P<number>{_NUMBER})\s+)?"
    rf"(?P<word>(?i:{'|'.join(sorted(set(_ORDINALS) | set(_WORDS), key=len, reverse=True))})"
    r"|[0-9]{1,2})(?![\w'’])"
    r"(?P<pause>\s*[,.:)](?![0-9]))?"
)
# A word that runs one item into the next: "du lait et deux, du pain".
_LINKS = {"et", "puis", "ensuite", "and", "then"}
# Words that tell a French intro apart, for the space before its colon.
_FRENCH_WORDS = {
    "le", "la", "les", "des", "du", "de", "et", "à", "je", "il", "on", "nous", "vous",
    "pour", "est", "sont", "faut", "choses", "voici", "points", "étapes",
}
_ITEM_LINE = re.compile(r"(?:^|\n)(?P<number>[0-9]+)\. [^\n]*$")
_SENTENCE_END = re.compile(r"(?:[.!?]|(?=\n))\s+(?=\S)")


def _value(match: re.Match[str]) -> int:
    word = match["word"].lower()
    return int(word) if word.isdigit() else _ORDINALS.get(word) or _WORDS[word]


def _sure(match: re.Match[str]) -> bool:
    """Whether the marker numbers an item for certain, or only maybe.

    "un des œufs, deux du lait": Whisper does not always write the pause after
    the number, and without it "un" may just as well be an article.
    """
    word = match["word"].lower()
    return bool(match["pause"] or match["number"]) or word in _ORDINALS


def _figure(text: str, match: re.Match[str]) -> bool:
    """"Ordre du jour 1. Le bilan": a figure Whisper wrote as an item number."""
    return (
        match["word"].isdigit()
        and (match["pause"] or "").strip() in (".", ")")
        and text[match.end():].lstrip(" ")[:1].isupper()
    )


def _boundary(text: str, index: int) -> bool:
    """Whether a marker at `index` opens a clause: a list item can start there."""
    before = text[:index].rstrip(" ")
    if not before or before[-1] in ".,;:!?\n":
        return True
    words = re.findall(r"[\w'’]+", before)
    return bool(words) and words[-1].lower() in _LINKS


def _markers(text: str, sure: bool = False) -> list[tuple[int, re.Match[str], bool]]:
    """The item numbers of the text: value, where it is, and whether for certain."""
    found = []
    for match in _MARKER.finditer(text):
        if _figure(text, match):
            found.append((_value(match), match, True))
        elif _boundary(text, match.start()):
            certain = _sure(match)
            if certain or not sure:
                found.append((_value(match), match, certain))
    return found


def _sequence(text: str, start: int, maybe: bool = False) -> list[re.Match[str]]:
    """The markers numbering start, start + 1… in order, each item said.

    A list numbered by markers that are maybe only words ("un des œufs") needs
    three items, unless `maybe` says the list is already under way.
    """
    markers = _markers(text)
    for index, (value, first, certain) in enumerate(markers):
        if value != start:
            continue
        chosen, sure = [first], certain
        for later_value, later, later_certain in markers[index + 1:]:
            if later_value == start + len(chosen):
                chosen.append(later)
                sure = sure and later_certain
        if not (sure or maybe or len(chosen) >= 3):
            continue
        ends = [m.start() for m in chosen[1:]] + [len(text)]
        if all(re.search(r"\w", _clean(text[m.end():end])) for m, end in zip(chosen, ends)):
            return chosen
    return []


def _clean(item: str) -> str:
    """An item without the pause, link or full stop around it."""
    item = item.strip().rstrip(",;. ")
    words = item.rsplit(None, 1)
    if len(words) == 2 and words[1].lower() in _LINKS:
        item = words[0].rstrip(",;. ")
    return item.lstrip(",;:. ")


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _french(text: str, markers: list[re.Match[str]]) -> bool:
    for marker in markers:
        word = (marker["number"] or marker["word"]).lower()
        if not word.isdigit():
            return word in _FRENCH
    words = set(re.findall(r"\w+", text.lower()))
    return bool(words & _FRENCH_WORDS or re.search(r"[àâçéèêëîïôûù]", text, re.I))


def _continued(before: str) -> int:
    """The number of the list item `before` ends on, 0 if it ends on none."""
    line = _ITEM_LINE.search(before)
    return int(line["number"]) if line else 0


def _continuation(text: str, last: int) -> list[re.Match[str]]:
    """The markers going on with a list ended on item `last`, from the text's start."""
    markers = _sequence(text, last + 1, maybe=True) if last else []
    if markers and text[:markers[0].start()].strip(" ,"):
        return []
    return markers


def apply(text: str, before: str = "") -> str:
    """The text with a numbered list said aloud written as one.

    `before` is what the dictation already inserted: a list it ends on goes on
    with the next number, and a sentence that is no item leaves it on a new line.
    """
    last = _continued(before)
    markers = _continuation(text, last)
    if not markers:
        markers = _sequence(text, 1)
        if len(markers) < 2:
            markers = []
        elif last:
            last = 0
    if not markers:
        if last and text[:1].isupper():
            return "\n" + text
        return text

    intro = text[:markers[0].start()].strip().rstrip(",;")
    if intro and intro[-1] not in ".:!?":
        intro += (" :" if _french(intro, markers) else ":")
    ends = [m.start() for m in markers[1:]] + [len(text)]
    items = [text[m.end():end] for m, end in zip(markers, ends)]
    rest = ""
    sentence_end = _SENTENCE_END.search(items[-1])
    if sentence_end:
        rest = items[-1][sentence_end.end():].strip()
        items[-1] = items[-1][:sentence_end.end()]
    lines = [
        f"{last + number}. {_capital(_clean(item))}" for number, item in enumerate(items, 1)
    ]
    out = "\n".join(lines)
    if intro:
        out = intro + "\n" + out
    elif before and not before.endswith("\n"):
        out = "\n" + out
    if rest:
        out += "\n" + _capital(rest)
    return out


def opens(text: str, before: str = "") -> bool:
    """Whether the text may be the start of a list whose next item is yet to come."""
    if _continuation(text, _continued(before)) or len(_sequence(text, 1)) >= 2:
        return False
    return any(value == 1 for value, _, _ in _markers(text, sure=True))


class Pending:
    """The sentences held back while a list may be starting.

    The as-you-go dictation inserts each sentence after a short pause: "un, des
    œufs" would be at the cursor before "deux, du lait" says it was a list. A
    sentence that may open one waits for the next, and no longer.
    """

    MAX_HELD = 2

    def __init__(self) -> None:
        self.held: list[str] = []

    def feed(self, text: str, before: str) -> str | None:
        """What to insert now that `text` was said, None while it is held back."""
        self.held.append(text)
        said = join(self.held)
        if opens(said, before) and len(self.held) < self.MAX_HELD:
            return None
        self.held = []
        return apply(said, before)

    def flush(self) -> str:
        """What was held back, as it was said: the list never came."""
        text, self.held = join(self.held), []
        return text
