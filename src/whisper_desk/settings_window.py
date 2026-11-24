#!/usr/bin/env python3
"""Settings window: the essentials of config.toml, without opening it.

A view launched with the system Python, like the overlay and the history:
settings_proc.py sends it the values and the choices on stdin, and receives
on stdout what the user asks for, one JSON object per line:

    stdin   {"values": {..., "snippets": [[cue, text], ...],
                         "replacements": [[misspelling, spelling], ...],
                         "app_styles": [[app, style], ...]}, "choices": {...},
             "hotkeys": {field: {"binding", "label"}}}
            {"level": 0.42, "meter": "..."}  {"status": "...", "saved": true}
    stdout  {"action": "save", "values": {...}}
            {"action": "test_mic" | "stop_mic", "device": "..."}
            {"action": "hotkey", "field": "binding" | "paste_last",
             "accel": "<Primary><Alt>d" | "auto" | "none"}
"""

from __future__ import annotations

import json
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

# The Hermez look: orange #e46212, stone greys, headings in Bricolage Grotesque
# when the font is installed (Pango falls back to the system sans without it).
CSS = """
.section {
    font-family: "Bricolage Grotesque", sans-serif;
    font-weight: 700;
    font-size: 110%;
    color: #e46212;
    margin-top: 20px;
}
.section.first { margin-top: 0; }
.brand { font-family: "Bricolage Grotesque", sans-serif; font-weight: 700; }
.hint { color: #78716c; font-size: small; }
.error { color: #b91c1c; }
.keycap {
    font-weight: bold;
    padding: 4px 10px;
    border: 1px solid #a8a29e;
    border-radius: 6px;
}
.keycap.capturing { border-color: #e46212; color: #e46212; }
button.suggested-action {
    background-image: none;
    background-color: #e46212;
    border-color: #c2500c;
    color: #ffffff;
    text-shadow: none;
}
button.suggested-action:hover { background-color: #f07a2b; }
button.restore { font-size: small; padding: 2px 8px; }
switch:checked { background-image: none; background-color: #e46212; border-color: #c2500c; }
levelbar block.filled { background-color: #e46212; background-image: none; }
notebook > header > tabs > tab:checked { box-shadow: inset 0 -3px #e46212; }
entry:focus, spinbutton:focus, combobox:focus button, button:focus, switch:focus, treeview:focus {
    border-color: #e46212;
    outline-color: #e46212;
}
"""

# Modifier keys alone are not a shortcut: the capture waits for the real key.
MODIFIER_KEYS = {
    Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Control_L, Gdk.KEY_Control_R,
    Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Super_L, Gdk.KEY_Super_R,
    Gdk.KEY_Meta_L, Gdk.KEY_Meta_R, Gdk.KEY_ISO_Level3_Shift, Gdk.KEY_Caps_Lock,
    Gdk.KEY_Hyper_L, Gdk.KEY_Hyper_R,
}


# Launched as a script: the schema sits next to it, not in a package.
from settings_schema import TABLE_KINDS, check  # noqa: E402

# Kinds drawn with another kind's widget.
KIND_WIDGET = {"int": "number", "float": "number", "threshold": "text", "paste": "text"}


def send(message: dict) -> None:
    try:
        print(json.dumps(message, ensure_ascii=False), flush=True)
    except (BrokenPipeError, OSError, ValueError):
        pass


def hex_colour(rgba: Gdk.RGBA) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255)
    )


class SettingsWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="whisper-desk settings")
        self.set_default_size(820, 720)
        self.set_icon_name("audio-input-microphone")
        # field -> {"binding", "keycap", "hint", "help"}: one per shortcut setting.
        self.shortcuts: dict = {}
        # The shortcut field waiting for its combination, or None.
        self.capturing = None
        self.testing = False
        self.built = False
        self.choices: dict = {}
        self.defaults: dict = {}
        # field -> (setting, widget, read, write); the window's whole state.
        self.fields: dict = {}
        self.pages: dict = {}

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        header = Gtk.HeaderBar()
        header.set_title("Settings")
        header.set_subtitle("whisper-desk")
        header.get_style_context().add_class("brand")
        cancel = Gtk.Button(label="Close")
        cancel.set_tooltip_text("Close (Ctrl+W)")
        cancel.connect("clicked", lambda _button: self.close())
        header.pack_start(cancel)
        self.save_button = Gtk.Button(label="Save")
        self.save_button.set_tooltip_text("Save (Ctrl+S)")
        self.save_button.get_style_context().add_class("suggested-action")
        self.save_button.connect("clicked", self._on_save)
        header.pack_end(self.save_button)
        self.set_titlebar(header)

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(layout)
        # Ctrl+PageUp / Ctrl+PageDown change tab, Alt+letter jumps to one.
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        layout.pack_start(self.notebook, True, True, 0)

        footer = Gtk.Box()
        footer.set_border_width(10)
        layout.pack_end(footer, False, False, 0)
        layout.pack_end(Gtk.Separator(), False, False, 0)
        self.status = Gtk.Label(label="Saved settings apply at once, without restarting.")
        self.status.get_style_context().add_class("hint")
        self.status.set_xalign(0.0)
        self.status.set_line_wrap(True)
        footer.pack_start(self.status, True, True, 0)

        self.connect("key-press-event", self._on_key)
        self.connect("delete-event", self._on_delete)

    # -- building the tabs from the layout ------------------------------------
    def _build(self, layout: list) -> None:
        for tab in layout:
            page = Gtk.Grid(column_spacing=16, row_spacing=10)
            page.set_border_width(22)
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.add(page)
            self.pages[tab["id"]] = scroller
            self.notebook.append_page(scroller, Gtk.Label.new_with_mnemonic(tab["title"]))
            row = 0
            for index, group in enumerate(tab["groups"]):
                row = self._add_group(page, row, group, first=index == 0, tab=tab["id"])
        self.built = True

    def _add_group(self, page: Gtk.Grid, row: int, group: dict, first: bool, tab: str) -> int:
        title = Gtk.Label(label=group["title"])
        title.set_xalign(0.0)
        context = title.get_style_context()
        context.add_class("section")
        if first:
            context.add_class("first")
        page.attach(title, 0, row, 1, 1)
        members = [setting for setting in group["settings"] if setting["kind"] not in TABLE_KINDS]
        if members:
            restore = Gtk.Button(label="Restore defaults")
            restore.get_style_context().add_class("restore")
            restore.set_halign(Gtk.Align.END)
            restore.set_tooltip_text(f"Put the {group['title']} settings back to their default values")
            restore.connect("clicked", self._on_restore, group)
            page.attach(restore, 1, row, 1, 1)
        row += 1
        for setting in group["settings"]:
            row = self._add_setting(page, row, setting, tab)
        return row

    def _add_setting(self, page: Gtk.Grid, row: int, setting: dict, tab: str) -> int:
        kind = setting["kind"]
        builder = getattr(self, f"_make_{kind}", None) or getattr(self, f"_make_{KIND_WIDGET.get(kind, kind)}")
        widget, read, write = builder(setting)
        self.fields[setting["field"]] = (setting, widget, read, write, tab)
        label = Gtk.Label(label="" if kind in TABLE_KINDS else setting["label"])
        label.set_xalign(1.0)
        label.set_yalign(0.0 if kind in TABLE_KINDS else 0.5)
        label.get_style_context().add_class("dim-label")
        label.set_mnemonic_widget(widget)
        widget.set_hexpand(True)
        page.attach(label, 0, row, 1, 1)
        page.attach(widget, 1, row, 1, 1)
        row += 1
        if kind == "device":
            row = self._add_meter(page, row)
        if kind in TABLE_KINDS:
            row = self._add_table_buttons(page, row, kind)
        hint = Gtk.Label(label=setting["help"])
        hint.set_xalign(0.0)
        hint.set_line_wrap(True)
        hint.set_max_width_chars(60)
        hint.get_style_context().add_class("hint")
        page.attach(hint, 1, row, 1, 1)
        if kind == "shortcut":
            self.shortcuts[setting["field"]].update(hint=hint, help=setting["help"])
        elif kind == "device":
            self.device_hint = hint
        self.fields[setting["field"]] += (hint,)
        return row + 1

    # One widget per kind: it hands back the widget, how to read it and how to set it.
    def _make_bool(self, _setting: dict):
        switch = Gtk.Switch()
        switch.set_halign(Gtk.Align.START)
        return switch, switch.get_active, lambda value: switch.set_active(bool(value))

    def _make_number(self, setting: dict):
        whole = setting["kind"] == "int"
        spin = Gtk.SpinButton.new_with_range(setting["minimum"], setting["maximum"], setting["step"])
        spin.set_digits(0 if whole else 1)
        spin.set_numeric(True)
        spin.set_halign(Gtk.Align.START)
        spin.set_activates_default(False)
        if setting["unit"]:
            box = Gtk.Box(spacing=8)
            box.pack_start(spin, False, False, 0)
            box.pack_start(Gtk.Label(label=setting["unit"]), False, False, 0)
            holder = box
        else:
            holder = spin

        def read():
            spin.update()
            return spin.get_value_as_int() if whole else round(spin.get_value(), 2)

        return holder, read, lambda value: spin.set_value(float(value))

    def _make_text(self, setting: dict):
        entry = Gtk.Entry()
        if setting["kind"] == "threshold":
            entry.set_placeholder_text("auto")
        elif setting["kind"] == "paste":
            entry.set_placeholder_text("auto, ctrl+v, shift+insert…")
        elif setting["field"] == "vocabulary":
            entry.set_placeholder_text("Animalink, Kubernetes, pull request…")
        return entry, entry.get_text, lambda value: entry.set_text(str(value))

    def _make_choice(self, setting: dict):
        combo = Gtk.ComboBoxText()
        name = setting["choices"] or setting["field"]

        def write(value):
            self._fill(combo, self.choices[name], str(value))

        return combo, combo.get_active_id, write

    def _make_device(self, setting: dict):
        widget, read, write = self._make_choice({**setting, "choices": "device"})
        widget.connect("changed", self._on_device_changed)
        self.device = widget
        return widget, read, write

    def _make_colour(self, _setting: dict):
        button = Gtk.ColorButton()
        button.props.use_alpha = False
        button.set_halign(Gtk.Align.START)

        def write(value):
            colour = Gdk.RGBA()
            if colour.parse(str(value)):
                button.set_rgba(colour)

        return button, lambda: hex_colour(button.get_rgba()), write

    def _make_shortcut(self, setting: dict):
        field = setting["field"]
        shortcut = self.shortcuts[field] = {"binding": "auto", "help": setting["help"]}
        keys = Gtk.Box(spacing=8)
        keycap = shortcut["keycap"] = Gtk.Label(label="…")
        keycap.get_style_context().add_class("keycap")
        keys.pack_start(keycap, False, False, 0)
        change = Gtk.Button(label="Change…")
        change.connect("clicked", self._on_capture, field)
        reset = Gtk.Button(label="Default")
        reset.set_tooltip_text(f"The host's default: {self._default_text(setting)}")
        reset.connect("clicked", lambda _button: send({"action": "hotkey", "field": field, "accel": "auto"}))
        buttons = [change, reset]
        if field != "binding":
            # Only the dictation's own shortcut cannot be done without.
            off = Gtk.Button(label="Off")
            off.set_tooltip_text("No such shortcut")
            off.connect("clicked", lambda _button: send({"action": "hotkey", "field": field, "accel": "none"}))
            buttons.append(off)
        for button in buttons:
            keys.pack_start(button, False, False, 0)
        # The binding is told by the daemon side, as a label: see show_state.
        return keys, lambda: shortcut["binding"], lambda value: None

    def _make_replacements(self, _setting: dict):
        self.replacements = Gtk.ListStore(str, str)
        self.replacement_view = self._table_view(self.replacements, ("Heard as", "Written"),
                                                 self._on_edit_replacement)
        frame = self._framed(self.replacement_view, 90)

        def write(rows):
            self.replacements.clear()
            for misspelling, spelling in rows:
                self.replacements.append([misspelling, spelling])

        return frame, lambda: [[row[0], row[1]] for row in self.replacements], write

    def _make_snippets(self, _setting: dict):
        self.snippets = Gtk.ListStore(str, str)
        self.snippet_view = self._table_view(self.snippets, ("Say", "To type"),
                                             self._on_edit_snippet, snippets=True)
        frame = self._framed(self.snippet_view, 120)

        def write(rows):
            self.snippets.clear()
            for cue, text in rows:
                self.snippets.append([cue, text])

        return frame, lambda: [[row[0], row[1]] for row in self.snippets], write

    def _make_app_styles(self, _setting: dict):
        self.app_styles = Gtk.ListStore(str, str)
        self.app_style_view = self._table_view(self.app_styles, ("App", "Style"),
                                               self._on_edit_app_style)
        # The style is kept by its name in config.toml, and shown by its label.
        self.app_style_view.get_column(1).set_cell_data_func(
            self.app_style_view.get_column(1).get_cells()[0], self._render_app_style
        )
        frame = self._framed(self.app_style_view, 90)

        def write(rows):
            self.app_styles.clear()
            for app, style in rows:
                self.app_styles.append([app, style])

        return frame, lambda: [[row[0], row[1]] for row in self.app_styles], write

    def _style_label(self, value: str) -> str:
        for choice, label in self.choices.get("style", []):
            if choice == value:
                return label.split(" — ")[0]
        return value

    def _render_app_style(self, _column, renderer, model, tree_iter, _data=None) -> None:
        renderer.props.text = self._style_label(model[tree_iter][1])

    def _table_view(self, model: Gtk.ListStore, titles: tuple, edit, snippets: bool = False):
        view = Gtk.TreeView(model=model)
        view.set_headers_visible(True)
        view.connect("row-activated", lambda *_args: edit(None))
        for index, title in enumerate(titles):
            renderer = Gtk.CellRendererText()
            renderer.props.ellipsize = Pango.EllipsizeMode.END
            if snippets:
                column = Gtk.TreeViewColumn(title, renderer)
                column.set_cell_data_func(renderer, self._render_snippet, index)
                column.set_expand(index == 1)
                if index == 0:
                    column.set_min_width(180)
            else:
                column = Gtk.TreeViewColumn(title, renderer, text=index)
                column.set_expand(True)
            column.set_resizable(True)
            view.append_column(column)
        return view

    @staticmethod
    def _framed(view: Gtk.TreeView, height: int) -> Gtk.ScrolledWindow:
        frame = Gtk.ScrolledWindow()
        frame.set_shadow_type(Gtk.ShadowType.IN)
        frame.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        frame.set_min_content_height(height)
        frame.add(view)
        return frame

    def _add_table_buttons(self, page: Gtk.Grid, row: int, kind: str) -> int:
        add, edit, remove = {
            "replacements": (self._on_add_replacement, self._on_edit_replacement,
                             self._on_remove_replacement),
            "snippets": (self._on_add_snippet, self._on_edit_snippet, self._on_remove_snippet),
            "app_styles": (self._on_add_app_style, self._on_edit_app_style,
                           self._on_remove_app_style),
        }[kind]
        buttons = Gtk.Box(spacing=8)
        for label, handler in (("Add…", add), ("Edit…", edit), ("Remove", remove)):
            button = Gtk.Button(label=label)
            button.connect("clicked", handler)
            buttons.pack_start(button, False, False, 0)
        page.attach(buttons, 1, row, 1, 1)
        return row + 1

    def _add_meter(self, page: Gtk.Grid, row: int) -> int:
        test = Gtk.Box(spacing=10)
        self.test_button = Gtk.Button(label="Test")
        self.test_button.connect("clicked", self._on_test)
        self.meter = Gtk.LevelBar()
        self.meter.set_min_value(0.0)
        self.meter.set_max_value(1.0)
        self.meter.set_valign(Gtk.Align.CENTER)
        self.meter.set_hexpand(True)
        test.pack_start(self.test_button, False, False, 0)
        test.pack_start(self.meter, True, True, 0)
        page.attach(test, 1, row, 1, 1)
        return row + 1

    @staticmethod
    def _fill(combo: Gtk.ComboBoxText, choices: list, current: str) -> None:
        combo.remove_all()
        for value, label in choices:
            combo.append(value, label)
        combo.set_active_id(current)

    # -- defaults ------------------------------------------------------------------
    def _default_text(self, setting: dict) -> str:
        """The default value, as the window shows it."""
        value = self.defaults.get(setting["field"])
        if setting["kind"] == "bool":
            return "on" if value else "off"
        if setting["kind"] in ("choice", "device"):
            name = setting["choices"] or setting["field"]
            for choice, label in self.choices.get(name, []):
                if choice == value:
                    return label.split(" — ")[0]
        if setting["kind"] == "shortcut" and setting["field"] == "paste_last":
            return "Shift+Super+J (Ctrl+Alt+Shift+J under WSL)"
        if setting["kind"] == "shortcut":
            return "Super+J (Ctrl+Alt+J under WSL)"
        if value in ("", None):
            return "none"
        return f"{value}{' ' + setting['unit'] if setting['unit'] else ''}"

    def _on_restore(self, _button: Gtk.Button, group: dict) -> None:
        for setting in group["settings"]:
            if setting["kind"] in TABLE_KINDS:
                continue
            if setting["kind"] == "shortcut":
                send({"action": "hotkey", "field": setting["field"], "accel": "auto"})
                continue
            self.fields[setting["field"]][3](self.defaults[setting["field"]])
        self.status.get_style_context().remove_class("error")
        self.status.set_text(f"{group['title']}: default values back — Save to keep them.")

    # -- orders from the command line --------------------------------------
    def show_state(self, message: dict) -> bool:
        choices = message.get("choices")
        values = message.get("values")
        if choices and values:
            self.choices = choices
            self.defaults = message.get("defaults", self.defaults)
            if not self.built and message.get("layout"):
                self._build(message["layout"])
                self.show_all()
            for field, (setting, _widget, _read, write, _tab, hint) in self.fields.items():
                if setting["kind"] == "shortcut":
                    shortcut = self.shortcuts[field]
                    shortcut["help"] = f"{setting['help']} Default: {self._default_text(setting)}."
                    shortcut["binding"] = values.get(field, shortcut["binding"])
                    if self.capturing != field:
                        shortcut["hint"].set_text(shortcut["help"])
                    continue
                write(values.get(field, self.defaults.get(field, "")))
                if setting["kind"] not in TABLE_KINDS:
                    hint.set_text(f"{setting['help']} Default: {self._default_text(setting)}.")
        for field, keys in message.get("hotkeys", {}).items():
            if field in self.shortcuts:
                self.shortcuts[field]["binding"] = keys["binding"]
                self.shortcuts[field]["keycap"].set_text(keys["label"])
                if self.capturing == field:
                    self._end_capture()
        if "level" in message:
            self.meter.set_value(float(message["level"]))
        if message.get("meter"):
            self.device_hint.set_text(message["meter"])
            self._stop_test(tell=False)
        if message.get("status"):
            self.status.set_text(message["status"])
            self.status.get_style_context().remove_class("error")
            if message.get("saved") is False:
                self.status.get_style_context().add_class("error")
            if self.capturing:
                self._end_capture()
        return GLib.SOURCE_REMOVE

    # -- what the user does ------------------------------------------------
    def values(self) -> dict:
        return {field: read() for field, (_s, _w, read, *_rest) in self.fields.items()}

    def _on_save(self, _button: Gtk.Button | None) -> None:
        # Refused here, before anything is sent: the field is shown and focused.
        for field, (setting, widget, read, _write, tab, _hint) in self.fields.items():
            if setting["kind"] in TABLE_KINDS or setting["kind"] == "shortcut":
                continue
            _value, error = check(setting, read())
            if error:
                self.notebook.set_current_page(
                    self.notebook.page_num(self.pages[tab])
                )
                widget.grab_focus()
                self.status.set_text(error)
                self.status.get_style_context().add_class("error")
                return
        self._stop_test()
        self.status.get_style_context().remove_class("error")
        self.status.set_text("Saving…")
        send({"action": "save", "values": self.values()})

    @staticmethod
    def _render_snippet(_column, renderer, model, tree_iter, index) -> None:
        # A multi-line text shows its first line: the whole is in Edit….
        text = model[tree_iter][index]
        first, _newline, rest = text.partition("\n")
        renderer.props.text = first + (" ⏎ …" if rest else "")

    def _on_add_snippet(self, _button: Gtk.Button) -> None:
        edited = self._snippet_dialog("New snippet", "", "")
        if edited:
            tree_iter = self.snippets.append(list(edited))
            self.snippet_view.get_selection().select_iter(tree_iter)

    def _on_edit_snippet(self, _button: Gtk.Button | None) -> None:
        model, tree_iter = self.snippet_view.get_selection().get_selected()
        if tree_iter is None:
            self.status.set_text("Select a snippet first.")
            return
        edited = self._snippet_dialog("Edit the snippet", model[tree_iter][0], model[tree_iter][1])
        if edited:
            model[tree_iter][0], model[tree_iter][1] = edited

    def _on_remove_snippet(self, _button: Gtk.Button) -> None:
        model, tree_iter = self.snippet_view.get_selection().get_selected()
        if tree_iter is not None:
            model.remove(tree_iter)

    def _snippet_dialog(self, title: str, cue: str, text: str) -> tuple[str, str] | None:
        """The cue and its text as the user leaves them, or None if cancelled."""
        dialog = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("OK", Gtk.ResponseType.OK).get_style_context().add_class("suggested-action")
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_default_size(460, 300)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(14)
        cue_label = Gtk.Label(label="What you say")
        cue_label.set_xalign(0.0)
        cue_entry = Gtk.Entry()
        cue_entry.set_text(cue)
        cue_entry.set_placeholder_text("my home address")
        cue_entry.set_activates_default(True)
        text_label = Gtk.Label(label="What is typed")
        text_label.set_xalign(0.0)
        buffer = Gtk.TextBuffer()
        buffer.set_text(text)
        text_view = Gtk.TextView(buffer=buffer)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroller = Gtk.ScrolledWindow()
        scroller.set_shadow_type(Gtk.ShadowType.IN)
        scroller.add(text_view)
        hint = Gtk.Label(label="Case and punctuation of the cue do not matter. "
                               "The text may hold several lines.")
        hint.set_xalign(0.0)
        hint.set_line_wrap(True)
        hint.get_style_context().add_class("hint")
        box.pack_start(cue_label, False, False, 0)
        box.pack_start(cue_entry, False, False, 0)
        box.pack_start(text_label, False, False, 0)
        box.pack_start(scroller, True, True, 0)
        box.pack_start(hint, False, False, 0)
        dialog.show_all()
        answer = dialog.run()
        cue = cue_entry.get_text().strip()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False).strip()
        dialog.destroy()
        if answer != Gtk.ResponseType.OK or not cue:
            return None
        return cue, text

    def _on_add_replacement(self, _button: Gtk.Button) -> None:
        edited = self._replacement_dialog("New replacement", "", "")
        if edited:
            tree_iter = self.replacements.append(list(edited))
            self.replacement_view.get_selection().select_iter(tree_iter)

    def _on_edit_replacement(self, _button: Gtk.Button | None) -> None:
        model, tree_iter = self.replacement_view.get_selection().get_selected()
        if tree_iter is None:
            self.status.set_text("Select a replacement first.")
            return
        edited = self._replacement_dialog("Edit the replacement",
                                          model[tree_iter][0], model[tree_iter][1])
        if edited:
            model[tree_iter][0], model[tree_iter][1] = edited

    def _on_remove_replacement(self, _button: Gtk.Button) -> None:
        model, tree_iter = self.replacement_view.get_selection().get_selected()
        if tree_iter is not None:
            model.remove(tree_iter)

    def _replacement_dialog(self, title: str, misspelling: str,
                            spelling: str) -> tuple[str, str] | None:
        """The misspelling and its spelling as the user leaves them, or None if cancelled."""
        dialog = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("OK", Gtk.ResponseType.OK).get_style_context().add_class("suggested-action")
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_default_size(420, -1)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(14)
        entries = []
        for label_text, value, placeholder in (
            ("What the model writes", misspelling, "mac os"),
            ("What you mean", spelling, "macOS"),
        ):
            label = Gtk.Label(label=label_text)
            label.set_xalign(0.0)
            entry = Gtk.Entry()
            entry.set_text(value)
            entry.set_placeholder_text(placeholder)
            entry.set_activates_default(True)
            box.pack_start(label, False, False, 0)
            box.pack_start(entry, False, False, 0)
            entries.append(entry)
        hint = Gtk.Label(label="Matched as whole words, whatever their case. "
                               "What you mean is written exactly as typed here.")
        hint.set_xalign(0.0)
        hint.set_line_wrap(True)
        hint.get_style_context().add_class("hint")
        box.pack_start(hint, False, False, 0)
        dialog.show_all()
        answer = dialog.run()
        misspelling, spelling = (entry.get_text().strip() for entry in entries)
        dialog.destroy()
        if answer != Gtk.ResponseType.OK or not misspelling or not spelling:
            return None
        return misspelling, spelling

    def _on_add_app_style(self, _button: Gtk.Button) -> None:
        edited = self._app_style_dialog("New style per app", "", "casual")
        if edited:
            tree_iter = self.app_styles.append(list(edited))
            self.app_style_view.get_selection().select_iter(tree_iter)

    def _on_edit_app_style(self, _button: Gtk.Button | None) -> None:
        model, tree_iter = self.app_style_view.get_selection().get_selected()
        if tree_iter is None:
            self.status.set_text("Select an app first.")
            return
        edited = self._app_style_dialog("Edit the style of the app",
                                        model[tree_iter][0], model[tree_iter][1])
        if edited:
            model[tree_iter][0], model[tree_iter][1] = edited

    def _on_remove_app_style(self, _button: Gtk.Button) -> None:
        model, tree_iter = self.app_style_view.get_selection().get_selected()
        if tree_iter is not None:
            model.remove(tree_iter)

    def _app_style_dialog(self, title: str, app: str, style: str) -> tuple[str, str] | None:
        """The app and its style as the user leaves them, or None if cancelled."""
        dialog = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("OK", Gtk.ResponseType.OK).get_style_context().add_class("suggested-action")
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_default_size(420, -1)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(14)
        app_label = Gtk.Label.new_with_mnemonic("_App")
        app_label.set_xalign(0.0)
        app_entry = Gtk.Entry()
        app_entry.set_text(app)
        app_entry.set_placeholder_text("slack")
        app_entry.set_activates_default(True)
        app_label.set_mnemonic_widget(app_entry)
        style_label = Gtk.Label.new_with_mnemonic("_Style")
        style_label.set_xalign(0.0)
        combo = Gtk.ComboBoxText()
        self._fill(combo, self.choices.get("style", []), style)
        style_label.set_mnemonic_widget(combo)
        hint = Gtk.Label(label="The name your system gives the app: slack, firefox, code on Linux, "
                               "Slack on macOS, WINWORD on Windows. Case, spaces and dashes "
                               "do not matter.")
        hint.set_xalign(0.0)
        hint.set_line_wrap(True)
        hint.get_style_context().add_class("hint")
        for widget in (app_label, app_entry, style_label, combo, hint):
            box.pack_start(widget, False, False, 0)
        dialog.show_all()
        answer = dialog.run()
        app = app_entry.get_text().strip()
        style = combo.get_active_id() or ""
        dialog.destroy()
        if answer != Gtk.ResponseType.OK or not app or not style:
            return None
        return app, style

    def _on_test(self, _button: Gtk.Button) -> None:
        if self.testing:
            self._stop_test()
            return
        self.testing = True
        self.test_button.set_label("Stop")
        self.device_hint.set_text("Listening — speak, the gauge must move.")
        send({"action": "test_mic", "device": self.device.get_active_id() or "default"})

    def _stop_test(self, tell: bool = True) -> None:
        if not self.testing:
            return
        self.testing = False
        self.test_button.set_label("Test")
        self.meter.set_value(0.0)
        if tell:
            send({"action": "stop_mic"})

    def _on_device_changed(self, _combo: Gtk.ComboBoxText) -> None:
        if self.testing:
            send({"action": "test_mic", "device": self.device.get_active_id() or "default"})

    def _on_capture(self, _button: Gtk.Button, field: str) -> None:
        if self.capturing:
            self._end_capture()
        self.capturing = field
        shortcut = self.shortcuts[field]
        shortcut["keycap"].set_text("Press the combination…")
        shortcut["keycap"].get_style_context().add_class("capturing")
        shortcut["hint"].set_text("Esc to keep the current shortcut.")

    def _end_capture(self) -> None:
        if not self.capturing:
            return
        shortcut = self.shortcuts[self.capturing]
        self.capturing = None
        shortcut["keycap"].get_style_context().remove_class("capturing")
        shortcut["hint"].set_text(shortcut["help"])

    def _on_key(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if not self.capturing:
            ctrl = event.state & Gtk.accelerator_get_default_mod_mask() == Gdk.ModifierType.CONTROL_MASK
            if ctrl and Gdk.keyval_to_lower(event.keyval) == Gdk.KEY_s:
                self._on_save(None)
                return True
            if ctrl and Gdk.keyval_to_lower(event.keyval) == Gdk.KEY_w:
                self.close()
                return True
            return False
        field = self.capturing
        if event.keyval == Gdk.KEY_Escape:
            send({"action": "hotkey", "field": field, "accel": self.shortcuts[field]["binding"]})
            return True
        if event.keyval in MODIFIER_KEYS:
            return True
        # X11 reports the Super key as Mod4, which the accelerator mask
        # leaves out: it is named Super before the mask is applied.
        state = event.state
        if state & Gdk.ModifierType.MOD4_MASK:
            state |= Gdk.ModifierType.SUPER_MASK
        modifiers = state & Gtk.accelerator_get_default_mod_mask()
        keyval = Gdk.keyval_to_lower(event.keyval)
        send({"action": "hotkey", "field": field, "accel": Gtk.accelerator_name(keyval, modifiers)})
        return True

    def _on_delete(self, _widget: Gtk.Widget, _event: Gdk.Event) -> bool:
        self._stop_test()
        return False


def read_orders(window: SettingsWindow) -> None:
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if isinstance(message, dict):
            GLib.idle_add(window.show_state, message)
    GLib.idle_add(Gtk.main_quit)


def main() -> int:
    window = SettingsWindow()
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    threading.Thread(target=read_orders, args=(window,), daemon=True).start()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
