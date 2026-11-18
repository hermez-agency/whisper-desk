"""The application in front: what each desktop answers, read into the names it goes by."""

from __future__ import annotations

import json
import subprocess
import unittest
from unittest import mock

from . import context  # noqa: F401
from .context import forced_host

from whisper_desk import focus, host


def answers(outputs: dict[str, str]):
    """A subprocess.run that answers each program with its output; anything else fails."""
    calls: list[list[str]] = []

    def run(command, **_kwargs):
        calls.append(command)
        for program, output in outputs.items():
            if program in " ".join(command):
                return subprocess.CompletedProcess(command, 0, output.encode(), b"")
        return subprocess.CompletedProcess(command, 1, b"", b"no")

    return run, calls


class KeyTest(unittest.TestCase):
    def test_spelling_does_not_matter(self):
        self.assertEqual(focus.key("Google Chrome"), focus.key("google-chrome"))
        self.assertEqual(focus.key("chrome.exe"), "chrome")
        self.assertEqual(focus.key("Slack.app"), "slack")
        self.assertEqual(focus.key("--"), "")


class LabelTest(unittest.TestCase):
    def test_the_capitalised_name_is_the_one_shown(self):
        self.assertEqual(focus.label(["google-chrome", "Google-chrome"]), "Google-chrome")
        self.assertEqual(focus.label(["code"]), "code")

    def test_a_reverse_dns_id_is_shown_by_its_last_part(self):
        self.assertEqual(focus.label(["org.gnome.TextEditor", "TextEditor"]), "TextEditor")

    def test_an_unknown_app_has_no_name(self):
        self.assertIsNone(focus.label([]))


class ParseTest(unittest.TestCase):
    def test_x11_class(self):
        self.assertEqual(focus.parse_xprop_class('WM_CLASS(STRING) = "slack", "Slack"\n'), ["slack"])
        self.assertEqual(focus.parse_xprop_class('WM_CLASS(STRING) = "Navigator", "firefox"\n'),
                         ["Navigator", "firefox"])
        self.assertEqual(focus.parse_xprop_class("WM_CLASS:  not found.\n"), [])

    def test_a_reverse_dns_id_adds_its_last_part(self):
        self.assertEqual(focus.parse_xprop_class(
            'WM_CLASS(STRING) = "org.gnome.TextEditor", "org.gnome.TextEditor"'),
            ["org.gnome.TextEditor", "TextEditor"])

    def test_hyprland(self):
        self.assertEqual(focus.parse_hyprland('{"class": "kitty", "initialClass": "kitty"}'), ["kitty"])
        self.assertEqual(focus.parse_hyprland("{}"), [])
        self.assertEqual(focus.parse_hyprland("Invalid"), [])

    def test_sway(self):
        tree = {"type": "root", "nodes": [{"type": "output", "nodes": [{"type": "workspace", "nodes": [
            {"type": "con", "focused": False, "app_id": "foot"},
            {"type": "con", "focused": False, "nodes": [], "floating_nodes": []},
        ], "floating_nodes": [
            {"type": "floating_con", "focused": True, "app_id": None,
             "window_properties": {"class": "Slack", "instance": "slack"}},
        ]}]}]}
        self.assertEqual(focus.parse_sway(json.dumps(tree)), ["Slack"])
        self.assertEqual(focus.parse_sway('{"type": "root", "nodes": []}'), [])


class FocusedAppTest(unittest.TestCase):
    def test_x11(self):
        run, calls = answers({
            "-root": "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x3a00007\n",
            "0x3a00007": 'WM_CLASS(STRING) = "code", "Code"\n',
        })
        with mock.patch.dict("os.environ", {"DISPLAY": ":0"}, clear=True), forced_host(host.LINUX), \
                mock.patch.object(focus.shutil, "which", lambda name: f"/usr/bin/{name}"), \
                mock.patch.object(focus.subprocess, "run", run):
            self.assertEqual(focus.focused_app(), ["code"])
        self.assertEqual(calls[1], ["xprop", "-id", "0x3a00007", "WM_CLASS"])

    def test_a_wayland_window_in_front_is_unknown(self):
        run, calls = answers({"-root": "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x0\n"})
        with mock.patch.dict("os.environ", {"DISPLAY": ":0"}, clear=True), forced_host(host.LINUX), \
                mock.patch.object(focus.shutil, "which", lambda name: f"/usr/bin/{name}"), \
                mock.patch.object(focus.subprocess, "run", run):
            self.assertEqual(focus.focused_app(), [])
        self.assertEqual(len(calls), 1)

    def test_no_display_asks_nothing(self):
        with mock.patch.dict("os.environ", {}, clear=True), forced_host(host.LINUX), \
                mock.patch.object(focus.subprocess, "run", lambda *a, **k: self.fail("ran")):
            self.assertEqual(focus.focused_app(), [])

    def test_hyprland_first(self):
        run, _calls = answers({"hyprctl": '{"class": "discord"}'})
        environment = {"DISPLAY": ":0", "HYPRLAND_INSTANCE_SIGNATURE": "x"}
        with mock.patch.dict("os.environ", environment, clear=True), forced_host(host.LINUX), \
                mock.patch.object(focus.shutil, "which", lambda name: f"/usr/bin/{name}"), \
                mock.patch.object(focus.subprocess, "run", run):
            self.assertEqual(focus.focused_app(), ["discord"])

    def test_macos(self):
        run, calls = answers({"osascript": "Slack\n"})
        with forced_host(host.MACOS), mock.patch.object(focus.subprocess, "run", run):
            self.assertEqual(focus.focused_app(), ["Slack"])
        self.assertIn("frontmost", calls[0][2])

    def test_wsl(self):
        with forced_host(host.WSL), \
                mock.patch.object(host, "run_powershell", lambda script, timeout: "WINWORD\r\n"):
            self.assertEqual(focus.focused_app(), ["WINWORD"])

    def test_a_tool_that_fails_or_hangs_says_nothing(self):
        def hang(command, **_kwargs):
            raise subprocess.TimeoutExpired(command, focus.TIMEOUT_SECONDS)

        with forced_host(host.MACOS), mock.patch.object(focus.subprocess, "run", hang):
            self.assertEqual(focus.focused_app(), [])
        with forced_host(host.WSL), mock.patch.object(host, "run_powershell", lambda *a, **k: None):
            self.assertEqual(focus.focused_app(), [])


if __name__ == "__main__":
    unittest.main()
