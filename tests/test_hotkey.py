"""Global shortcut: syntax of the combinations, and translation for each host."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from . import context  # noqa: F401
from .context import forced_host

from whisper_desk import host, hotkey


class ParseTest(unittest.TestCase):
    def test_gtk_syntax(self):
        self.assertEqual(hotkey.parse_binding("<Super>j"), (["super"], "j"))

    def test_several_modifiers(self):
        self.assertEqual(hotkey.parse_binding("<Ctrl><Alt>j"), (["ctrl", "alt"], "j"))

    def test_plus_syntax(self):
        self.assertEqual(hotkey.parse_binding("ctrl+alt+j"), (["ctrl", "alt"], "j"))

    def test_synonyms(self):
        self.assertEqual(hotkey.parse_binding("cmd+j"), (["super"], "j"))
        self.assertEqual(hotkey.parse_binding("<Primary><Option>j"), (["ctrl", "alt"], "j"))

    def test_named_key(self):
        self.assertEqual(hotkey.parse_binding("<Ctrl><Alt>space"), (["ctrl", "alt"], "space"))

    def test_the_modifier_order_is_normalised(self):
        self.assertEqual(
            hotkey.parse_binding("<Alt><Ctrl>j"), hotkey.parse_binding("<Ctrl><Alt>j")
        )

    def test_gtk_round_trip(self):
        self.assertEqual(hotkey.format_gtk(*hotkey.parse_binding("<Ctrl><Alt>j")), "<Ctrl><Alt>j")


class LabelTest(unittest.TestCase):
    """The shortcut as the overlay tells it: the way it reads on the keyboard."""

    def test_gtk_syntax_becomes_keycaps(self):
        with forced_host(host.LINUX):
            self.assertEqual(hotkey.label("<Super>j"), "Super+J")
            self.assertEqual(hotkey.label("<Ctrl><Alt>space"), "Ctrl+Alt+Space")

    def test_a_mac_keyboard_says_cmd(self):
        with forced_host(host.MACOS):
            self.assertEqual(hotkey.label("<Super><Alt>d"), "Option+Cmd+D")


class DefaultBindingTest(unittest.TestCase):
    def test_wsl_avoids_the_windows_key(self):
        with forced_host(host.WSL):
            self.assertEqual(hotkey.default_binding(), "<Ctrl><Alt>j")

    def test_elsewhere_it_is_super(self):
        for name in (host.LINUX, host.MACOS):
            with forced_host(name):
                self.assertEqual(hotkey.default_binding(), "<Super>j")

    def test_auto_is_resolved(self):
        with forced_host(host.LINUX):
            self.assertEqual(hotkey.resolve_binding({"hotkey": {"binding": "auto"}}), "<Super>j")

    def test_an_explicit_shortcut_is_honoured(self):
        with forced_host(host.WSL):
            self.assertEqual(
                hotkey.resolve_binding({"hotkey": {"binding": "<Super><Shift>d"}}),
                "<Super><Shift>d",
            )


class WindowsFormatTest(unittest.TestCase):
    def test_accepted_combination(self):
        self.assertEqual(hotkey.format_windows(["ctrl", "alt"], "j"), "CTRL+ALT+J")

    def test_ctrl_shift_too(self):
        self.assertEqual(hotkey.format_windows(["ctrl", "shift"], "k"), "CTRL+SHIFT+K")

    def test_named_key(self):
        self.assertEqual(hotkey.format_windows(["ctrl", "alt"], "space"), "CTRL+ALT+SPACE")

    def test_the_windows_key_is_refused(self):
        with self.assertRaises(hotkey.UnsupportedDesktop) as raised:
            hotkey.format_windows(["super"], "j")
        self.assertIn("Ctrl+Alt", str(raised.exception))

    def test_ctrl_alone_is_refused(self):
        with self.assertRaises(hotkey.UnsupportedDesktop):
            hotkey.format_windows(["ctrl"], "j")

    def test_without_a_final_key(self):
        with self.assertRaises(hotkey.UnsupportedDesktop):
            hotkey.format_windows(["ctrl", "alt"], "")


class SkhdFormatTest(unittest.TestCase):
    def test_command_alone(self):
        self.assertEqual(hotkey.format_skhd(["super"], "j"), "cmd - j")

    def test_several_modifiers(self):
        self.assertEqual(hotkey.format_skhd(["ctrl", "alt"], "j"), "ctrl + alt - j")

    def test_without_a_modifier(self):
        self.assertEqual(hotkey.format_skhd([], "f13"), "f13")

    def test_without_a_final_key(self):
        with self.assertRaises(hotkey.UnsupportedDesktop):
            hotkey.format_skhd(["super"], "")


class BackendTest(unittest.TestCase):
    def test_each_host_has_its_plugin(self):
        expectations = {host.LINUX: "GNOME", host.WSL: "Windows", host.MACOS: "skhd"}
        for name, expected in expectations.items():
            with forced_host(name):
                self.assertEqual(hotkey.backend().name, expected)

    def test_outside_wsl_the_windows_plugin_refuses(self):
        with forced_host(host.LINUX):
            with self.assertRaises(hotkey.UnsupportedDesktop):
                hotkey.WindowsHotkey().check()


class PasteLastBindingTest(unittest.TestCase):
    """The second shortcut: the dictation's key with Shift, unless said otherwise."""

    def test_auto_adds_shift_to_the_dictation_key(self):
        with forced_host(host.LINUX):
            self.assertEqual(hotkey.resolve_paste_last({"hotkey": {"paste_last": "auto"}}),
                             "<Super><Shift>j")

    def test_wsl_keeps_to_ctrl_alt(self):
        with forced_host(host.WSL):
            binding = hotkey.resolve_paste_last({"hotkey": {"paste_last": "auto"}})
        self.assertEqual(binding, "<Ctrl><Alt><Shift>j")
        self.assertEqual(hotkey.format_windows(*hotkey.parse_binding(binding)), "CTRL+ALT+SHIFT+J")

    def test_a_configuration_without_it_gets_the_default(self):
        with forced_host(host.MACOS):
            self.assertEqual(hotkey.resolve_paste_last({"hotkey": {}}), "<Super><Shift>j")

    def test_it_can_be_turned_off(self):
        for value in ("none", "", "off", "None"):
            self.assertEqual(hotkey.resolve_paste_last({"hotkey": {"paste_last": value}}), "")

    def test_an_explicit_shortcut_is_honoured(self):
        config = {"hotkey": {"binding": "auto", "paste_last": "<Ctrl><Alt>v"}}
        self.assertEqual(hotkey.resolve(config, hotkey.PASTE_LAST), "<Ctrl><Alt>v")


