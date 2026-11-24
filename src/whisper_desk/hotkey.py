"""Registering the global shortcut with the host's shortcut manager.

Nobody agrees on the matter: GNOME stores shortcuts in gsettings, Windows
attaches them to a Start menu shortcut, macOS exposes nothing at all — there
you have to go through a third-party agent (skhd) or through the user's own
hands. Each host therefore has its own plugin, behind the same interface.

Two shortcuts share it, each in a slot of its own: the dictation (TOGGLE) and
the one that types the last dictation again (PASTE_LAST).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from . import host

SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = f"{SCHEMA}.custom-keybinding"
BASE_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
SLOT = "whisper-desk"
KEY_PATH = f"{BASE_PATH}/{SLOT}/"

TOGGLE = "toggle"
PASTE_LAST = "paste_last"
SLOTS = (TOGGLE, PASTE_LAST)
KEY_PATHS = {TOGGLE: KEY_PATH, PASTE_LAST: f"{BASE_PATH}/{SLOT}-paste-last/"}

SHORTCUT_NAME = "whisper-desk"
SKHD_CONFIG = os.path.expanduser("~/.config/skhd/skhdrc")
SKHD_MARK = "# whisper-desk"
SKHD_MARKS = {TOGGLE: SKHD_MARK, PASTE_LAST: "# whisper-desk paste-last"}
# Words that turn a binding off rather than name one.
OFF = ("", "none", "off", "disabled")


class UnsupportedDesktop(RuntimeError):
    """No automatic way to install the shortcut here."""


# -- shortcut syntax ----------------------------------------------------------

MODIFIER_NAMES = {
    "super": "super", "cmd": "super", "command": "super", "meta": "super",
    "win": "super", "windows": "super", "mod4": "super",
    "ctrl": "ctrl", "control": "ctrl", "primary": "ctrl",
    "alt": "alt", "option": "alt", "opt": "alt",
    "shift": "shift",
}
MODIFIER_ORDER = ("ctrl", "alt", "shift", "super")
GTK_MODIFIERS = {"ctrl": "<Ctrl>", "alt": "<Alt>", "shift": "<Shift>", "super": "<Super>"}


def parse_binding(binding: str) -> tuple[list[str], str]:
    """Parses "<Ctrl><Alt>j" or "ctrl+alt+j" into (["ctrl", "alt"], "j")."""
    tokens: list[str] = []
    rest = binding.strip()
    while rest.startswith("<") and ">" in rest:
        end = rest.index(">")
        tokens.append(rest[1:end])
        rest = rest[end + 1:].strip()
    tokens += [part for part in rest.replace("+", " ").split() if part]

    modifiers: list[str] = []
    key = ""
    for token in tokens:
        canonical = MODIFIER_NAMES.get(token.lower())
        if canonical:
            if canonical not in modifiers:
                modifiers.append(canonical)
        else:
            key = token
    modifiers.sort(key=MODIFIER_ORDER.index)
    return modifiers, key.lower()


def format_gtk(modifiers: list[str], key: str) -> str:
    return "".join(GTK_MODIFIERS[modifier] for modifier in modifiers) + key


def default_binding() -> str:
    """The shortcut proposed when the configuration says "auto".

    Windows keeps the Windows key for its own shortcuts, and only accepts
    combinations based on Ctrl+Alt anyway.
    """
    return "<Ctrl><Alt>j" if host.is_wsl() else "<Super>j"


def resolve_binding(config: dict[str, Any]) -> str:
    binding = str(config["hotkey"]["binding"]).strip()
    return default_binding() if not binding or binding.lower() == "auto" else binding


def default_paste_last() -> str:
    """The dictation's own key with Shift: one more finger, nothing new to learn."""
    return "<Ctrl><Alt><Shift>j" if host.is_wsl() else "<Super><Shift>j"


def resolve_paste_last(config: dict[str, Any]) -> str:
    """The shortcut that types the last dictation again; "" when it is off."""
    binding = str(config["hotkey"].get("paste_last", "auto")).strip()
    if binding.lower() in OFF:
        return ""
    return default_paste_last() if binding.lower() == "auto" else binding


def resolve(config: dict[str, Any], slot: str = TOGGLE) -> str:
    return resolve_paste_last(config) if slot == PASTE_LAST else resolve_binding(config)


def label(binding: str) -> str:
    """"<Super>j" → "Super+J": the shortcut as the user reads it on their keyboard."""
    modifiers, key = parse_binding(binding)
    keycaps = {"super": "Cmd", "alt": "Option"} if host.is_macos() else {}
    names = [keycaps.get(modifier, modifier.capitalize()) for modifier in modifiers]
    return "+".join([*names, key.upper() if len(key) == 1 else key.capitalize()])


# -- GNOME --------------------------------------------------------------------

def _gsettings(*args: str) -> str:
    result = subprocess.run(
        ["gsettings", *args], check=True, capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip()


def is_gnome() -> bool:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "") + os.environ.get("DESKTOP_SESSION", "")
    return "GNOME" in desktop.upper() or "UNITY" in desktop.upper()


