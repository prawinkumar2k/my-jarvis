"""Task engine with risk tiers: the user approves a plan once, dangerous steps still ask.

Fake tools and a recording guard; real classification, real SQLite store (temporary file).
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from core import task_engine
from core.security import approval_policy as ap
from core.security import emergency_stop


class FakeTool:
    def __init__(self):
        self.calls = 0

    def invoke(self, args):
        self.calls += 1
        return "ok"


@pytest.fixture
def engine(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(task_engine, "_db_path_override", tmp_path / "tasks.db")
    monkeypatch.setattr(ap, "_prefs_path", lambda: tmp_path / "prefs.json")
    tools = {name: FakeTool() for name in (
        "diagnostico_sistema", "instalar_programa", "mover_archivo", "controlar_pc", "click_en_navegador")}
    guard_log: list[tuple[str, str]] = []
    monkeypatch.setattr(task_engine, "_tool", tools.get)
    monkeypatch.setattr("services.security_manager._security_guard",
                        lambda tool, args, goal, source, profile_id: guard_log.append((tool, source)) or (True, ""))
    emergency_stop.release()
    ap.grants.revoke_all()
    yield tools, guard_log
    emergency_stop.release()


def make(steps):
    return task_engine.create_task("evening cleanup", steps)


def run(task_id):
    return task_engine.run_task(task_id, sleep=lambda _s: None)


PLAN = [
    {"tool": "diagnostico_sistema", "args": {}},
    {"tool": "instalar_programa", "args": {"id_paquete": "Gyan.FFmpeg"}},
    {"tool": "mover_archivo", "args": {"origen": "a.txt", "destino": "b"}},
    {"tool": "controlar_pc", "args": {"accion": "apagar"}},
]


def test_one_approval_covers_the_whole_plan_but_shutdown_still_asks(engine):
    tools, guard_log = engine
    task = make(PLAN)
    paused = run(task["id"])
    assert paused["state"] == "approval_required"
    assert tools["diagnostico_sistema"].calls == 1  # harmless step ran without asking
    assert paused["approval"]["scope"] == "plan"
    assert [s["summary"].split("(")[0] for s in paused["approval"]["steps"]] == ["instalar_programa", "mover_archivo"]

    task_engine.approve_step(task["id"])  # the single plan approval
    paused2 = run(task["id"])
    assert tools["instalar_programa"].calls == 1 and tools["mover_archivo"].calls == 1  # no second question
    assert paused2["state"] == "approval_required" and paused2["approval"]["scope"] == "step"
    assert tools["controlar_pc"].calls == 0

    task_engine.approve_step(task["id"])  # shutdown needs its own yes
    done = run(task["id"])
    assert done["state"] == "completed" and tools["controlar_pc"].calls == 1
    sources = dict(guard_log)
    assert sources["instalar_programa"] == "task_approved" and sources["mover_archivo"] == "task_approved"
    assert sources["controlar_pc"] == "control_panel" and sources["diagnostico_sistema"] == "task_engine"


def test_plan_approval_does_not_create_chat_wide_approvals(engine):
    task = make(PLAN[:3])
    run(task["id"])
    task_engine.approve_step(task["id"])
    run(task["id"])
    assert ap.grants.snapshot() == []


def test_rejecting_the_plan_runs_nothing_more(engine):
    tools, _ = engine
    task = make(PLAN)
    run(task["id"])
    rejected = task_engine.reject_step(task["id"])
    assert rejected["state"] == "cancelled"
    assert run(task["id"])["state"] == "cancelled"
    assert tools["instalar_programa"].calls == 0 and tools["mover_archivo"].calls == 0


def test_a_plan_with_only_harmless_steps_never_asks(engine):
    tools, _ = engine
    done = run(make([{"tool": "diagnostico_sistema", "args": {}}] * 3)["id"])
    assert done["state"] == "completed" and tools["diagnostico_sistema"].calls == 3


def test_emergency_stop_withdraws_an_earlier_plan_approval(engine):
    tools, _ = engine
    task = make(PLAN[:3])
    run(task["id"])
    task_engine.approve_step(task["id"])
    assert task_engine.get_task(task["id"])["plan_approved"] is True
    emergency_stop.engage("test")
    emergency_stop.release()
    after = task_engine.get_task(task["id"])
    assert after["plan_approved"] is False
    assert run(task["id"])["state"] == "approval_required"  # asks again before touching anything
    assert tools["instalar_programa"].calls == 0


def test_an_approval_does_not_apply_if_the_stored_plan_was_changed(engine, tmp_path):
    tools, _ = engine
    task = make(PLAN[:3])
    run(task["id"])
    task_engine.approve_step(task["id"])
    with sqlite3.connect(tmp_path / "tasks.db") as conn:  # someone edits the stored steps afterwards
        conn.execute("UPDATE steps SET args=? WHERE task_id=? AND idx=1", ('{"id_paquete": "Evil.Package"}', task["id"]))
    assert task_engine.get_task(task["id"])["plan_approved"] is False
    assert run(task["id"])["state"] == "approval_required"
    assert tools["instalar_programa"].calls == 0


def test_old_task_databases_without_hashes_are_upgraded(engine, tmp_path):
    with sqlite3.connect(tmp_path / "old.db") as conn:
        conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, goal TEXT, state TEXT, created TEXT, updated TEXT, error TEXT DEFAULT '')")
        conn.execute("CREATE TABLE steps (task_id TEXT, idx INTEGER, tool TEXT, args TEXT, state TEXT, result TEXT DEFAULT '',"
                     " attempts INTEGER DEFAULT 0, needs_approval INTEGER DEFAULT 0, approved INTEGER DEFAULT 0, error TEXT DEFAULT '')")
        conn.execute("INSERT INTO tasks VALUES ('old1','legacy','pending','c','u','')")
        conn.execute("INSERT INTO steps (task_id, idx, tool, args, state) VALUES ('old1',0,'mover_archivo','{}','pending')")
    task_engine._db_path_override = tmp_path / "old.db"
    legacy = task_engine.get_task("old1")
    assert legacy["plan_approved"] is False and legacy["state"] == "pending"


# ── answering from chat / voice ──────────────────────────────────────────────
def wait_for(task_id, state, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if task_engine.get_task(task_id)["state"] == state:
            return True
        time.sleep(0.05)
    return False


def test_a_chat_yes_approves_the_one_waiting_task_and_runs_it(engine):
    tools, _ = engine
    task = make(PLAN[:3])
    run(task["id"])
    reply = task_engine.answer_waiting_task("approve")
    assert "Approved" in reply and wait_for(task["id"], "completed")
    assert tools["mover_archivo"].calls == 1


def test_a_chat_no_stops_the_waiting_task(engine):
    task = make(PLAN[:3])
    run(task["id"])
    assert "stopped" in task_engine.answer_waiting_task("reject")
    assert task_engine.get_task(task["id"])["state"] == "cancelled"


def test_nothing_is_guessed_when_two_tasks_wait_or_the_question_is_old(engine, tmp_path):
    first, second = make(PLAN[:3]), make(PLAN[:3])
    run(first["id"])
    run(second["id"])
    assert task_engine.answer_waiting_task("approve") is None  # which one? ask in the panel
    task_engine.cancel_task(second["id"])
    old = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
    with sqlite3.connect(tmp_path / "tasks.db") as conn:
        conn.execute("UPDATE tasks SET updated=? WHERE id=?", (old, first["id"]))
    assert task_engine.answer_waiting_task("approve") is None  # stale approval question
    assert task_engine.get_task(first["id"])["state"] == "approval_required"


def test_chat_approval_is_refused_while_emergency_stop_is_on(engine):
    task = make(PLAN[:3])
    run(task["id"])
    emergency_stop.engage("test")
    try:
        assert "Emergency stop" in task_engine.answer_waiting_task("approve")
        assert task_engine.get_task(task["id"])["state"] != "completed"
    finally:
        emergency_stop.release()


def test_summary_tells_the_user_how_to_answer(engine):
    task = make(PLAN)
    text = task_engine.summarize(run(task["id"]))
    assert "approve" in text.lower() and "seri" in text.lower()
