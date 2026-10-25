"""Process-wide emergency stop.

While engaged, every tool call is refused at both gates: the
ToolExecutionService (pipeline steps) and security_manager._security_guard
(any direct tool invocation). Registered cancel hooks run once when the stop
is engaged, so speech playback and live voice sessions can be released.

The stop does not undo operations that already completed, and it cannot
recall a request already sent to an external service.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class EmergencyStopState:
    engaged: bool
    reason: str
    engaged_at: str
    hook_failures: tuple[str, ...] = ()


_lock = threading.RLock()
_engaged = False
_reason = ""
_engaged_at = ""
_hook_failures: tuple[str, ...] = ()
_cancel_hooks: dict[str, Callable[[], None]] = {}


def register_cancel_hook(name: str, hook: Callable[[], None]) -> None:
    """Register a callable that releases a resource when the stop engages."""
    with _lock:
        _cancel_hooks[str(name)] = hook


def unregister_cancel_hook(name: str) -> None:
    with _lock:
        _cancel_hooks.pop(str(name), None)


def engage(reason: str = "user") -> EmergencyStopState:
    """Engage the stop and run every cancel hook. Idempotent."""
    global _engaged, _reason, _engaged_at, _hook_failures
    with _lock:
        _engaged = True
        _reason = str(reason or "user")[:120]
        _engaged_at = datetime.now(UTC).isoformat(timespec="seconds")
        hooks = list(_cancel_hooks.items())
    failures = []
    for name, hook in hooks:
        try:
            hook()
        except Exception:
            failures.append(name)
    with _lock:
        _hook_failures = tuple(failures)
    return state()


def release() -> EmergencyStopState:
    """Allow tools to run again. Pending work is not resumed automatically."""
    global _engaged, _reason, _engaged_at, _hook_failures
    with _lock:
        _engaged = False
        _reason = ""
        _engaged_at = ""
        _hook_failures = ()
    return state()


def is_engaged() -> bool:
    with _lock:
        return _engaged


def state() -> EmergencyStopState:
    with _lock:
        return EmergencyStopState(_engaged, _reason, _engaged_at, _hook_failures)