class FakeGsettings:
    """gsettings reduced to a dictionary."""

    def __init__(self):
        self.store: dict[tuple[str, str], str] = {(hotkey.SCHEMA, "custom-keybindings"): "@as []"}

    def __call__(self, action: str, schema: str, key: str, value: str = "") -> str:
        if action == "set":
            self.store[(schema, key)] = value
            return ""
        return self.store.get((schema, key), "")


class SlotsTest(unittest.TestCase):
    """Each shortcut has a slot of its own: installing or removing one leaves the other."""

    def test_gnome_keeps_two_custom_shortcuts(self):
        fake = FakeGsettings()
        with mock.patch.object(hotkey, "_gsettings", fake), \
                mock.patch.object(hotkey, "is_gnome", lambda: True), \
                mock.patch.object(hotkey.shutil, "which", lambda name: "/usr/bin/" + name):
            gnome = hotkey.GnomeHotkey()
            gnome.install("<Super>j", "whisper-desk", "wd toggle")
            gnome.install("<Super><Shift>j", "whisper-desk (paste last)", "wd paste-last",
                          hotkey.PASTE_LAST)
            self.assertEqual(hotkey._bindings(), [hotkey.KEY_PATH, hotkey.KEY_PATHS[hotkey.PASTE_LAST]])
            target = f"{hotkey.CUSTOM_SCHEMA}:{hotkey.KEY_PATHS[hotkey.PASTE_LAST]}"
            self.assertEqual(fake.store[(target, "command")], "wd paste-last")
            gnome.remove(hotkey.PASTE_LAST)
            self.assertEqual(hotkey._bindings(), [hotkey.KEY_PATH])
            self.assertEqual(gnome.show(hotkey.PASTE_LAST), {})

    def test_skhd_keeps_two_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "skhdrc"
            path.write_text("cmd - t : open -a Terminal\n", encoding="utf-8")
            with mock.patch.object(hotkey, "SKHD_CONFIG", str(path)), \
                    mock.patch.object(hotkey.shutil, "which", lambda name: "/usr/bin/" + name), \
                    mock.patch.object(hotkey.SkhdHotkey, "_reload", lambda self: None):
                skhd = hotkey.SkhdHotkey()
                skhd.install("<Super>j", "whisper-desk", "/bin/whisper-desk toggle")
                skhd.install("<Super><Shift>j", "whisper-desk", "/bin/whisper-desk paste-last", hotkey.PASTE_LAST)
                skhd.install("<Super>k", "whisper-desk", "/bin/whisper-desk toggle")
                self.assertEqual(skhd.show(hotkey.PASTE_LAST)["binding"], "shift + cmd - j")
                self.assertEqual(skhd.show()["binding"], "cmd - k")
                skhd.remove(hotkey.PASTE_LAST)
                self.assertEqual(skhd.show(hotkey.PASTE_LAST), {})
                self.assertEqual(path.read_text(encoding="utf-8"),
                                 "cmd - t : open -a Terminal\n# whisper-desk\ncmd - k : /bin/whisper-desk toggle\n")

    def test_a_shortcut_turned_off_is_removed(self):
        plugin = mock.Mock()
        with mock.patch.object(hotkey, "backend", lambda: plugin):
            installed = hotkey.install({"hotkey": {"name": "whisper-desk", "paste_last": "none"}},
                                       "wd paste-last", hotkey.PASTE_LAST)
        self.assertEqual(installed, "")
        plugin.remove.assert_called_once_with(hotkey.PASTE_LAST)
        plugin.install.assert_not_called()

    def test_its_name_says_what_it_does(self):
        plugin = mock.Mock()
        plugin.install.side_effect = lambda binding, *_args: binding
        with forced_host(host.LINUX), mock.patch.object(hotkey, "backend", lambda: plugin):
            hotkey.install({"hotkey": {"name": "whisper-desk", "paste_last": "auto"}},
                           "wd paste-last", hotkey.PASTE_LAST)
        plugin.install.assert_called_once_with(
            "<Super><Shift>j", "whisper-desk (paste last)", "wd paste-last", hotkey.PASTE_LAST
        )


if __name__ == "__main__":
    unittest.main()
