"""Persistent multi-step task engine.

A task is a goal plus ordered steps, each a registered tool with arguments.
State lives in SQLite (runtime memory folder) so tasks survive restarts.

Safety model:
- Every step goes through security_manager._security_guard (permissions,
  emergency stop, strict mode, confirmation policy) before it runs.
- Steps whose tool requires confirmation stop the task in
  ``approval_required`` until the user approves from the control panel.
- Completed step results are reused; a completed step never runs twice.
- Only non-confirmation (reversible) steps are retried, at most
  MAX_RETRIES times with backoff. Risky steps are never retried blindly.
- Tasks found ``running`` at startup are marked ``interrupted``.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

MAX_STEPS = 12
MAX_RETRIES = 2
STEP_TIMEOUT_SECONDS = 60.0
TERMINAL_STATES = {"completed", "failed", "cancelled"}

_lock = threading.RLock()
_db_path_override: Path | None = None


def _db_path() -> Path:
    if _db_path_override is not None:
        return _db_path_override
    from core.runtime_paths import resolve_runtime_paths

    return resolve_runtime_paths().memory / "tasks.db"


@contextmanager
def _connect():
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, goal TEXT NOT NULL, state TEXT NOT NULL,
                created TEXT NOT NULL, updated TEXT NOT NULL, error TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS steps (
                task_id TEXT NOT NULL, idx INTEGER NOT NULL, tool TEXT NOT NULL,
                args TEXT NOT NULL, state TEXT NOT NULL, result TEXT DEFAULT '',
                attempts INTEGER DEFAULT 0, needs_approval INTEGER DEFAULT 0,
                approved INTEGER DEFAULT 0, error TEXT DEFAULT '',
                PRIMARY KEY (task_id, idx)
            );
            """
        )
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _tool(name: str):
    import tools

    if name not in getattr(tools, "_LAZY_EXPORTS", {}):
        return None
    return getattr(tools, name)


def _needs_approval(name: str) -> bool:
    from core.security.tool_policy import get_tool_policy

    return bool(get_tool_policy(name).requires_confirmation)


# ── Creation and inspection ───────────────────────────────────────
def create_task(goal: str, steps: list[dict]) -> dict:
    """Validate and store a task. steps: [{"tool": name, "args": {...}}, ...]."""
    goal = str(goal or "").strip()[:300]
    if not goal:
        raise ValueError("goal_required")
    if not steps or len(steps) > MAX_STEPS:
        raise ValueError(f"between 1 and {MAX_STEPS} steps required")
    clean = []
    for step in steps:
        name = str((step or {}).get("tool") or "").strip()
        args = (step or {}).get("args") or {}
        if not isinstance(args, dict):
            raise ValueError(f"args for {name} must be an object")
        if _tool(name) is None:
            raise ValueError(f"unknown tool: {name}")
        clean.append((name, args))
    task_id = uuid.uuid4().hex[:8]
    with _lock, _connect() as conn:
        conn.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?)", (task_id, goal, "pending", _now(), _now(), ""))
        for idx, (name, args) in enumerate(clean):
            conn.execute(
                "INSERT INTO steps (task_id, idx, tool, args, state, needs_approval) VALUES (?,?,?,?,?,?)",
                (task_id, idx, name, json.dumps(args, ensure_ascii=False), "pending", int(_needs_approval(name))),
            )
    return get_task(task_id)


def get_task(task_id: str) -> dict | None:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            return None
        steps = conn.execute("SELECT * FROM steps WHERE task_id=? ORDER BY idx", (task_id,)).fetchall()
    task = dict(row)
    task["steps"] = [{**dict(s), "args": json.loads(s["args"])} for s in steps]
    return task


def list_tasks(limit: int = 20) -> list[dict]:
    with _lock, _connect() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM tasks ORDER BY created DESC LIMIT ?", (limit,))]
    return [t for t in (get_task(i) for i in ids) if t]


def _set_task(task_id: str, state: str, error: str = "") -> None:
    with _lock, _connect() as conn:
        conn.execute("UPDATE tasks SET state=?, updated=?, error=? WHERE id=?", (state, _now(), error[:300], task_id))


