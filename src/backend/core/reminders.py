"""Persistent reminders.

Stored as JSON in the runtime data folder so they survive restarts. A reminder
moves pending -> fired (when due) -> shown (after the UI displayed it).
Reminders that came due while JARVIS was closed fire on the next check and
are flagged as missed. Firing does not depend on the optional scheduler:
the UI poll and the scheduler both call fire_due().
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

MISSED_GRACE_SECONDS = 120
MAX_REMINDERS = 200
REPEATS = ("daily", "weekdays", "weekly")
URGENT_KINDS = {"alarm", "timer"}  # never held back by quiet hours


def quiet_hours(env_value: str | None = None) -> tuple[int, int] | None:
    """JARVIS_QUIET_HOURS="22:00-07:00" -> (start, end) in minutes after midnight, or None."""
    raw = str(env_value if env_value is not None else os.getenv("JARVIS_QUIET_HOURS") or "").strip()
    try:
        start, end = (part.strip() for part in raw.split("-", 1))
        sh, sm = (int(x) for x in start.split(":"))
        eh, em = (int(x) for x in end.split(":"))
    except ValueError:
        return None
    if not (0 <= sh < 24 and 0 <= eh < 24 and 0 <= sm < 60 and 0 <= em < 60) or (sh, sm) == (eh, em):
        return None
    return sh * 60 + sm, eh * 60 + em


def in_quiet_hours(now: datetime, window: tuple[int, int] | None) -> bool:
    if window is None:
        return False
    start, end = window
    minute = now.hour * 60 + now.minute
    return start <= minute < end if start < end else minute >= start or minute < end


def next_occurrence(due: datetime, repeat: str, now: datetime) -> datetime:
    """First occurrence after now (a long downtime yields one missed fire, not a flood)."""
    nxt = due + timedelta(days=7 if repeat == "weekly" else 1)
    while nxt <= now or (repeat == "weekdays" and nxt.weekday() >= 5):
        nxt += timedelta(days=7 if repeat == "weekly" else 1)
    return nxt


def _store_path() -> Path:
    from core.runtime_paths import resolve_runtime_paths

    return resolve_runtime_paths().memory / "reminders.json"


class ReminderStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path or _store_path()

    def _load(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items[-MAX_REMINDERS:], ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)  # atomic: a crash never leaves a half-written file

    def add(self, text: str, minutes: float, now: datetime | None = None, *, repeat: str | None = None,
            kind: str = "reminder") -> dict:
        now = now or datetime.now()
        if repeat is not None and repeat not in REPEATS:
            raise ValueError(f"repeat must be one of {', '.join(REPEATS)}")
        due = now + timedelta(minutes=float(minutes))
        while repeat == "weekdays" and due.weekday() >= 5:
            due += timedelta(days=1)
        item = {
            "id": uuid.uuid4().hex[:8],
            "text": str(text).strip()[:300],
            "due": due.isoformat(timespec="seconds"),
            "created": now.isoformat(timespec="seconds"),
            "state": "pending",
            "missed": False,
            "repeat": repeat,
            "kind": kind,
        }
        with self._lock:
            items = self._load()
            items.append(item)
            self._save(items)
        return item

    def pending(self) -> list[dict]:
        with self._lock:
            return sorted((i for i in self._load() if i["state"] == "pending"), key=lambda i: i["due"])

    def cancel(self, ref: str) -> dict | None:
        ref = str(ref or "").strip().lower()
        with self._lock:
            items = self._load()
            pending = [i for i in items if i["state"] == "pending"]
            matches = [i for i in pending if i["id"] == ref] or [i for i in pending if ref and ref in i["text"].lower()]
            if len(matches) != 1:
                return None
            matches[0]["state"] = "cancelled"
            self._save(items)
            return matches[0]

    def fire_due(self, now: datetime | None = None) -> list[dict]:
        """Mark due reminders as fired and return the ones fired by this call.

        During quiet hours ordinary reminders wait (they fire when quiet hours end);
        alarms and timers always fire. A repeating reminder schedules its next time.
        """
        now = now or datetime.now()
        quiet = in_quiet_hours(now, quiet_hours())
        fired = []
        with self._lock:
            items = self._load()
            follow_ups = []
            for item in items:
                if item["state"] != "pending":
                    continue
                due = datetime.fromisoformat(item["due"])
                if due > now or (quiet and item.get("kind", "reminder") not in URGENT_KINDS):
                    continue
                item["state"] = "fired"
                item["missed"] = (now - due).total_seconds() > MISSED_GRACE_SECONDS
                fired.append(item)
                if item.get("repeat") in REPEATS:
                    follow_ups.append({
                        **item,
                        "id": uuid.uuid4().hex[:8],
                        "due": next_occurrence(due, item["repeat"], now).isoformat(timespec="seconds"),
                        "state": "pending",
                        "missed": False,
                    })
            items.extend(follow_ups)
            if fired:
                self._save(items)
        return fired

    def take_unshown(self, now: datetime | None = None) -> list[dict]:
        """Fire anything due, then return fired reminders the UI has not shown yet."""
        self.fire_due(now)
        with self._lock:
            items = self._load()
            unshown = [i for i in items if i["state"] == "fired"]
            for item in unshown:
                item["state"] = "shown"
            if unshown:
                self._save(items)
        return unshown


reminder_store = ReminderStore()
