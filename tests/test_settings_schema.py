"""The settings window offers every key of config.toml: a key added without its setting fails here."""

from __future__ import annotations

import tomllib
import unittest

from . import context  # noqa: F401

from whisper_desk import config as config_module
from whisper_desk import settings_proc, settings_schema
from whisper_desk.settings_schema import check


def example() -> dict:
    with config_module.EXAMPLE_PATH.open("rb") as handle:
        return tomllib.load(handle)


def offered() -> tuple[set[tuple[str, str]], set[str]]:
    """The (section, key) pairs with a setting of their own, and the whole sections."""
    keys = {(s.section, s.key) for s in settings_schema.settings() if not s.is_table}
    tables = {s.section for s in settings_schema.settings() if s.is_table}
    return keys, tables


class EveryKeyHasItsSettingTest(unittest.TestCase):
    def test_each_key_of_the_example_is_in_the_window(self):
        keys, tables = offered()
        missing = []
        for section, content in example().items():
            if section in tables:
                continue
            for key in content:
                if (section, key) not in keys:
                    missing.append(f"{section}.{key}")
        self.assertEqual(missing, [], "keys of config.example.toml without a setting in the window "
                                      "(add them to settings_schema.TABS)")

    def test_each_key_of_the_defaults_is_in_the_window(self):
        keys, tables = offered()
        missing = [f"{section}.{key}" for section, content in config_module.DEFAULTS.items()
                   if section not in tables for key in content if (section, key) not in keys]
        self.assertEqual(missing, [])

    def test_each_setting_is_a_key_of_the_example(self):
        content = example()
        keys, tables = offered()
        self.assertEqual([pair for pair in keys if pair[1] not in content.get(pair[0], {})], [])
        self.assertEqual([table for table in tables if table not in content], [])

    def test_a_field_is_set_once_and_has_a_label_and_a_help(self):
        fields = [setting.field for setting in settings_schema.settings()]
        self.assertEqual(len(fields), len(set(fields)))
        for setting in settings_schema.settings():
            self.assertTrue(setting.label and setting.help, setting.field)

    def test_each_value_has_its_default_and_each_choice_its_list(self):
        controller = settings_proc.SettingsController(
            config_module.load(config_module.CONFIG_DIR / "absent.toml"), "x", send=lambda *a, **k: {}
        )
        snapshot = controller.snapshot()
        for setting in settings_schema.settings():
            if setting.is_table:
                continue
            self.assertIn(setting.field, snapshot["defaults"])
            self.assertIn(setting.field, snapshot["values"])
            if setting.kind == "choice":
                self.assertIn(setting.choices, snapshot["choices"], setting.field)
                values = [value for value, _label in snapshot["choices"][setting.choices]]
                self.assertIn(snapshot["defaults"][setting.field], values, setting.field)

    def test_the_default_of_a_number_is_inside_its_range(self):
        for setting in settings_schema.settings():
            if setting.kind in ("int", "float"):
                default = config_module.DEFAULTS[setting.section][setting.key]
                self.assertEqual(check(setting, default)[1], "", setting.field)


class CheckTest(unittest.TestCase):
    def setting(self, field: str):
        return settings_schema.by_field()[field]

    def test_a_number_out_of_range_is_refused(self):
        self.assertIn("out of range", check(self.setting("beam_size"), 0)[1])
        self.assertIn("out of range", check(self.setting("bars"), 500)[1])

    def test_not_a_number_is_refused(self):
        self.assertIn("not a number", check(self.setting("width"), "wide")[1])
        self.assertIn("whole number", check(self.setting("width"), "10.5")[1])

    def test_a_decimal_comma_is_read(self):
        self.assertEqual(check(self.setting("segment_silence_seconds"), "0,8"), (0.8, ""))

    def test_the_threshold_is_auto_or_a_number(self):
        field = self.setting("threshold")
        self.assertEqual(check(field, " Auto "), ("auto", ""))
        self.assertEqual(check(field, "300"), (300, ""))
        self.assertNotEqual(check(field, "loud")[1], "")
        self.assertNotEqual(check(field, "0")[1], "")

    def test_the_paste_shortcut_is_auto_or_keys(self):
        field = self.setting("paste_shortcut")
        self.assertEqual(check(field, "ctrl+v"), ("ctrl+v", ""))
        self.assertNotEqual(check(field, "ctrl+")[1], "")
        self.assertNotEqual(check(field, "")[1], "")

    def test_the_desktop_name_cannot_be_blank(self):
        self.assertNotEqual(check(self.setting("hotkey_name"), "  ")[1], "")
        self.assertEqual(check(self.setting("initial_prompt"), "")[1], "")


if __name__ == "__main__":
    unittest.main()
