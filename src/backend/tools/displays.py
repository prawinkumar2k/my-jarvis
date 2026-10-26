"""Monitors and per-monitor window placement (Windows).

Geometry comes from the live display configuration every time; nothing is
cached, so a monitor that was unplugged is simply no longer offered. JARVIS
only moves and resizes windows. It never changes resolution, scaling,
orientation or any other persistent display setting.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from langchain_core.tools import tool

IS_WINDOWS = sys.platform == "win32"
MONITORINFOF_PRIMARY = 1
MONITOR_DEFAULTTONEAREST = 2
PLACEMENTS = ("full", "left", "right", "top", "bottom", "center")


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


def _rect(r) -> tuple[int, int, int, int]:
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def _info(hmon) -> dict:
    info = _MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        raise OSError("GetMonitorInfoW failed")
    return {
        "device": info.szDevice,
        "primary": bool(info.dwFlags & MONITORINFOF_PRIMARY),
        "bounds": _rect(info.rcMonitor),
        "work": _rect(info.rcWork),
    }


def number_monitors(monitors: list[dict]) -> list[dict]:
    """Screen 1 is the primary; the rest are numbered left to right, then top to bottom."""
    ordered = sorted(monitors, key=lambda m: (not m["primary"], m["bounds"][0], m["bounds"][1]))
    return [{**m, "number": i} for i, m in enumerate(ordered, 1)]


def list_monitors() -> list[dict]:
    if not IS_WINDOWS:
        return []
    from tools.pc_control import _ensure_dpi_aware

    _ensure_dpi_aware()
    found: list[dict] = []
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.RECT), ctypes.c_void_p)

    def callback(hmon, _hdc, _rect_ptr, _data):
        try:
            found.append(_info(hmon))
        except OSError:
            pass
        return True

    ctypes.windll.user32.EnumDisplayMonitors(None, None, proc(callback), 0)
    return number_monitors(found)


def monitor_of_window(hwnd: int, monitors: list[dict]) -> dict | None:
    hmon = ctypes.windll.user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
    if not hmon:
        return None
    try:
        device = _info(hmon)["device"]
    except OSError:
        return None
    return next((m for m in monitors if m["device"] == device), None)


def placement_rect(placement: str, work: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Target rectangle inside a monitor's work area (taskbar excluded)."""
    x, y, w, h = work
    half_w, half_h = w // 2, h // 2
    return {
        "full": (x, y, w, h),
        "left": (x, y, half_w, h),
        "right": (x + half_w, y, w - half_w, h),
        "top": (x, y, w, half_h),
        "bottom": (x, y + half_h, w, h - half_h),
        "center": (x + w // 8, y + h // 8, w - w // 4, h - h // 4),  # focus layout: 75% centred
    }[placement]


def fits(rect: tuple[int, int, int, int], monitors: list[dict]) -> bool:
    """A target must lie fully inside one monitor that exists right now."""
    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return False
    for m in monitors:
        mx, my, mw, mh = m["bounds"]
        if mx <= x and my <= y and x + w <= mx + mw and y + h <= my + mh:
            return True
    return False


def _pick_monitor(screen: str | int, monitors: list[dict], current: dict | None) -> dict | None:
    text = str(screen or "").strip().lower()
    if text in {"", "primary", "main", "1"}:
        return next((m for m in monitors if m["primary"]), monitors[0] if monitors else None)
    if text in {"next", "other", "second", "secondary"}:
        if len(monitors) < 2:
            return None
        if current is None:
            return monitors[1]
        return monitors[current["number"] % len(monitors)]
    if text.isdigit():
        return next((m for m in monitors if m["number"] == int(text)), None)
    return None


def move_window(hwnd: int, rect: tuple[int, int, int, int]) -> bool:
    user32 = ctypes.windll.user32
    if not user32.IsWindow(wintypes.HWND(hwnd)):
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE (a maximized window ignores MoveWindow)
    x, y, w, h = rect
    return bool(user32.MoveWindow(hwnd, x, y, w, h, True))


@tool
def listar_pantallas() -> str:
    """List connected screens (monitors) with their size and the windows on each one."""
    if not IS_WINDOWS:
        return "Screen tools are only available on Windows."
    from tools.desktop_control import _window_snapshot

    monitors = list_monitors()
    if not monitors:
        return "Windows reported no screens."
    windows = _window_snapshot(30)
    lines = []
    for m in monitors:
        x, y, w, h = m["bounds"]
        on_it = [win["title"][:50] for win in windows if (monitor_of_window(win["handle"], monitors) or {}).get("number") == m["number"]]
        tag = " (primary)" if m["primary"] else ""
        lines.append(f"Screen {m['number']}{tag}: {w}x{h} at ({x}, {y}). Windows: {', '.join(on_it[:8]) or 'none'}")
    return "\n".join(lines)


@tool
def mover_ventana_a_pantalla(ventana: str, pantalla: str = "next", posicion: str = "full") -> str:
    """Move a window to a screen. ventana: window title part or window id. pantalla: 1 (primary), 2, 3...,
    or 'next'. posicion: full, left, right, top, bottom or center (focus)."""
    if not IS_WINDOWS:
        return "Screen tools are only available on Windows."
    from tools.desktop_control import _find_window

    placement = str(posicion or "full").strip().lower()
    if placement not in PLACEMENTS:
        return f"Position must be one of: {', '.join(PLACEMENTS)}."
    monitors = list_monitors()
    win = _find_window(ventana)
    if not win:
        return f"No open window matches '{ventana}'."
    current = monitor_of_window(win["handle"], monitors)
    target = _pick_monitor(pantalla, monitors, current)
    if target is None:
        count = len(monitors)
        return f"There is no screen '{pantalla}'. {count} screen{'s' if count != 1 else ''} connected."
    rect = placement_rect(placement, target["work"])
    if not fits(rect, monitors):
        return "That position is outside the current screens; nothing was moved."
    if not move_window(win["handle"], rect):
        return f"Windows did not let me move '{win['title'][:60]}' (it may have closed or be protected)."
    return f"Moved '{win['title'][:60]}' to screen {target['number']} ({placement})."
