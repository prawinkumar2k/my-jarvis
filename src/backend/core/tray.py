"""System-tray icon for the desktop shell: "Open JARVIS" and "Quit JARVIS".

Optional: needs `pystray` and Pillow. Without them, or with JARVIS_TRAY_ENABLED=false, nothing happens.
The tray never keeps JARVIS alive on its own: closing the window still quits everything.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

ICON_CANDIDATES = ("media/jarvis.ico",)


def tray_enabled() -> bool:
    return os.getenv("JARVIS_TRAY_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def build_menu_items(on_open: Callable[[], None], on_quit: Callable[[], None]) -> list[tuple[str, Callable[[], None]]]:
    """(label, action) pairs; kept separate from pystray so they can be tested."""
    return [("Open JARVIS", on_open), ("Quit JARVIS", on_quit)]


def _icon_image(root: Path):
    from PIL import Image, ImageDraw

    for rel in ICON_CANDIDATES:
        candidate = root / rel
        if candidate.is_file():
            try:
                return Image.open(candidate).convert("RGBA")
            except OSError:
                continue
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((6, 6, 58, 58), fill=(0, 190, 255, 255))
    return image


def start_tray(root: Path, on_open: Callable[[], None], on_quit: Callable[[], None]):
    """Start the tray icon in a background thread. Returns the icon, or None when unavailable."""
    if not tray_enabled():
        return None
    try:
        import pystray
    except ImportError:
        return None
    try:
        menu = pystray.Menu(*[
            pystray.MenuItem(label, lambda _icon, _item, action=action: action(), default=(i == 0))
            for i, (label, action) in enumerate(build_menu_items(on_open, on_quit))
        ])
        icon = pystray.Icon("jarvis", _icon_image(root), "J.A.R.V.I.S.", menu)
        threading.Thread(target=icon.run, name="jarvis-tray", daemon=True).start()
        return icon
    except Exception as exc:  # the tray is a convenience, never a reason to fail start-up
        print(f"[WARN] Tray icon unavailable: {type(exc).__name__}", flush=True)
        return None


def stop_tray(icon) -> None:
    try:
        if icon is not None:
            icon.stop()
    except Exception:
        pass
