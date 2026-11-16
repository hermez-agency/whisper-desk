"""The application in front when a dictation starts: what a style per app is chosen by."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from typing import Any

from . import host

logger = logging.getLogger("whisper-desk.focus")

# Asked once, at the shortcut: a desktop that does not answer at once only
# costs the style per app, never the dictation.
TIMEOUT_SECONDS = 3.0

_WINDOW_ID = re.compile(r"window id # (0x[0-9a-fA-F]+)")
_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')

_FRONTMOST_MACOS = (
    'tell application "System Events" to get name of first application process '
    "whose frontmost is true"
)
_FRONTMOST_WINDOWS = (
    "Add-Type -Name Foreground -Namespace WhisperDesk -MemberDefinition '"
    '[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();'
    '[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);'
    "';$id = 0;"
    "[void][WhisperDesk.Foreground]::GetWindowThreadProcessId([WhisperDesk.Foreground]::GetForegroundWindow(), [ref]$id);"
    "(Get-Process -Id $id).ProcessName"
)


def key(name: str) -> str:
    """An app's name as it is compared: "Google Chrome", "google-chrome" and "chrome.exe" alike."""
    name = name.strip().lower()
    name = name.removesuffix(".exe").removesuffix(".app")
    return re.sub(r"[\W_]+", "", name)


def _run(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, timeout=TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        logger.debug("%s unavailable: %s", command[0], error)
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace")


def _names(*candidates: Any) -> list[str]:
    """The names an app goes by, each once; reverse-DNS ids add their last part."""
    names: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        found = [candidate.strip()]
        if candidate.strip().count(".") >= 2 and " " not in candidate.strip():
            found.append(candidate.rsplit(".", 1)[-1])
        for name in found:
            if key(name) and key(name) not in {key(known) for known in names}:
                names.append(name)
    return names


def parse_xprop_class(output: str) -> list[str]:
    """`WM_CLASS(STRING) = "slack", "Slack"` -> its instance and class."""
    if "WM_CLASS" not in output or "not found" in output:
        return []
    return _names(*_QUOTED.findall(output))


def _x11() -> list[str]:
    root = _run(["xprop", "-root", "_NET_ACTIVE_WINDOW"])
    match = _WINDOW_ID.search(root or "")
    # 0x0: the focus is on no X window — under Wayland, a native window.
    if not match or int(match[1], 16) == 0:
        return []
    return parse_xprop_class(_run(["xprop", "-id", match[1], "WM_CLASS"]) or "")


def parse_hyprland(output: str) -> list[str]:
    try:
        window = json.loads(output)
    except ValueError:
        return []
    if not isinstance(window, dict):
        return []
    return _names(window.get("class"), window.get("initialClass"))


def _focused_node(node: dict[str, Any]) -> dict[str, Any] | None:
    if node.get("focused") and node.get("type") in ("con", "floating_con"):
        return node
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        found = _focused_node(child)
        if found:
            return found
    return None


def parse_sway(output: str) -> list[str]:
    try:
        tree = json.loads(output)
    except ValueError:
        return []
    node = _focused_node(tree) if isinstance(tree, dict) else None
    if node is None:
        return []
    properties = node.get("window_properties") or {}
    return _names(node.get("app_id"), properties.get("class"), properties.get("instance"))


def _linux() -> list[str]:
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
        return parse_hyprland(_run(["hyprctl", "activewindow", "-j"]) or "")
    if os.environ.get("SWAYSOCK") and shutil.which("swaymsg"):
        return parse_sway(_run(["swaymsg", "-t", "get_tree"]) or "")
    # GNOME and KDE on Wayland tell no client which window is in front; their
    # X11 side (XWayland) still names an X application that has the focus.
    if os.environ.get("DISPLAY") and shutil.which("xprop"):
        return _x11()
    return []


def _macos() -> list[str]:
    return _names((_run(["osascript", "-e", _FRONTMOST_MACOS]) or "").strip())


def _wsl() -> list[str]:
    # The window in front is a Windows one: Linux tools would only see WSLg's.
    output = host.run_powershell(_FRONTMOST_WINDOWS, timeout=TIMEOUT_SECONDS)
    return _names((output or "").strip())


def focused_app() -> list[str]:
    """The names of the application in front — empty when the desktop does not say."""
    try:
        if host.is_macos():
            return _macos()
        if host.is_wsl():
            return _wsl()
        return _linux()
    except Exception:  # the style per app is a nicety: never a failed dictation
        logger.exception("Could not tell the application in front")
        return []
