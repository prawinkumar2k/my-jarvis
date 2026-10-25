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

    def add(self, text: str, minutes: float, now: datetime | None = None) -> dict:
        now = now or datetime.now()
        item = {
            "id": uuid.uuid4().hex[:8],
            "text": str(text).strip()[:300],
            "due": (now + timedelta(minutes=float(minutes))).isoformat(timespec="seconds"),
            "created": now.isoformat(timespec="seconds"),
            "state": "pending",
            "missed": False,
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
        """Mark due reminders as fired and return the ones fired by this call."""
        now = now or datetime.now()
        fired = []
        with self._lock:
            items = self._load()
            for item in items:
                if item["state"] != "pending":
                    continue
                due = datetime.fromisoformat(item["due"])
                if due <= now:
                    item["state"] = "fired"
                    item["missed"] = (now - due).total_seconds() > MISSED_GRACE_SECONDS
                    fired.append(item)
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