def _set_step(task_id: str, idx: int, **fields) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock, _connect() as conn:
        conn.execute(f"UPDATE steps SET {cols} WHERE task_id=? AND idx=?", (*fields.values(), task_id, idx))  # noqa: S608


def recover_after_restart() -> int:
    """Mark tasks that were running when JARVIS stopped as interrupted."""
    with _lock, _connect() as conn:
        cur = conn.execute("UPDATE tasks SET state='interrupted', updated=? WHERE state='running'", (_now(),))
        conn.execute("UPDATE steps SET state='pending' WHERE state='running'")
        return cur.rowcount


def cancel_task(task_id: str) -> dict | None:
    task = get_task(task_id)
    if task and task["state"] not in TERMINAL_STATES:
        _set_task(task_id, "cancelled", "cancelled by user")
    return get_task(task_id)


def approve_step(task_id: str) -> dict | None:
    """Approve the step that is waiting for approval (control panel action)."""
    task = get_task(task_id)
    if not task or task["state"] != "approval_required":
        return task
    for step in task["steps"]:
        if step["state"] == "approval_required":
            _set_step(task_id, step["idx"], approved=1, state="pending")
            break
    _set_task(task_id, "pending")
    return get_task(task_id)


# ── Execution ─────────────────────────────────────────────────────
def _invoke_with_timeout(tool, args: dict, timeout: float) -> str:
    box: dict = {}

    def run():
        try:
            box["result"] = tool.invoke(args)
        except Exception as exc:
            box["error"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise TimeoutError(f"step exceeded {timeout:.0f}s")
    if "error" in box:
        raise box["error"]
    return str(box.get("result", ""))


def run_task(task_id: str, *, profile_id: str = "admin", sleep=time.sleep) -> dict:
    """Run pending steps in order until done, blocked, cancelled or failed."""
    from services import security_manager

    from core.security import emergency_stop

    task = get_task(task_id)
    if task is None:
        raise KeyError(task_id)
    if task["state"] in TERMINAL_STATES:
        return task
    _set_task(task_id, "running")
    for step in task["steps"]:
        idx = step["idx"]
        if step["state"] == "completed":
            continue  # reuse the stored result; never repeat a finished step
        if (get_task(task_id) or {}).get("state") == "cancelled":
            return get_task(task_id)
        if emergency_stop.is_engaged():
            _set_task(task_id, "interrupted", "emergency stop")
            return get_task(task_id)
        if step["needs_approval"] and not step["approved"]:
            _set_step(task_id, idx, state="approval_required")
            _set_task(task_id, "approval_required", f"step {idx + 1} ({step['tool']}) needs approval")
            return get_task(task_id)
        source = "control_panel" if step["approved"] else "task_engine"
        allowed, reason = security_manager._security_guard(step["tool"], step["args"], task["goal"], source, profile_id)
        if not allowed:
            _set_step(task_id, idx, state="failed", error=str(reason)[:300])
            _set_task(task_id, "failed", f"step {idx + 1} blocked: {reason}")
            return get_task(task_id)
        retries = 0 if step["needs_approval"] else MAX_RETRIES
        for attempt in range(retries + 1):
            _set_step(task_id, idx, state="running", attempts=step["attempts"] + attempt + 1)
            try:
                result = _invoke_with_timeout(_tool(step["tool"]), step["args"], STEP_TIMEOUT_SECONDS)
                _set_step(task_id, idx, state="completed", result=result[:4000], error="")
                break
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:200]}"
                if attempt >= retries:
                    _set_step(task_id, idx, state="failed", error=error)
                    _set_task(task_id, "failed", f"step {idx + 1} failed after {attempt + 1} attempt(s)")
                    return get_task(task_id)
                sleep(min(8.0, 1.5 * (2**attempt)))
    _set_task(task_id, "completed")
    return get_task(task_id)


def summarize(task: dict) -> str:
    done = sum(1 for s in task["steps"] if s["state"] == "completed")
    head = f"Task {task['id']} '{task['goal']}': {task['state']} ({done}/{len(task['steps'])} steps done)."
    lines = [f"  {s['idx'] + 1}. {s['tool']} - {s['state']}" + (f": {s['error']}" if s["error"] else "") for s in task["steps"]]
    return head + ("\n" + "\n".join(lines) if lines else "") + (f"\nNote: {task['error']}" if task.get("error") else "")
