"""Writing styles: how formally a dictation is capitalised and punctuated.

Wispr Flow's Styles, rebuilt by rules: "formal" writes the text as Whisper
punctuates it; "casual" drops the full stop that ends the dictation, as in a
chat message; "very_casual" drops it too and writes the sentences without the
capital they open on.
"""

from __future__ import annotations

import re
from typing import Any

from . import focus
from .punctuation import separator

STYLES = ("formal", "casual", "very_casual")
DEFAULT = "formal"
# A kind of app whose style is the general one: Wispr Flow's "Other".
SAME = "same"

# Wispr Flow's app categories, filled in as it does: the names a messaging or
# mail app goes by on Linux (X11 class, Flatpak id's last part), macOS
# (process name) and Windows (process name), compared as focus.key does.
CATEGORIES: dict[str, frozenset[str]] = {
    "personal": frozenset({
        "whatsapp", "whatsappforlinux", "whatsdesk", "zapzap", "signal", "signaldesktop",
        "telegram", "telegramdesktop", "orgtelegramdesktop", "discord", "vesktop",
        "messenger", "caprine", "messages", "element", "riot", "beeper", "threema",
    }),
    "work": frozenset({
        "slack", "teams", "msteams", "microsoftteams", "teamsforlinux", "mattermost",
        "mattermostdesktop", "zulip", "rocketchat", "webex", "lark", "feishu",
    }),
    "email": frozenset({
        "thunderbird", "betterbird", "evolution", "geary", "mail", "outlook",
        "microsoftoutlook", "olk", "mailspring", "spark", "sparkdesktop", "airmail",
        "kmail", "kmail2", "clawsmail", "mimestream", "canarymail", "mailclient", "postbox",
    }),
}

# Words a full stop follows without ending the sentence: it is part of them.
_ABBREVIATIONS = {
    "m", "mm", "mme", "mmes", "mlle", "mlles", "dr", "pr", "st", "ste", "etc", "cf",
    "ex", "mr", "mrs", "ms", "jr", "sr", "vs", "inc", "ltd", "e.g", "i.e",
}
# English "I" and its contractions are written with a capital anywhere.
_ALWAYS_CAPITAL = re.compile(r"^I(?:['’](?:m|ll|ve|d|s))?$")
# The word a sentence opens on: at the start, after a sentence's end, after a
# line break — past the quote or bracket closed after it, an opening one, and
# a list item's number or bullet.
_SENTENCE_START = re.compile(
    r"(?:\A|(?:(?<=[.!?…])|(?<=[.!?…][»\"”)\]}])|(?<=[.!?…] »))[ \t]+|\n)"
    r"[ \t«\"“([{]*(?:(?:\d+\.|-)[ \t]+)?(?P<word>[^\W\d_][\w'’.-]*)"
)
_LAST_WORD = re.compile(r"([\w'’.-]*)\.\Z")


def normalise(value: Any) -> str:
    """A style as written by hand — "Very casual" — in its configuration name, or ""."""
    value = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    return value if value in STYLES else ""


def category(apps: list[str]) -> str:
    """The kind of app in front — "personal", "work", "email" — or "" for any other."""
    names = {focus.key(name) for name in apps} - {""}
    return next((kind for kind, known in CATEGORIES.items() if names & known), "")


def category_styles(config: dict[str, Any]) -> dict[str, str]:
    """The categories given a style of their own, other than the general one."""
    model = config["model"]
    return {
        kind: normalise(model.get(f"{kind}_style", SAME))
        for kind in CATEGORIES
        if normalise(model.get(f"{kind}_style", SAME))
    }


def per_app(config: dict[str, Any]) -> bool:
    """Whether the app in front can change the style: worth asking the desktop."""
    return bool(config.get("app_styles")) or bool(category_styles(config))


def for_app(config: dict[str, Any], apps: list[str]) -> str:
    """The style set for the application in front (any of its names), or "".

    An app listed by name wins over its category: Slack can stay formal
    while the other work chats are casual.
    """
    names = {focus.key(name) for name in apps} - {""}
    for app, value in config.get("app_styles", {}).items():
        if isinstance(value, str) and focus.key(app) in names and normalise(value):
            return normalise(value)
    return category_styles(config).get(category(apps), "")


def resolve(config: dict[str, Any], apps: list[str] | None = None) -> str:
    """The style of the app in front, else the configured one; formal when unknown, as before styles."""
    return for_app(config, apps or []) or normalise(config["model"].get("style", DEFAULT)) or DEFAULT


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
