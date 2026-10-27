"""Scheduled routines (daily summary, morning health check ...) that run while JARVIS is open.

Rules, because nobody is watching when a routine fires:
- Only tools the approval policy classifies as AUTO may be scheduled (nothing that would need a yes),
  checked when it is created AND again every time it runs.
- Every run goes through the same security guard as any tool call (emergency STOP, blocked tools, profile).
- Ordinary routines wait during quiet hours (JARVIS_QUIET_HOURS); they never run while the PC is off or
  JARVIS is closed. A routine missed during downtime runs once on the next start, flagged as missed, never
  once per missed day.
- Results are kept (last 30) and shown as a Windows notification; nothing is sent anywhere.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

MAX_ROUTINES = 20
MAX_RESULTS = 30
REPEATS = ("once", "daily", "weekdays", "weekly")
# Offered in the UI. The chat tool accepts any registered tool that is AUTO-tier, with arguments.
SUGGESTED_TOOLS = ("resumen_del_dia", "estado_jarvis", "diagnostico_sistema", "informacion_sistema",
                   "leer_notas", "listar_recordatorios", "ver_tareas")
_FORBIDDEN = {"programar_rutina", "cancelar_rutina", "ejecutar_tarea_multipaso", "reanudar_tarea"}
_CLOCK = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_lock = threading.RLock()
_path_override: Path | None = None


def _path() -> Path:
    if _path_override is not None:
        return _path_override
    from core.runtime_paths import resolve_runtime_paths

    return resolve_runtime_paths().memory / "routines.json"


def _load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"routines": list(data.get("routines") or []), "results": list(data.get("results") or [])}


def _save(data: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"routines": data["routines"], "results": data["results"][-MAX_RESULTS:]},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)  # atomic: a crash never leaves a half-written file


def _tool(name: str):
    import tools

    return getattr(tools, name) if name in getattr(tools, "_LAZY_EXPORTS", {}) else None


def _is_auto(tool: str, args: dict) -> bool:
    from core.security.approval_policy import Tier, classify

    return classify(tool, args).tier is Tier.AUTO


def next_run(clock: str, repeat: str, after: datetime) -> datetime:
    """First time at `clock` strictly after `after` that matches the repeat rule."""
    hour, minute = (int(part) for part in clock.split(":"))
    candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    while candidate <= after or (repeat == "weekdays" and candidate.weekday() >= 5):
        candidate += timedelta(days=1)
    return candidate


def add(name: str, clock: str, repeat: str, tool: str, args: dict | None = None, now: datetime | None = None) -> dict:
    """Create a routine. Raises ValueError with a user-readable reason."""
    now = now or datetime.now()
    name = str(name or "").strip()[:60]
    clock = str(clock or "").strip()
    args = args if isinstance(args, dict) else {}
    if not name:
        raise ValueError("Give the routine a name.")
    if not _CLOCK.match(clock):
        raise ValueError("Time must look like 08:00 (24 hours).")
    if repeat not in REPEATS:
        raise ValueError(f"Repeat must be one of: {', '.join(REPEATS)}.")
    if tool in _FORBIDDEN or _tool(tool) is None:
        raise ValueError(f"'{tool}' cannot be scheduled.")
    if not _is_auto(tool, args):
        raise ValueError(f"'{tool}' needs your approval each time, so it cannot run on its own.")
    clock = f"{int(clock.split(':')[0]):02d}:{clock.split(':')[1]}"
    with _lock:
        data = _load()
        if len(data["routines"]) >= MAX_ROUTINES:
            raise ValueError(f"At most {MAX_ROUTINES} routines.")
        routine = {"id": uuid.uuid4().hex[:8], "name": name, "time": clock, "repeat": repeat, "tool": tool, "args": args,
                   "enabled": True, "created": now.isoformat(timespec="seconds"), "last_run": "",
                   "next_run": next_run(clock, repeat, now).isoformat(timespec="seconds")}
        data["routines"].append(routine)
        _save(data)
    return routine


def list_all() -> dict:
    with _lock:
        return _load()


def remove(ref: str) -> dict | None:
    ref = str(ref or "").strip().lower()
    with _lock:
        data = _load()
        matches = [r for r in data["routines"] if r["id"] == ref] or [r for r in data["routines"] if ref and ref in r["name"].lower()]
        if len(matches) != 1:
            return None
        data["routines"].remove(matches[0])
        _save(data)
        return matches[0]


def _execute(routine: dict, profile_id: str) -> tuple[bool, str]:
    from services import security_manager

    from core import task_engine

    tool, args = routine["tool"], routine.get("args") or {}
    if not _is_auto(tool, args):  # classification may have changed (settings, local-only mode)
        return False, "skipped: this tool now needs approval"
    allowed, reason = security_manager._security_guard(tool, args, routine["name"], "routine", profile_id)
    if not allowed:
        return False, f"blocked: {reason}"
    target = _tool(tool)
    if target is None:
        return False, "tool no longer exists"
    try:
        return True, task_engine._invoke_with_timeout(target, args, 60.0)[:1500]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"


def run_due(now: datetime | None = None, *, profile_id: str = "admin", execute=None, force_id: str | None = None) -> list[dict]:
    """Run routines that are due (or one by id, now). Returns the results recorded by this call."""
    from core.reminders import in_quiet_hours, quiet_hours
    from core.security import emergency_stop

    now = now or datetime.now()
    if emergency_stop.is_engaged():
        return []
    quiet = in_quiet_hours(now, quiet_hours())
    run = execute or _execute
    produced = []
    with _lock:
        data = _load()
        for routine in data["routines"]:
            if force_id:
                if routine["id"] != force_id:
                    continue
            elif not routine.get("enabled") or quiet or datetime.fromisoformat(routine["next_run"]) > now:
                continue
            late = (now - datetime.fromisoformat(routine["next_run"])).total_seconds()
            ok, text = run(routine, profile_id)
            result = {"id": routine["id"], "name": routine["name"], "tool": routine["tool"], "ok": ok, "text": text,
                      "at": now.isoformat(timespec="seconds"), "missed": late > 600 and not force_id}
            produced.append(result)
            data["results"].append(result)
            routine["last_run"] = result["at"]
            if not force_id:  # a manual "run now" never uses up the next scheduled run
                if routine["repeat"] == "once":
                    routine["enabled"] = False
                routine["next_run"] = next_run(
                    routine["time"], routine["repeat"], max(now, datetime.fromisoformat(routine["next_run"]))
                ).isoformat(timespec="seconds")
        if produced:
            _save(data)
    return produced
