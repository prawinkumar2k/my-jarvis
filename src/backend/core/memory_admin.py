"""Memory management for the UI: list, search, add, edit, forget, export, clear, private mode.

A thin layer over the existing memory tools (`tools/memory.py`), so the same rules apply as when the
user talks to JARVIS: private mode blocks writes, secrets (passwords, keys, card numbers, one-time codes)
are refused, and forgetting also removes the copy in the cognitive memory graph. Nothing here talks to
the cloud.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_PROFILE = "web_default"
RETENTION_CHOICES = (0, 30, 90, 365)  # days a memory is kept; 0 = until you forget it
_lock = threading.RLock()


def _pid(profile_id: str | None) -> str:
    from tools._common import _normalizar_profile_id

    return _normalizar_profile_id(profile_id or DEFAULT_PROFILE)


def list_facts(profile_id: str | None = None, query: str = "") -> list[dict]:
    from tools.memory import _fact_lines

    needle = str(query or "").strip().lower()
    return [
        {"n": number, "text": text}
        for number, text in enumerate(_fact_lines(_pid(profile_id)), 1)
        if not needle or needle in text.lower()
    ]


def _run(tool, profile_id: str | None, **args) -> str:
    from core import jarvis_state

    with jarvis_state.active_profile(_pid(profile_id)):
        return str(tool.invoke(args))


def add_fact(profile_id: str | None, text: str) -> tuple[bool, str]:
    from tools.memory import guardar_dato_memoria

    before = len(list_facts(profile_id))
    message = _run(guardar_dato_memoria, profile_id, dato=text)
    return len(list_facts(profile_id)) > before or "already" in message.lower(), message


def edit_fact(profile_id: str | None, number: int, text: str) -> tuple[bool, str]:
    from tools.memory import editar_memoria

    message = _run(editar_memoria, profile_id, numero_o_texto=str(number), nuevo_texto=text)
    return message.startswith("Memory updated"), message


def forget_fact(profile_id: str | None, number: int) -> tuple[bool, str]:
    from tools.memory import olvidar_memoria

    message = _run(olvidar_memoria, profile_id, numero_o_texto=str(number))
    return message.startswith("Forgotten"), message


def clear_all(profile_id: str | None) -> int:
    """Forget every saved memory (and its graph copy). Returns how many were removed."""
    removed = 0
    while list_facts(profile_id):
        ok, _ = forget_fact(profile_id, 1)
        if not ok:
            break
        removed += 1
    return removed


def _retention_path() -> Path:
    from core.runtime_paths import resolve_runtime_paths

    return resolve_runtime_paths().memory / "memory_retention.json"


def _load_retention() -> dict:
    try:
        data = json.loads(_retention_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data = data if isinstance(data, dict) else {}
    days = data.get("days")
    saved = data.get("first_seen")
    return {"days": days if days in RETENTION_CHOICES else 0, "first_seen": saved if isinstance(saved, dict) else {}}


def _save_retention(data: dict) -> None:
    path = _retention_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def retention_days() -> int:
    return _load_retention()["days"]


def set_retention_days(days: int) -> int:
    if days not in RETENTION_CHOICES:
        raise ValueError(f"Choose one of {', '.join(str(d) for d in RETENTION_CHOICES)} days (0 keeps memories until you forget them).")
    with _lock:
        data = _load_retention()
        data["days"] = days
        _save_retention(data)
    return days


def prune_expired(profile_id: str | None = None, now: datetime | None = None) -> int:
    """Forget memories older than the retention period. Returns how many were removed.

    Memories carry no date of their own, so each one is dated the first time it is seen here; memories
    that existed before this feature count from that first look, not from when they were really saved.
    """
    from tools.memory import _fact_lines

    now = now or datetime.now()
    pid = _pid(profile_id)
    with _lock:
        data = _load_retention()
        seen = data["first_seen"].setdefault(pid, {})
        facts = _fact_lines(pid)
        changed = False
        for fact in facts:
            if fact not in seen:
                seen[fact] = now.isoformat(timespec="seconds")
                changed = True
        for gone in [fact for fact in seen if fact not in facts]:
            del seen[gone]
            changed = True
        removed = 0
        days = data["days"]
        if days:
            cutoff = now - timedelta(days=days)
            for number in range(len(facts), 0, -1):  # from the end so numbers stay valid
                try:
                    stamped = datetime.fromisoformat(seen[facts[number - 1]])
                except (KeyError, ValueError):
                    continue
                if stamped < cutoff and forget_fact(profile_id, number)[0]:
                    seen.pop(facts[number - 1], None)
                    removed += 1
                    changed = True
        if changed:
            _save_retention(data)
        return removed


def export_facts(profile_id: str | None = None) -> dict:
    from core.privacy import is_private_mode

    facts = list_facts(profile_id)
    return {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "profile": _pid(profile_id),
        "private_mode": is_private_mode(),
        "count": len(facts),
        "memories": [fact["text"] for fact in facts],
        "note": "Passwords, keys, card numbers and one-time codes are never stored as memory.",
    }
