"""
Clipboard tools (Windows). Read only on request, never in the background;
contents are never logged. Anything that looks like a secret is withheld.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from core.privacy import looks_sensitive
from langchain_core.tools import tool

IS_WINDOWS = sys.platform == "win32"
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
MAX_RETURN_CHARS = 2000


def _api():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    return user32, kernel32


def _open(user32) -> bool:
    for _ in range(10):  # another app may hold the clipboard briefly
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.05)
    return False


def read_clipboard_text() -> str | None:
    """Unicode text on the clipboard, '' when it holds no text, None on failure."""
    if not IS_WINDOWS:
        return None
    user32, kernel32 = _api()
    if not _open(user32):
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def write_clipboard_text(text: str) -> bool:
    if not IS_WINDOWS:
        return False
    user32, kernel32 = _api()
    data = str(text).encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        return False
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        return False
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not _open(user32):
        kernel32.GlobalFree(handle)
        return False
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True  # the system owns the memory now
    finally:
        user32.CloseClipboard()


@tool
def leer_portapapeles() -> str:
    """Read the text currently on the clipboard, only when the user asks (e.g. 'clipboard la enna irukku',
    'explain what I copied'). Secrets are withheld."""
    if not IS_WINDOWS:
        return "Clipboard tools are only available on Windows."
    text = read_clipboard_text()
    if text is None:
        return "Could not open the clipboard (another app may be using it)."
    if not text.strip():
        return "The clipboard has no text."
    if looks_sensitive(text):
        return "The clipboard holds something that looks like a password, key, code or card number, so I won't read it out."
    clipped = text[:MAX_RETURN_CHARS]
    more = f"\n... ({len(text) - MAX_RETURN_CHARS} more characters)" if len(text) > MAX_RETURN_CHARS else ""
    return f"Clipboard text:\n{clipped}{more}"


@tool
def copiar_al_portapapeles(texto: str) -> str:
    """Put text on the clipboard so the user can paste it (replaces the current clipboard text)."""
    if not IS_WINDOWS:
        return "Clipboard tools are only available on Windows."
    value = str(texto or "")
    if not value:
        return "Nothing to copy."
    if looks_sensitive(value):
        return "Not copied: that looks like a password, key, code or card number."
    if not write_clipboard_text(value):
        return "Windows did not accept the clipboard change."
    return f"Copied {len(value)} characters to the clipboard."