def _bindings() -> list[str]:
    raw = _gsettings("get", SCHEMA, "custom-keybindings")
    if raw in ("@as []", "[]", ""):
        return []
    return [item.strip().strip("'\"") for item in raw.strip("[]").split(",") if item.strip()]


def _write_bindings(paths: list[str]) -> None:
    serialized = "[" + ", ".join(f"'{path}'" for path in paths) + "]"
    _gsettings("set", SCHEMA, "custom-keybindings", serialized)


class GnomeHotkey:
    """GNOME custom shortcut, stored in gsettings."""

    name = "GNOME"

    def check(self) -> None:
        if not shutil.which("gsettings"):
            raise UnsupportedDesktop("gsettings not found")
        if not is_gnome():
            raise UnsupportedDesktop(
                f"unsupported desktop ({os.environ.get('XDG_CURRENT_DESKTOP', 'unknown')})"
            )

    def install(self, binding: str, name: str, command: str, slot: str = TOGGLE) -> str:
        self.check()
        key_path = KEY_PATHS[slot]
        paths = _bindings()
        if key_path not in paths:
            paths.append(key_path)
            _write_bindings(paths)
        target = f"{CUSTOM_SCHEMA}:{key_path}"
        _gsettings("set", target, "name", name)
        _gsettings("set", target, "command", command)
        _gsettings("set", target, "binding", binding)
        return binding

    def remove(self, slot: str = TOGGLE) -> None:
        self.check()
        paths = _bindings()
        if KEY_PATHS[slot] in paths:
            _write_bindings([path for path in paths if path != KEY_PATHS[slot]])

    def show(self, slot: str = TOGGLE) -> dict[str, str]:
        self.check()
        key_path = KEY_PATHS[slot]
        if key_path not in _bindings():
            return {}
        target = f"{CUSTOM_SCHEMA}:{key_path}"
        return {
            "name": _gsettings("get", target, "name").strip("'"),
            "command": _gsettings("get", target, "command").strip("'"),
            "binding": _gsettings("get", target, "binding").strip("'"),
        }


# -- Windows (WSL) ------------------------------------------------------------

# Windows only accepts a global shortcut on a .lnk in the Start menu or on the
# desktop, and only with Ctrl+Alt (optionally completed by Shift).
WINDOWS_KEYS = {"space": "SPACE", "enter": "ENTER", "insert": "INS"}
LINK_NAME = "whisper-desk.lnk"
LINK_NAMES = {TOGGLE: LINK_NAME, PASTE_LAST: "whisper-desk paste last.lnk"}


def start_menu(slot: str = TOGGLE) -> str:
    return "$env:APPDATA + '\\Microsoft\\Windows\\Start Menu\\Programs\\" + LINK_NAMES[slot] + "'"



def format_windows(modifiers: list[str], key: str) -> str:
    """Returns "CTRL+ALT+J", or raises UnsupportedDesktop if Windows refuses it."""
    if "super" in modifiers:
        raise UnsupportedDesktop(
            "Windows reserves the Windows key for itself: choose a shortcut "
            "based on Ctrl+Alt, for instance '<Ctrl><Alt>j'"
        )
    if "ctrl" not in modifiers or not ("alt" in modifiers or "shift" in modifiers):
        raise UnsupportedDesktop(
            "Windows only accepts Ctrl+Alt+key (or Ctrl+Shift+key) shortcuts"
        )
    if not key:
        raise UnsupportedDesktop("shortcut without a final key")
    names = {"ctrl": "CTRL", "alt": "ALT", "shift": "SHIFT"}
    return "+".join(names[modifier] for modifier in modifiers) + "+" + WINDOWS_KEYS.get(
        key, key.upper()
    )


class WindowsHotkey:
    """Windows shortcut attached to a Start menu .lnk, which calls WSL back."""

    name = "Windows"

    def check(self) -> None:
        if not host.is_wsl():
            raise UnsupportedDesktop("host is not WSL")
        if not host.has_windows_interop():
            raise UnsupportedDesktop(
                "Windows interoperability unavailable (powershell.exe not found)"
            )

    def _script(self, body: str, slot: str = TOGGLE) -> str:
        return f"$path = {start_menu(slot)}; $shell = New-Object -ComObject WScript.Shell; {body}"

    def install(self, binding: str, name: str, command: str, slot: str = TOGGLE) -> str:
        self.check()
        hotkey = format_windows(*parse_binding(binding))
        distro = host.wsl_distro()
        arguments = (f"-d {distro} " if distro else "") + f"-e {command}"
        body = (
            "$link = $shell.CreateShortcut($path);"
            "$link.TargetPath = $env:SystemRoot + '\\System32\\wsl.exe';"
            f"$link.Arguments = {host.powershell_literal(arguments)};"
            f"$link.Description = {host.powershell_literal(name)};"
            "$link.WindowStyle = 7;"
            f"$link.Hotkey = {host.powershell_literal(hotkey)};"
            "$link.Save()"
        )
        if host.run_powershell(self._script(body, slot)) is None:
            raise UnsupportedDesktop("cannot create the Windows shortcut")
        return hotkey

    def remove(self, slot: str = TOGGLE) -> None:
        self.check()
        host.run_powershell(
            self._script("if (Test-Path $path) { Remove-Item $path -Force }", slot)
        )

    def show(self, slot: str = TOGGLE) -> dict[str, str]:
        self.check()
        body = (
            "if (-not (Test-Path $path)) { exit 0 };"
            "$link = $shell.CreateShortcut($path);"
            "$link.Hotkey; $link.Arguments; $link.Description"
        )
        output = host.run_powershell(self._script(body, slot))
        if not output:
            return {}
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines:
            return {}
        return {
            "binding": lines[0],
            "command": lines[1] if len(lines) > 1 else "",
            "name": lines[2] if len(lines) > 2 else SHORTCUT_NAME,
        }


