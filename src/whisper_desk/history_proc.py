"""Driving the history window (GTK3, system Python) from the command line.

The window is a view: this side reads and rewrites the history, copies,
asks the daemon to type a text again, writes the purge setting, and adds
the words a correction teaches to the vocabulary.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from . import config as config_module
from . import history, hotkey, output, vocabulary, window_proc

WINDOW_SCRIPT = Path(__file__).with_name("history_window.py")


class HistoryController:
    """Answers the window's requests; every answer is what it should show next."""

    def __init__(
        self,
        config: dict[str, Any],
        copy: Callable[[str], bool],
        send: Callable[..., dict[str, Any]],
    ):
        self.config = config
        self.copy = copy
        self.send = send

    def snapshot(self, status: str = "") -> dict[str, Any]:
        entries = [
            {"id": index, **asdict(entry)} for index, entry in enumerate(history.load())
        ]
        message: dict[str, Any] = {
            "entries": entries,
            "keep_days": int(self.config["output"]["history_days"]),
            "hint": hotkey.label(hotkey.resolve_binding(self.config)),
        }
        if status:
            message["status"] = status
        return message

    def _find(self, request: dict[str, Any]) -> history.Entry | None:
        """The entry the window meant — checked by its date, in case the file moved."""
        entries = history.load()
        index = request.get("id")
        if isinstance(index, int) and 0 <= index < len(entries):
            if entries[index].date == request.get("date"):
                return entries[index]
        for entry in entries:
            if entry.date == request.get("date"):
                return entry
        return None

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        action = request.get("action")
        if action == "keep_days":
            days = max(int(request.get("days", 0)), 0)
            config_module.update({"output": {"history_days": days}})
            self.config["output"]["history_days"] = days
            removed = history.purge(days)
            self._reload_daemon()
            status = "Dictations are kept forever" if days == 0 else (
                f"Dictations older than {days} days are deleted"
                + (f" — {removed} removed" if removed else "")
            )
            return self.snapshot(status)

        entry = self._find(request)
        if entry is None:
            return self.snapshot("This dictation is no longer in the history")
        if action == "copy":
            copied = self.copy(entry.text)
            return self.snapshot("Copied to the clipboard" if copied else "Could not copy")
        if action == "delete":
            deleted = history.delete(entry)
            return self.snapshot("Dictation deleted" if deleted else
                                 "This dictation is no longer in the history")
        if action == "correct":
            return self._correct(entry, str(request.get("text", "")),
                                 bool(request.get("learn", True)))
        if action == "insert":
            try:
                reply = self.send("insert", timeout=10, text=entry.text)
            except Exception as error:  # the daemon is down: the text is not lost
                reply = {"error": str(error)}
            if "error" in reply:
                self.copy(entry.text)
                output.notify(
                    "whisper-desk: the dictation was copied instead",
                    f"It could not be typed again ({reply['error']}).",
                )
            return None
        return None

    def _correct(self, entry: history.Entry, text: str, learn: bool) -> dict[str, Any]:
        text = text.strip()
        if not text:
            return self.snapshot("A dictation cannot be emptied — delete it instead")
        if text == entry.text:
            return self.snapshot("Nothing was changed")
        if not history.correct(entry, text):
            return self.snapshot("This dictation is no longer in the history")
        added = vocabulary.learn(entry.text, text, self.config, config_module.update) if learn else []
        if not added:
            return self.snapshot("Dictation corrected")
        self._reload_daemon()
        return self.snapshot(f"Dictation corrected — added to the vocabulary: {', '.join(added)}")

    def _reload_daemon(self) -> None:
        """The daemon keeps what it read: the purge limit, the vocabulary."""
        try:
            self.send("reload", timeout=10, autostart=False)
        except Exception:
            pass  # not running: it will read the file when it starts


def open_window(controller: HistoryController) -> int:
    """Shows the window until it is closed; returns the window's exit code."""
    return window_proc.run(WINDOW_SCRIPT, controller.snapshot(), controller.handle)
