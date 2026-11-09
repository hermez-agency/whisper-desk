"""Personal dictionary: the words a corrected dictation teaches the vocabulary.

Wispr Flow adds to its dictionary the words you correct. Here the correction
is made in the history; the words it brings that Whisper could not have
guessed — names, jargon, a word it heard as another — join `vocabulary`, the
hotwords pushed into the decoder for every sentence. A grammar fix ("mange"
-> "manges", "a" -> "à") or a word Whisper merely left out teaches nothing.

A name the vocabulary already held and Whisper still wrote wrong is beyond
what the hotwords can do: the correction saves what it wrote and the name as
a replacement ("Opal" -> "Opoil"), Wispr Flow's "Correct a misspelling".
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections.abc import Callable
from typing import Any

from . import replacements

# Inner dots, dashes and signs belong to the word: "Node.js", "faster-whisper", "C++".
WORD = re.compile(r"\w(?:[\w'’.+#-]*[\w+#])?")
# The article or pronoun elided before a word, and the English possessive after it:
# "d'Animalink" and "Animalink's" teach "Animalink".
ELIDED = re.compile(r"^(?:[cdjlmnst]|qu)['’](?=\w)", re.IGNORECASE)
POSSESSIVE = re.compile(r"(?<=\w\w)['’]s$")
# A replaced run longer than this is a sentence rewritten, not a word misheard:
# only its names and jargon are learned.
SHORT_RUN = 3
# Plain lowercase words shorter than this are grammar ("des", "have", "were").
MIN_PLAIN = 5
# A plain word misheard sounds like the one written instead — "ripos" for
# "repos" —, a word less alike is the user changing their mind.
ALIKE = 0.5
# What Whisper wrote for a name is saved as a replacement only when it is made
# of plain words: the replacement matches them spaced or hyphenated, never
# across a dot or a sign.
PLAIN = re.compile(r"\w+(?:['’-]\w+)*")
# Fewer letters than this ("a", "I", "un") is grammar the replacement would
# rewrite everywhere.
MIN_MISHEARD = 3
# Below this likeness, what was written was said: "OVH" corrected into
# "Scaleway" is a change of mind, not a name misheard ("Tory" -> "Tauri": 0.44).
SOUNDS_LIKE = 0.4


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _words(text: str) -> list[tuple[str, bool]]:
    """Each word, and whether a sentence starts with it (its capital tells nothing)."""
    found = []
    for match in WORD.finditer(text):
        word = POSSESSIVE.sub("", match.group())
        elided = ELIDED.match(word)
        if elided:
            found.append((word[elided.end():], False))
            continue
        before = text[: match.start()].rstrip(" \t\"'«»“”(")
        found.append((word, not before or before[-1] in ".!?:\n"))
    return found


def _marked(word: str, starts: bool) -> bool:
    """A name or jargon: a capital a sentence start does not explain, a digit, a sign."""
    # A dash is French as much as jargon: "après-midi", "rendez-vous".
    if any(char.isdigit() or not (char.isalpha() or char in "'’-") for char in word):
        return True
    capitals = [char for char in word[1:] if char.isupper()]
    return bool(capitals) or (word[0].isupper() and not starts)


def _inflected(word: str, other: str) -> bool:
    """The same word with another ending: an agreement, a tense, not a mishearing."""
    a, b = fold(word), fold(other)
    common = len(_prefix(a, b))
    return common >= 3 and common >= max(len(a), len(b)) - 3


def _alike(word: str, replaced: list[str]) -> bool:
    """Heard as one of the words it replaces, or as all of them run together."""
    return any(difflib.SequenceMatcher(None, fold(word), fold(other)).ratio() >= ALIKE
               for other in [*replaced, "".join(replaced)])


def _prefix(a: str, b: str) -> str:
    return a[: next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))]


def learned(before: str, after: str) -> list[str]:
    """The words of `after` worth adding to the vocabulary, in their order."""
    old, new = _words(before), _words(after)
    matcher = difflib.SequenceMatcher(None, [w for w, _ in old], [w for w, _ in new],
                                      autojunk=False)
    found: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag not in ("replace", "insert"):
            continue
        replaced = [w for w, _ in old[i1:i2]]
        short = tag == "replace" and max(i2 - i1, j2 - j1) <= SHORT_RUN
        for word, starts in new[j1:j2]:
            if word in replaced:
                continue
            if any(fold(word) == fold(other) for other in replaced):
                # Only the case or the accents changed: a name given its capital.
                keep = _marked(word, starts)
            elif _marked(word, starts):
                keep = True
            else:
                # An elision is grammar too: "they're", "c'est", "j'appelle".
                keep = (short and len(word) >= MIN_PLAIN and not set("'’") & set(word)
                        and _alike(word, replaced)
                        # "Hermes" -> "Hermez" is a name spelt, not an agreement.
                        and (word[0].isupper()
                             or not any(_inflected(word, other) for other in replaced)))
            if keep and fold(word) not in {fold(w) for w in found}:
                found.append(word)
    return found


def entries(vocabulary: str) -> list[str]:
    return [term.strip() for term in vocabulary.split(",") if term.strip()]


def merge(vocabulary: str, words: list[str]) -> tuple[str, list[str]]:
    """The vocabulary with the words it lacks added at the end, and those words."""
    terms = entries(vocabulary)
    known = {fold(term) for term in terms}
    added = []
    for word in words:
        if fold(word) not in known:
            known.add(fold(word))
            added.append(word)
    if not added:
        return vocabulary, []
    return ", ".join(terms + added), added


def learn(before: str, after: str, config: dict[str, Any], save: Callable[[dict[str, Any]], None]) -> list[str]:
    """Adds what the correction teaches to config["model"]["vocabulary"].

    `save` writes the changes to config.toml (config.update); the words are
    returned so that the user is told what was learned.
    """
    vocabulary, added = merge(str(config["model"]["vocabulary"]), learned(before, after))
    if added:
        save({"model": {"vocabulary": vocabulary}})
        config["model"]["vocabulary"] = vocabulary
    return added


def _within(words: list[str], others: list[str]) -> bool:
    """`words` found in a row inside `others`: replacing them would repeat them."""
    a, b = [fold(w) for w in words], [fold(w) for w in others]
    return any(b[i:i + len(a)] == a for i in range(len(b) - len(a) + 1))


def _replaceable(heard: list[str], meant: list[str], terms: list[str]) -> bool:
    whole = {fold(term) for term in terms}
    if fold(" ".join(heard)) == fold(" ".join(meant)):
        # A whole term given the case or accents it lacked: "hermez" -> "Hermez".
        # Not a word of a longer one: "link" would become "Link" everywhere.
        return fold(" ".join(meant)) in whole
    # A term of the vocabulary is never replaced by another.
    if fold(" ".join(heard)) in whole or any(fold(w) in whole for w in heard) or _within(heard, meant):
        return False
    # An ordinary word put for another ("pool" -> "pull") is right elsewhere;
    # words run together ("middle where" -> "middleware") are not.
    if len(heard) <= len(meant) and all(w.isalpha() and w.islower() for w in meant):
        return False
    said, written = ("".join(fold(w) for w in words) for words in (heard, meant))
    return difflib.SequenceMatcher(None, said, written).ratio() >= SOUNDS_LIKE


def misheard(before: str, after: str, vocabulary: str) -> list[tuple[str, str]]:
    """What Whisper wrote for the names `vocabulary` already held, and those names.

    Only the runs of a few words corrected into words all in the vocabulary
    count: the hotwords did not suffice for them.
    """
    terms = entries(vocabulary)
    known = {fold(term) for term in terms} | {fold(w) for term in terms for w, _ in _words(term)}
    old, new = _words(before), _words(after)
    matcher = difflib.SequenceMatcher(None, [w for w, _ in old], [w for w, _ in new],
                                      autojunk=False)
    found: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "replace" or max(i2 - i1, j2 - j1) > SHORT_RUN:
            continue
        heard, meant = [w for w, _ in old[i1:i2]], [w for w, _ in new[j1:j2]]
        if not (fold(" ".join(meant)) in known or all(fold(w) in known for w in meant)):
            continue
        if (not all(PLAIN.fullmatch(w) for w in heard)
                or sum(map(len, heard)) < MIN_MISHEARD
                or not _replaceable(heard, meant, terms)):
            continue
        pair = (" ".join(heard), " ".join(meant))
        if pair not in found:
            found.append(pair)
    return found


def learn_spellings(before: str, after: str, config: dict[str, Any],
                    save: Callable[[dict[str, Any]], None]) -> dict[str, str]:
    """Adds to config["replacements"] the misspellings the correction shows.

    Called before `learn`, against the vocabulary the dictation was made
    with. An entry already there for the misspelling — one switched off by
    hand too — is left alone. `save` writes the whole [replacements] section;
    the entries added are returned so that the user is told.
    """
    table = config["replacements"]
    keys = {replacements.misspelling_key(key) for key in table}
    added: dict[str, str] = {}
    for heard, meant in misheard(before, after, str(config["model"]["vocabulary"])):
        key = replacements.misspelling_key(heard)
        if key and key not in keys:
            keys.add(key)
            added[heard] = meant
    if added:
        table = {**table, **added}
        save(table)
        config["replacements"] = table
    return added
