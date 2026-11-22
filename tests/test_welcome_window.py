"""The welcome window: in the Hermez look, and done without the mouse."""

from __future__ import annotations

import importlib.util
import re
import unittest

from . import context  # noqa: F401

WINDOW = context.SOURCE / "whisper_desk" / "welcome_window.py"
# Hermez orange and its two shades, the stone greys, white on the orange button.
PALETTE = {"#e46212", "#c2500c", "#f07a2b", "#78716c", "#a8a29e", "#ffffff"}


def css() -> str:
    """The window's style sheet, read from its source: no GTK needed."""
    source = WINDOW.read_text(encoding="utf-8")
    match = re.search(r'^CSS = f"""(.*?)^"""', source, re.S | re.M)
    if match is None:
        raise AssertionError("welcome_window.py has no CSS block")
    return match.group(1).replace("{ACCENT}", "#e46212")


def rule(selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{\{(.*?)\}\}", css(), re.S)
    if match is None:
        raise AssertionError(f"no rule for {selector}")
    return match.group(1)


class LookTest(unittest.TestCase):
    def test_next_is_hermez_orange_not_the_theme_colour(self):
        button = rule("button.suggested-action")
        self.assertIn("background-color: #e46212", button)
        self.assertIn("background-image: none", button)

    def test_headlines_are_in_bricolage_grotesque(self):
        self.assertIn('"Bricolage Grotesque"', rule(".headline"))
        self.assertIn('"Bricolage Grotesque"', rule(".brand"))

    def test_the_focus_shows_in_orange(self):
        self.assertIn("outline-color: #e46212", rule("button:focus, textview:focus"))

    def test_no_colour_outside_the_hermez_palette(self):
        colours = {colour.lower() for colour in re.findall(r"#[0-9a-fA-F]{6}\b", css())}
        self.assertLessEqual(colours, PALETTE)


def load_window():
    try:
        import gi  # noqa: F401
    except ImportError:
        raise unittest.SkipTest("PyGObject is not installed") from None
    spec = importlib.util.spec_from_file_location("welcome_window", WINDOW)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, ValueError) as error:
        raise unittest.SkipTest(f"GTK 3 is not available: {error}") from None
    return module


class EscapeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.window = load_window()

    def test_escape_goes_back_one_step(self):
        self.assertEqual(self.window.escape_step(2), 1)
        self.assertEqual(self.window.escape_step(1), 0)

    def test_escape_on_the_first_step_closes(self):
        self.assertEqual(self.window.escape_step(0), -1)

    def test_escape_on_the_last_step_is_left_to_the_test_dictation(self):
        last = self.window.STEPS.index("try")
        self.assertIsNone(self.window.escape_step(last))


if __name__ == "__main__":
    unittest.main()
