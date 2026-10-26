"""
Everyday Windows controls: media keys, brightness, screenshots, window layouts.

Results describe what was actually done. Media keys are sent to whatever app
owns media playback; Windows does not report which app reacted, so replies
say the key was sent rather than claiming playback changed.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from core.service_container import services
from langchain_core.tools import tool

IS_WINDOWS = sys.platform == "win32"

MEDIA_KEYS = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
    "stop": 0xB2,
}
_MEDIA_ALIASES = {
    "play": "play_pause", "pause": "play_pause", "resume": "play_pause", "toggle": "play_pause",
    "podu": "play_pause", "niruthu": "play_pause", "next": "next", "skip": "next", "adutha": "next",
    "previous": "previous", "prev": "previous", "back": "previous", "munnadi": "previous", "stop": "stop",
}


def _press_key(vk: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 2, 0)


@tool
def control_multimedia(accion: str) -> str:
    """Control any media player (YouTube in the browser, VLC, Spotify, etc.) with the Windows media keys.
    accion: play_pause, next, previous or stop (also 'play', 'pause', 'skip', 'back')."""
    if not IS_WINDOWS:
        return "Media keys are only available on Windows."
    key = _MEDIA_ALIASES.get(str(accion or "").strip().lower(), str(accion or "").strip().lower())
    vk = MEDIA_KEYS.get(key)
    if vk is None:
        return "Use one of: play_pause, next, previous, stop."
    _press_key(vk)
    return f"Sent the {key.replace('_', '/')} media key to the active player."


def _powershell(script: str, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=timeout, check=False,
    )


def read_brightness() -> int | None:
    if not IS_WINDOWS:
        return None
    result = _powershell("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction Stop).CurrentBrightness")
    try:
        return int(result.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return None


@tool
def ajustar_brillo(nivel: str) -> str:
    """Set the laptop screen brightness: a number 0-100, or 'up'/'down' (±10). Works on built-in laptop screens."""
    if not IS_WINDOWS:
        return "Brightness control is only available on Windows."
    current = read_brightness()
    if current is None:
        return "This screen does not allow brightness control from Windows (external monitors usually don't)."
    raw = str(nivel or "").strip().lower().rstrip("%")
    if raw in {"up", "increase", "athigam", "kooduthal", "+"}:
        target = current + 10
    elif raw in {"down", "decrease", "kammi", "kuraivu", "-"}:
        target = current - 10
    else:
        try:
            target = int(float(raw))
        except ValueError:
            return "Give a brightness from 0 to 100, or 'up'/'down'."
    target = max(0, min(100, target))
    _powershell(
        "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop)"
        f".WmiSetBrightness(1, {target}) | Out-Null"
    )
    after = read_brightness()
    if after is None or abs(after - target) > 5:
        return f"Tried to set brightness to {target}%, but Windows reports {after}%."
    return f"Brightness set to {after}%."


def screenshots_dir() -> Path:
    base = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Pictures" / "JARVIS Screenshots"
    base.mkdir(parents=True, exist_ok=True)
    return base


@tool
def captura_pantalla() -> str:
    """Take a screenshot of the whole screen and save it in Pictures/JARVIS Screenshots (only when the user asks)."""
    try:
        from PIL import ImageGrab
    except ImportError:
        return "Screenshots need Pillow: pip install Pillow."
    try:
        image = ImageGrab.grab(all_screens=True)
    except Exception as exc:
        services.log_event("screenshot_failed", error=type(exc).__name__)
        return "Windows did not allow the screenshot."
    path = screenshots_dir() / f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
    image.save(path)
    return f"Screenshot saved: Pictures/JARVIS Screenshots/{path.name} ({image.width}x{image.height})."


# ── Window layouts ────────────────────────────────────────────────
class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def _ensure_dpi_aware() -> None:
    """Use real pixels; otherwise display scaling (125%, 150%) skews window positions."""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass


def _work_area() -> tuple[int, int, int, int]:
    rect = _RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def layout_rects(layout: str, count: int, area: tuple[int, int, int, int]) -> list[tuple[int, int, int, int]]:
    left, top, width, height = area
    if layout == "full" or count == 1:
        return [(left, top, width, height)] * count
    if count >= 3:  # three or four windows always use the 2x2 grid
        half_w, half_h = width // 2, height // 2
        cells = [(left, top), (left + half_w, top), (left, top + half_h), (left + half_w, top + half_h)]
        return [(x, y, half_w, half_h) for x, y in cells[:count]]
    half = width // 2
    return [(left, top, half, height), (left + half, top, width - half, height)][:count]


@tool
def organizar_ventanas(ventanas: str, distribucion: str = "split") -> str:
    """Arrange open windows on the main screen. ventanas: comma-separated window/app names in order,
    e.g. 'Chrome, Visual Studio Code' (first goes left). distribucion: split (left/right), grid (2x2), full."""
    if not IS_WINDOWS:
        return "Window layouts are only available on Windows."
    from tools.desktop_control import _find_window, _window_snapshot

    _ensure_dpi_aware()
    names = [n.strip() for n in str(ventanas or "").split(",") if n.strip()][:4]
    if not names:
        return "Tell me which windows to arrange, e.g. 'Chrome, VS Code'."
    snapshot = _window_snapshot(50)
    found, missing = [], []
    used: set[int] = set()
    for name in names:
        # Skip windows already placed, so "Notepad, Notepad" means two windows.
        win = _find_window(name, [w for w in snapshot if w["handle"] not in used])
        if win:
            used.add(win["handle"])
        (found if win else missing).append((name, win))
    if not found:
        return "None of those windows are open: " + ", ".join(n for n, _ in missing)
    layout = str(distribucion or "split").strip().lower()
    rects = layout_rects(layout if layout in {"split", "grid", "full"} else "split", len(found), _work_area())
    user32 = ctypes.windll.user32
    for (_name, win), (x, y, w, h) in zip(found, rects, strict=True):
        hwnd = int(win["handle"])
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.MoveWindow(hwnd, x, y, w, h, True)
    placed = ", ".join(n for n, _ in found)
    tail = f" Not open: {', '.join(n for n, _ in missing)}." if missing else ""
    return f"Arranged {placed} ({layout}).{tail}"
