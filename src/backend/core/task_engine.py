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

import hashlib
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
_running: set[str] = set()  # tasks executing in this process (guards against double clicks)


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
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
        for column in ("started", "finished", "plan_hash", "approved_hash"):  # added after the first release
            if column not in columns:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {column} TEXT DEFAULT ''")
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


def _tier(name: str, args: dict):
    """Risk tier of one step: AUTO runs, TASK is covered by one plan approval, EXPLICIT asks on its own."""
    from core.security.approval_policy import Tier, classify

    if not _needs_approval(name):
        return Tier.AUTO
    found = classify(name, args)
    # "none" means the central table does not know this tool as confirmation-required: stay conservative.
    return Tier.EXPLICIT if found.category == "none" else found.tier


def _plan_hash(steps: list[tuple[str, dict]]) -> str:
    payload = json.dumps([[name, args] for name, args in steps], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _brief(tool: str, args: dict) -> str:
    detail = ", ".join(f"{k}={str(v)[:40]}" for k, v in list((args or {}).items())[:3])
    return f"{tool}({detail})" if detail else tool


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
        conn.execute(
            "INSERT INTO tasks (id, goal, state, created, updated, error, plan_hash) VALUES (?,?,?,?,?,?,?)",
            (task_id, goal, "pending", _now(), _now(), "", _plan_hash(clean)),
        )
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
    task["active"] = task_id in _running
    # One approval covers the plan only while the stored steps still match what was approved.
    current = _plan_hash([(s["tool"], s["args"]) for s in task["steps"]])
    task["plan_approved"] = bool(task.get("approved_hash")) and task["approved_hash"] == current
    task["approval"] = _approval_info(task) if task["state"] == "approval_required" else None
    return task


def _approval_info(task: dict) -> dict | None:
    """What a pending approval covers, for the control panel and chat."""
    from core.security.approval_policy import Tier

    waiting = next((s for s in task["steps"] if s["state"] == "approval_required"), None)
    if waiting is None:
        return None
    if _tier(waiting["tool"], waiting["args"]) is Tier.TASK:
        covered = [s for s in task["steps"] if s["state"] != "completed" and _tier(s["tool"], s["args"]) is Tier.TASK]
        return {"scope": "plan", "steps": [{"idx": s["idx"], "summary": _brief(s["tool"], s["args"])} for s in covered]}
    return {"scope": "step", "steps": [{"idx": waiting["idx"], "summary": _brief(waiting["tool"], waiting["args"])}]}


def list_tasks(limit: int = 20) -> list[dict]:
    with _lock, _connect() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM tasks ORDER BY created DESC LIMIT ?", (limit,))]
    return [t for t in (get_task(i) for i in ids) if t]


def _set_task(task_id: str, state: str, error: str = "") -> None:
    now = _now()
    with _lock, _connect() as conn:
        conn.execute("UPDATE tasks SET state=?, updated=?, error=? WHERE id=?", (state, now, error[:300], task_id))
        if state == "running":
            conn.execute("UPDATE tasks SET started=? WHERE id=? AND (started IS NULL OR started='')", (now, task_id))
        if state in TERMINAL_STATES:
            conn.execute("UPDATE tasks SET finished=? WHERE id=?", (now, task_id))


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
    """Approve what is waiting for approval (control panel click or an accepted chat reply).

    A plan-level approval covers every remaining step of the same risk tier in this
    exact plan, so the user is asked once. A step that needs its own confirmation is
    approved alone and never widens the plan approval.
    """
    from core.security.approval_policy import Tier

    task = get_task(task_id)
    if not task or task["state"] != "approval_required":
        return task
    for step in task["steps"]:
        if step["state"] == "approval_required":
            if _tier(step["tool"], step["args"]) is Tier.TASK:
                with _lock, _connect() as conn:
                    conn.execute("UPDATE tasks SET approved_hash=plan_hash WHERE id=?", (task_id,))
            _set_step(task_id, step["idx"], approved=1, state="pending")
            break
    _set_task(task_id, "pending")
    return get_task(task_id)


def tasks_waiting_for_approval(max_age_s: float = 900.0) -> list[dict]:
    """Tasks paused for approval that nobody is already running, newest first."""
    now = datetime.now()
    waiting = []
    for task in list_tasks(20):
        if task["state"] != "approval_required" or task.get("active"):
            continue
        try:
            age = (now - datetime.fromisoformat(task["updated"])).total_seconds()
        except ValueError:
            continue
        if age <= max_age_s:
            waiting.append(task)
    return waiting


def answer_waiting_task(verdict: str, *, max_age_s: float = 900.0) -> str | None:
    """Apply a chat/voice "yes" or "no" to the ONE task waiting for approval.

    Returns the reply to show, or None when nothing is waiting or it is ambiguous
    (several tasks waiting, or the question is old): nothing is guessed.
    """
    from core.security import emergency_stop

    waiting = tasks_waiting_for_approval(max_age_s)
    if len(waiting) != 1:
        return None
    task = waiting[0]
    if verdict == "reject":
        reject_step(task["id"])
        return f"Okay, I stopped task {task['id']} ('{task['goal'][:60]}'). The step that was waiting will not run."
    if verdict != "approve":
        return None
    if emergency_stop.is_engaged():
        return "Emergency stop is active, so nothing was approved. Release it first."
    approve_step(task["id"])
    threading.Thread(target=run_task, args=(task["id"],), name=f"task-{task['id']}", daemon=True).start()
    return f"Approved. I'm running the rest of '{task['goal'][:60]}' now; progress is in the Tasks panel."


def reject_step(task_id: str) -> dict | None:
    """Refuse the step waiting for approval: it never runs and the task stops."""
    task = get_task(task_id)
    if not task or task["state"] != "approval_required":
        return task
    for step in task["steps"]:
        if step["state"] == "approval_required":
            _set_step(task_id, step["idx"], state="rejected", error="rejected by user")
            _set_task(task_id, "cancelled", f"step {step['idx'] + 1} ({step['tool']}) rejected by user")
            break
    return get_task(task_id)


def can_resume(task: dict) -> bool:
    return task["state"] in {"pending", "interrupted"} and not task.get("active")


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
    with _lock:
        if task_id in _running:
            return get_task(task_id)  # already executing: a second click must not run steps twice
        _running.add(task_id)
    try:
        return _run_task(task_id, profile_id, sleep)
    finally:
        with _lock:
            _running.discard(task_id)


def _run_task(task_id: str, profile_id: str, sleep) -> dict:
    from services import security_manager

    from core.security import emergency_stop
    from core.security.approval_policy import Tier

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
        tier = _tier(step["tool"], step["args"])
        if tier is Tier.EXPLICIT:
            if not step["approved"]:
                _set_step(task_id, idx, state="approval_required")
                _set_task(task_id, "approval_required", f"step {idx + 1} ({step['tool']}) needs its own confirmation")
                return get_task(task_id)
            source = "control_panel"
        elif tier is Tier.TASK:
            # Bound to the plan hash only: a per-step flag would still authorise a step edited after approval.
            if not task["plan_approved"]:
                _set_step(task_id, idx, state="approval_required")
                covered = [s for s in task["steps"][idx:] if s["state"] != "completed" and _tier(s["tool"], s["args"]) is Tier.TASK]
                listing = "; ".join(_brief(s["tool"], s["args"]) for s in covered)[:240]
                _set_task(task_id, "approval_required", f"needs your OK once for {len(covered)} step(s): {listing}")
                return get_task(task_id)
            source = "task_approved"  # covered by the one plan approval; no extra grant is created
        else:
            source = "task_engine"
        allowed, reason = security_manager._security_guard(step["tool"], step["args"], task["goal"], source, profile_id)
        if not allowed:
            _set_step(task_id, idx, state="failed", error=str(reason)[:300])
            _set_task(task_id, "failed", f"step {idx + 1} blocked: {reason}")
            return get_task(task_id)
        retries = MAX_RETRIES if tier is Tier.AUTO else 0  # never blindly repeat something that was approved
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


def _revoke_plan_approvals_on_stop() -> None:
    """Emergency STOP: approvals given earlier no longer carry over to unfinished steps."""
    try:
        with _lock, _connect() as conn:
            conn.execute("UPDATE tasks SET approved_hash='' WHERE state NOT IN ('completed','failed','cancelled')")
            conn.execute(
                "UPDATE steps SET approved=0 WHERE state != 'completed' AND task_id IN "
                "(SELECT id FROM tasks WHERE state NOT IN ('completed','failed','cancelled'))"
            )
    except sqlite3.Error:
        pass


def _register_stop_hook() -> None:
    try:
        from core.security import emergency_stop

        emergency_stop.register_cancel_hook("task_plan_approvals", _revoke_plan_approvals_on_stop)
    except Exception:  # never break import over the hook
        pass


_register_stop_hook()


def summarize(task: dict) -> str:
    done = sum(1 for s in task["steps"] if s["state"] == "completed")
    head = f"Task {task['id']} '{task['goal']}': {task['state']} ({done}/{len(task['steps'])} steps done)."
    if task["state"] == "approval_required":
        head += " Reply 'yes' (or 'seri') to approve, or 'no' to stop, or use the Tasks panel."
    lines = [f"  {s['idx'] + 1}. {s['tool']} - {s['state']}" + (f": {s['error']}" if s["error"] else "") for s in task["steps"]]
    return head + ("\n" + "\n".join(lines) if lines else "") + (f"\nNote: {task['error']}" if task.get("error") else "")
