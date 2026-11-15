"""What the settings window offers: every key of config.toml, by tab, and what it accepts.

Read by both sides of the window — settings_proc.py in the venv, and
settings_window.py with the system Python, which imports it as a neighbouring
script, like overlay_protocol.py: stdlib only, no relative import. The default
values are not repeated here: they come from config.DEFAULTS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_THRESHOLD = 32767

# Kinds with a widget of their own in the window.
SPECIAL = ("device", "shortcut", "replacements", "snippets")
TABLE_KINDS = ("replacements", "snippets")


@dataclass(frozen=True)
class Setting:
    field: str
    section: str
    key: str
    kind: str           # bool | int | float | text | choice | colour | threshold | paste | SPECIAL
    label: str
    help: str
    choices: str = ""   # the name of the list offered, for a choice
    minimum: float = 0
    maximum: float = 0
    step: float = 1
    unit: str = ""
    required: bool = False  # a text that cannot be blank

    @property
    def is_table(self) -> bool:
        return self.kind in TABLE_KINDS


@dataclass(frozen=True)
class Group:
    title: str
    settings: tuple[Setting, ...]


@dataclass(frozen=True)
class Tab:
    id: str
    title: str          # with its mnemonic: "_Dictation"
    groups: tuple[Group, ...]


def _s(field: str, where: str, kind: str, label: str, help: str, **extra: Any) -> Setting:
    section, _, key = where.partition(".")
    return Setting(field, section, key, kind, label, help, **extra)


TABS: tuple[Tab, ...] = (
    Tab("dictation", "_Dictation", (
        Group("Language and model", (
            _s("language", "model.language", "choice", "Language",
               "What you speak. “French and English” takes each sentence in whichever of the two it was said in.",
               choices="language"),
            _s("model", "model.name", "choice", "Model",
               "Larger models understand better and ask for more time and memory. "
               "A new model is downloaded once, in the background.",
               choices="model"),
            _s("style", "model.style", "choice", "Style",
               "Casual leaves the full stop out at the end, as in a chat message; "
               "very casual the capitals too.",
               choices="style"),
        )),
        Group("What is written", (
            _s("spoken_punctuation", "model.spoken_punctuation", "bool", "Spoken punctuation",
               "“Comma”, “question mark”, “new line” are written as the sign they name."),
            _s("hesitations", "model.hesitations", "bool", "Leave out hesitations",
               "“Um”, “euh” and a word said twice are dropped from the text."),
            _s("corrections", "model.corrections", "bool", "Spoken corrections",
               "“On Tuesday, no wait, on Wednesday” is written “on Wednesday”."),
            _s("lists", "model.lists", "bool", "Numbered lists",
               "“One, eggs, two, milk” becomes a list on lines of its own."),
            _s("developer_syntax", "model.developer_syntax", "bool", "Developer syntax",
               "“Camel case user name” is written userName; snake, kebab, pascal and constant case too."),
        )),
    )),
    Tab("microphone", "_Microphone", (
        Group("Microphone", (
            _s("device", "recording.device", "device", "Device",
               "The microphone to listen to. Press Test and speak: the gauge must move."),
            _s("backend", "recording.backend", "choice", "Capture tool",
               "The program that records the microphone. Automatic takes the first one this machine has.",
               choices="backend"),
        )),
        Group("Pauses and limits", (
            _s("streaming", "recording.streaming", "bool", "Insert sentence by sentence",
               "Each sentence is transcribed and inserted at a short pause, without stopping to listen."),
            _s("segment_silence_seconds", "recording.segment_silence_seconds", "float",
               "Pause between sentences",
               "How long a pause cuts a sentence, in seconds.",
               minimum=0.1, maximum=5.0, step=0.1, unit="s"),
            _s("silence_seconds", "recording.silence_seconds", "float", "Silence that ends the dictation",
               "Stops listening after this much silence, in seconds. 0 never stops by itself.",
               minimum=0.0, maximum=60.0, step=0.5, unit="s"),
            _s("start_timeout_seconds", "recording.start_timeout_seconds", "int", "Give up after",
               "Stops if nothing is said within this delay after the shortcut, in seconds.",
               minimum=1, maximum=120, unit="s"),
            _s("max_seconds", "recording.max_seconds", "int", "Longest dictation",
               "A dictation is cut off after this many seconds.",
               minimum=5, maximum=3600, step=5, unit="s"),
            _s("threshold", "recording.threshold", "threshold", "Voice threshold",
               "The volume from which you are heard: “auto”, or a number from 1 to 32767. "
               "Raise it in a noisy room."),
        )),
    )),
    Tab("output", "_Shortcut and output", (
        Group("Shortcut", (
            _s("binding", "hotkey.binding", "shortcut", "Start and stop",
               "Starts the dictation, stops it, then cuts it off. Change…, then press the new combination."),
            _s("hotkey_name", "hotkey.name", "text", "Name in the desktop",
               "How the shortcut is called in your desktop's keyboard settings.",
               required=True),
            _s("hotkey_action", "hotkey.action", "choice", "What the shortcut does",
               "One press starts listening, the next transcribes.",
               choices="hotkey_action"),
        )),
        Group("Output", (
            _s("mode", "output.mode", "choice", "The text",
               "Where the dictated text goes.",
               choices="mode"),
            _s("paste_shortcut", "output.paste_shortcut", "paste", "Paste shortcut",
               "The keys sent to paste the text: “auto”, or for instance ctrl+v or shift+insert."),
            _s("keyboard", "output.keyboard", "choice", "Way of pasting",
               "How that keystroke is sent. Automatic follows your system.",
               choices="keyboard"),
            _s("restore_clipboard", "output.restore_clipboard", "bool", "Give the clipboard back",
               "Your own clipboard is put back once the text is inserted."),
            _s("notify", "output.notify", "bool", "Notify every dictation",
               "A desktop notification for each transcription."),
        )),
    )),
    Tab("words", "_Words", (
        Group("Vocabulary", (
            _s("vocabulary", "model.vocabulary", "text", "Vocabulary",
               "Proper nouns, tools and jargon the model tends to mangle, separated by commas."),
        )),
        Group("Replacements", (
            _s("replacements", "replacements", "replacements", "Replacements",
               "A spelling the model keeps writing, and the one you mean: “mac os” is written “macOS” "
               "wherever it appears. Avoid words you also say for what they are."),
        )),
        Group("Snippets", (
            _s("snippets", "snippets", "snippets", "Snippets",
               "Say the cue, alone or inside a sentence, and its text is typed instead. "
               "Pick cues you would not say otherwise: “my home address”, not “thanks”."),
        )),
    )),
    Tab("overlay", "_Overlay", (
        Group("Overlay", (
            _s("overlay", "overlay.enabled", "bool", "Show the overlay",
               "The pill that shows the listening, and the text as it comes."),
            _s("position", "overlay.position", "choice", "Position",
               "Where the overlay appears on the screen.",
               choices="position"),
            _s("margin", "overlay.margin", "int", "Distance to the edge",
               "Between the overlay and the screen edge, in pixels.",
               minimum=0, maximum=1000, step=4, unit="px"),
            _s("accent", "overlay.accent", "colour", "Accent colour",
               "The colour of the equalizer and the progress."),
            _s("width", "overlay.width", "int", "Width",
               "Size of the pill, in pixels.",
               minimum=100, maximum=1000, step=4, unit="px"),
            _s("height", "overlay.height", "int", "Height",
               "Size of the pill, in pixels.",
               minimum=32, maximum=400, step=4, unit="px"),
            _s("bars", "overlay.bars", "int", "Equalizer bars",
               "How many bars the equalizer draws.",
               minimum=3, maximum=64),
        )),
    )),
    Tab("history", "_History", (
        Group("History", (
            _s("history", "output.history", "bool", "Keep a history",
               "Every dictation is kept on this machine: whisper-desk history."),
            _s("history_days", "output.history_days", "int", "Keep for",
               "Dictations older than this many days are dropped. 0 keeps them forever.",
               minimum=0, maximum=3650, unit="days"),
        )),
    )),
    Tab("advanced", "_Advanced", (
        Group("Transcription", (
            _s("model_device", "model.device", "choice", "Compute device",
               "Automatic uses the NVIDIA graphics card when there is one, the processor otherwise.",
               choices="compute_device"),
            _s("compute_type", "model.compute_type", "choice", "Precision",
               "Lighter is faster and takes less memory; heavier is a little more accurate.",
               choices="compute_type"),
            _s("beam_size", "model.beam_size", "int", "Beam size",
               "How many candidates the model weighs for each word: more is slower, slightly more accurate.",
               minimum=1, maximum=20),
            _s("initial_prompt", "model.initial_prompt", "text", "Priming sentence",
               "A sentence given to the model before it listens, to set the style or the subject."),
            _s("context", "model.context", "bool", "Remember the last sentence",
               "The end of what was just dictated is given back to the model, "
               "so a sentence cut by a pause keeps its context."),
            _s("preload", "model.preload", "bool", "Load the model at startup",
               "The first dictation is instant, at the price of the memory the model takes."),
        )),
    )),
    Tab("updates", "_Updates", (
        Group("Updates", (
            _s("updates", "update.auto_update", "choice", "New versions",
               "Checked once a day on GitHub — the only request whisper-desk makes. "
               "An update never interrupts a dictation.",
               choices="updates"),
        )),
    )),
)


def settings() -> list[Setting]:
    return [setting for tab in TABS for group in tab.groups for setting in group.settings]


def by_field() -> dict[str, Setting]:
    return {setting.field: setting for setting in settings()}


def layout() -> list[dict[str, Any]]:
    """The tabs as the window gets them, in JSON."""
    return [
        {
            "id": tab.id,
            "title": tab.title,
            "groups": [
                {
                    "title": group.title,
                    "settings": [
                        {name: getattr(setting, name) for name in setting.__dataclass_fields__}
                        for setting in group.settings
                    ],
                }
                for group in tab.groups
            ],
        }
        for tab in TABS
    ]


def check(setting: Setting | dict[str, Any], value: Any) -> tuple[Any, str]:
    """The value as it is written, and what is wrong with it: ("", message) if refused.

    `setting` is a Setting, or the dict the window got it as.
    """
    get = setting.get if isinstance(setting, dict) else lambda name: getattr(setting, name)
    kind, label = get("kind"), get("label")
    minimum, maximum, unit = get("minimum"), get("maximum"), get("unit")
    if kind == "bool":
        return bool(value), ""
    if kind in ("int", "float"):
        text = str(value).strip().replace(",", ".")
        try:
            number = float(text)
        except ValueError:
            return "", f"{label}: “{value}” is not a number"
        if kind == "int":
            if number != int(number):
                return "", f"{label}: “{value}” is not a whole number"
            number = int(number)
        bounds = f"{minimum:g} to {maximum:g}"
        if not minimum <= number <= maximum:
            return "", f"{label}: {number:g} is out of range ({bounds}{' ' + unit if unit else ''})"
        return number, ""
    if kind == "threshold":
        text = str(value).strip().lower()
        if text == "auto":
            return "auto", ""
        try:
            number = int(text)
        except ValueError:
            return "", f"{label}: “{value}” is neither “auto” nor a whole number"
        if not 1 <= number <= MAX_THRESHOLD:
            return "", f"{label}: {number} is out of range (1 to {MAX_THRESHOLD})"
        return number, ""
    if kind == "colour":
        text = str(value).strip()
        if not COLOUR.match(text):
            return "", f"The colour {text} is not of the form #rrggbb"
        return text, ""
    if kind == "paste":
        text = str(value).strip()
        parts = [part.strip() for part in text.split("+")]
        if not text or not all(parts):
            return "", f"{label}: write “auto”, or keys joined by +, such as ctrl+v"
        return text, ""
    text = str(value).strip()
    if not text and (kind in ("choice", "device", "shortcut") or get("required")):
        return "", f"{label}: " + ("pick one" if kind != "text" else "cannot be empty")
    return text, ""