# -- macOS --------------------------------------------------------------------

SKHD_MODIFIERS = {"super": "cmd", "ctrl": "ctrl", "alt": "alt", "shift": "shift"}

MACOS_MANUAL = (
    "macOS exposes no global shortcut on the command line. Two ways: "
    "'brew install skhd && skhd --start-service', then run this command again; "
    "or create a Quick Action (Automator → Run Shell Script) and assign it "
    "a shortcut in System Settings → Keyboard → Keyboard Shortcuts"
)


def format_skhd(modifiers: list[str], key: str) -> str:
    """Returns "cmd - j", the skhd syntax."""
    if not key:
        raise UnsupportedDesktop("shortcut without a final key")
    names = [SKHD_MODIFIERS[modifier] for modifier in modifiers]
    return (" + ".join(names) + " - " if names else "") + key


class SkhdHotkey:
    """macOS shortcut entrusted to skhd, the only common scriptable agent."""

    name = "skhd"

    def check(self) -> None:
        if not shutil.which("skhd"):
            raise UnsupportedDesktop(MACOS_MANUAL)

    def _lines(self) -> list[str]:
        try:
            with open(SKHD_CONFIG, encoding="utf-8") as handle:
                return handle.read().splitlines()
        except OSError:
            return []

    def _without_ours(self, slot: str = TOGGLE) -> list[str]:
        """Removes our line and its comment, so it can be rewritten cleanly."""
        kept, skip_next = [], False
        for line in self._lines():
            if line.strip() == SKHD_MARKS[slot]:
                skip_next = True
                continue
            if skip_next:
                skip_next = False
                if "whisper-desk" in line:
                    continue
            kept.append(line)
        return kept

    def _write(self, lines: list[str]) -> None:
        os.makedirs(os.path.dirname(SKHD_CONFIG), exist_ok=True)
        with open(SKHD_CONFIG, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines).rstrip("\n") + "\n")

    def _reload(self) -> None:
        subprocess.run(["skhd", "--reload"], capture_output=True, timeout=10, check=False)

    def install(self, binding: str, name: str, command: str, slot: str = TOGGLE) -> str:
        self.check()
        shortcut = format_skhd(*parse_binding(binding))
        self._write(self._without_ours(slot) + [SKHD_MARKS[slot], f"{shortcut} : {command}"])
        self._reload()
        return shortcut

    def remove(self, slot: str = TOGGLE) -> None:
        self.check()
        self._write(self._without_ours(slot))
        self._reload()

    def show(self, slot: str = TOGGLE) -> dict[str, str]:
        self.check()
        lines = self._lines()
        for index, line in enumerate(lines):
            if line.strip() == SKHD_MARKS[slot] and index + 1 < len(lines):
                shortcut, _, command = lines[index + 1].partition(":")
                return {
                    "name": SHORTCUT_NAME,
                    "binding": shortcut.strip(),
                    "command": command.strip(),
                }
        return {}


BACKENDS = {
    host.LINUX: GnomeHotkey,
    host.WSL: WindowsHotkey,
    host.MACOS: SkhdHotkey,
}


def backend():
    """The shortcut plugin of the current host."""
    return BACKENDS[host.name()]()


def install(config: dict[str, Any], command: str, slot: str = TOGGLE) -> str:
    """Creates or updates a shortcut. Returns the installed combination.

    A slot whose binding is off is removed instead, and "" returned.
    """
    binding = resolve(config, slot)
    plugin = backend()
    if not binding:
        plugin.remove(slot)
        return ""
    name = str(config["hotkey"]["name"])
    if slot == PASTE_LAST:
        name += " (paste last)"
    return plugin.install(binding, name, command, slot)


def remove(slot: str = TOGGLE) -> None:
    backend().remove(slot)


def show(slot: str = TOGGLE) -> dict[str, str]:
    return backend().show(slot)
