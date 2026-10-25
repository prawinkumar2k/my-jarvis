"""Private mode and sensitive-content guard for persistent memory.

Private mode is a process-wide switch (initial value: JARVIS_PRIVATE_MODE).
While it is on, nothing new is written to long-term memory: no saved facts, no
automatic preference extraction. Conversation context for the current session
still works so JARVIS can follow the conversation.
"""

from __future__ import annotations

import os
import re
import threading

_lock = threading.RLock()
_private_mode = str(os.getenv("JARVIS_PRIVATE_MODE") or "").strip().lower() in {"1", "true", "yes", "on"}

_SENSITIVE_PATTERNS = (
    re.compile(r"\b(?:AIza[0-9A-Za-z_-]{20,}|gsk_[0-9A-Za-z]{20,}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[0-9A-Za-z]{20,}|xox[abpr]-[0-9A-Za-z-]{10,})"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:password|passwd|pwd|passcode|pin|otp|2fa|cvv|api[ _-]?key|secret|token)\b\s*(?:is|=|:|-)?\s*\S+", re.IGNORECASE),
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),  # payment card numbers
    re.compile(r"\b\d{6}\b.*\b(?:code|otp)\b|\b(?:code|otp)\b.*\b\d{6}\b", re.IGNORECASE),
)


def is_private_mode() -> bool:
    with _lock:
        return _private_mode


def set_private_mode(enabled: bool) -> bool:
    global _private_mode
    with _lock:
        _private_mode = bool(enabled)
        return _private_mode


def looks_sensitive(text: str) -> bool:
    """True for credentials, keys, card numbers or one-time codes."""
    value = str(text or "")
    return any(pattern.search(value) for pattern in _SENSITIVE_PATTERNS)
