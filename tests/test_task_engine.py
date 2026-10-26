"""Task engine tests. Tools and the security guard are stubbed (no real actions run)."""

from __future__ import annotations

from pathlib import Path

import pytest
from core import task_engine
from core.security import emergency_stop


class FakeTool:
    def __init__(self, name, fail_times=0):
        self.name, self.fail_times, self.calls = name, fail_times, 0

    def invoke(self, args):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"{self.name} transient error")
        return f"{self.name} ok {args}"


@pytest.fixture
def engine(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(task_engine, "_db_path_override", tmp_path / "tasks.db")
    fakes = {
        "open_app": FakeTool("open_app"),
        "flaky": FakeTool("flaky", fail_times=1),
        "broken": FakeTool("broken", fail_times=99),
        "delete_file": FakeTool("delete_file"),
    }
    guard_calls = []

    def guard(tool, args, goal, source, profile_id):
        guard_calls.append((tool, source))
        return (tool != "forbidden", "blocked by policy")

    monkeypatch.setattr(task_engine, "_tool", lambda name: fakes.get(name) or (FakeTool(name) if name == "forbidden" else None))
    monkeypatch.setattr(task_engine, "_needs_approval", lambda name: name == "delete_file")
    monkeypatch.setattr("services.security_manager._security_guard", guard)
    emergency_stop.release()
    yield fakes, guard_calls
    emergency_stop.release()


def _run(task_id):
    return task_engine.run_task(task_id, sleep=lambda _s: None)


def test_multi_step_task_completes_in_order(engine):
    fakes, guard_calls = engine
    task = task_engine.create_task("work setup", [{"tool": "open_app", "args": {"n": 1}}, {"tool": "flaky", "args": {}}])
    done = _run(task["id"])
    assert done["state"] == "completed"
    assert [s["state"] for s in done["steps"]] == ["completed", "completed"]
    assert done["steps"][1]["attempts"] == 2  # one bounded retry for the transient failure
    assert [c[0] for c in guard_calls] == ["open_app", "flaky"]  # every step went through the guard


def test_repeated_failure_stops_after_bounded_retries(engine):
    fakes, _ = engine
    task = task_engine.create_task("x", [{"tool": "broken", "args": {}}, {"tool": "open_app", "args": {}}])
    done = _run(task["id"])
    assert done["state"] == "failed"
    assert fakes["broken"].calls == task_engine.MAX_RETRIES + 1
    assert fakes["open_app"].calls == 0  # later steps never ran


def test_risky_step_waits_for_approval_then_resumes_without_repeating(engine):
    fakes, guard_calls = engine
    task = task_engine.create_task("cleanup", [{"tool": "open_app", "args": {}}, {"tool": "delete_file", "args": {"p": "a"}}])
    paused = _run(task["id"])
    assert paused["state"] == "approval_required"
    assert fakes["delete_file"].calls == 0
    task_engine.approve_step(task["id"])
    done = _run(task["id"])
    assert done["state"] == "completed"
    assert fakes["open_app"].calls == 1  # completed step reused, not repeated
    assert ("delete_file", "control_panel") in guard_calls  # approval travels as control-panel confirmation


def test_risky_steps_are_never_retried(engine, monkeypatch):
    fakes, _ = engine
    fakes["delete_file"].fail_times = 5
    task = task_engine.create_task("x", [{"tool": "delete_file", "args": {}}])
    _run(task["id"])
    task_engine.approve_step(task["id"])
    assert _run(task["id"])["state"] == "failed"
    assert fakes["delete_file"].calls == 1


def test_restart_marks_running_tasks_interrupted_and_resume_skips_done_steps(engine):
    fakes, _ = engine
    task = task_engine.create_task("x", [{"tool": "open_app", "args": {}}, {"tool": "flaky", "args": {}}])
    task_engine._set_task(task["id"], "running")
    task_engine._set_step(task["id"], 0, state="completed", result="done before crash")
    task_engine._set_step(task["id"], 1, state="running")
    assert task_engine.recover_after_restart() == 1
    assert task_engine.get_task(task["id"])["state"] == "interrupted"
    done = _run(task["id"])
    assert done["state"] == "completed"
    assert fakes["open_app"].calls == 0  # finished before the crash, not repeated


def test_cancel_and_emergency_stop(engine):
    fakes, _ = engine
    task = task_engine.create_task("x", [{"tool": "open_app", "args": {}}])
    assert task_engine.cancel_task(task["id"])["state"] == "cancelled"
    assert _run(task["id"])["state"] == "cancelled" and fakes["open_app"].calls == 0
    other = task_engine.create_task("y", [{"tool": "open_app", "args": {}}])
    emergency_stop.engage("test")
    assert _run(other["id"])["state"] == "interrupted"
    assert fakes["open_app"].calls == 0


def test_permission_denial_fails_the_task(engine):
    task = task_engine.create_task("x", [{"tool": "forbidden", "args": {}}])
    done = _run(task["id"])
    assert done["state"] == "failed" and "blocked" in done["error"]


def test_validation_rejects_unknown_tools_and_too_many_steps(engine):
    with pytest.raises(ValueError, match="unknown tool"):
        task_engine.create_task("x", [{"tool": "rm_rf", "args": {}}])
    with pytest.raises(ValueError):
        task_engine.create_task("x", [{"tool": "open_app", "args": {}}] * 13)


def test_reject_stops_the_task_without_running_the_risky_step(engine):
    fakes, _ = engine
    task = task_engine.create_task("x", [{"tool": "delete_file", "args": {}}, {"tool": "open_app", "args": {}}])
    _run(task["id"])
    rejected = task_engine.reject_step(task["id"])
    assert rejected["state"] == "cancelled" and "rejected" in rejected["error"]
    assert rejected["steps"][0]["state"] == "rejected"
    assert _run(task["id"])["state"] == "cancelled"
    assert fakes["delete_file"].calls == 0 and fakes["open_app"].calls == 0


def test_a_second_run_while_running_does_not_repeat_steps(engine, monkeypatch):
    import threading

    fakes, _ = engine
    gate, entered = threading.Event(), threading.Event()
    slow = FakeTool("open_app")

    def invoke(args):
        entered.set()
        gate.wait(5)
        return FakeTool.invoke(slow, args)

    slow.invoke = invoke
    fakes["open_app"] = slow
    task = task_engine.create_task("x", [{"tool": "open_app", "args": {}}])
    worker = threading.Thread(target=_run, args=(task["id"],))
    worker.start()
    assert entered.wait(5)
    second = _run(task["id"])  # double click while the first run is busy
    assert second["active"] is True and second["state"] == "running"
    gate.set()
    worker.join(5)
    assert slow.calls == 1
    done = task_engine.get_task(task["id"])
    assert done["state"] == "completed" and done["active"] is False
    assert done["started"] and done["finished"]


def test_old_database_without_timestamp_columns_is_upgraded(engine, tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, goal TEXT NOT NULL, state TEXT NOT NULL,"
                     " created TEXT NOT NULL, updated TEXT NOT NULL, error TEXT DEFAULT '')")
        conn.execute("INSERT INTO tasks VALUES ('old1', 'legacy', 'interrupted', 'c', 'u', '')")
    task_engine._db_path_override = db
    legacy = task_engine.get_task("old1")
    assert legacy["state"] == "interrupted" and legacy["started"] == "" and legacy["steps"] == []


def test_task_routes_enforce_eligibility_and_origin(engine, monkeypatch):
    import asyncio

    import jarvis_backend

    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    fakes, _ = engine
    risky = task_engine.create_task("cleanup", [{"tool": "delete_file", "args": {}}])
    _run(risky["id"])
    done = task_engine.create_task("done", [{"tool": "open_app", "args": {}}])
    _run(done["id"])

    async def call():
        client = jarvis_backend.app.test_client()
        h = {"Origin": "http://localhost:5002"}
        out = {}
        out["list"] = await (await client.get("/api/security/tasks", headers=h)).get_json()
        out["hostile"] = (await client.post(f"/api/security/tasks/{risky['id']}/approve", headers={"Origin": "https://evil.example"})).status_code
        out["bad"] = (await client.post(f"/api/security/tasks/{risky['id']}/explode", headers=h)).status_code
        out["missing"] = (await client.post("/api/security/tasks/nope/cancel", headers=h)).status_code
        out["resume_waiting"] = (await client.post(f"/api/security/tasks/{risky['id']}/resume", headers=h)).status_code
        out["approve_done"] = (await client.post(f"/api/security/tasks/{done['id']}/approve", headers=h)).status_code
        out["cancel_done"] = (await client.post(f"/api/security/tasks/{done['id']}/cancel", headers=h)).status_code
        approve = await client.post(f"/api/security/tasks/{risky['id']}/approve", headers=h)
        out["approve"] = approve.status_code
        for _ in range(50):
            if task_engine.get_task(risky["id"])["state"] == "completed":
                break
            await asyncio.sleep(0.05)
        out["approve_again"] = (await client.post(f"/api/security/tasks/{risky['id']}/approve", headers=h)).status_code
        return out

    out = asyncio.run(call())
    assert {t["id"] for t in out["list"]["tasks"]} >= {risky["id"], done["id"]}
    assert out["hostile"] == 403 and out["bad"] == 400 and out["missing"] == 404
    assert out["resume_waiting"] == 409  # resume never bypasses an approval
    assert out["approve_done"] == 409 and out["cancel_done"] == 409
    assert out["approve"] == 202
    assert task_engine.get_task(risky["id"])["state"] == "completed"
    assert fakes["delete_file"].calls == 1
    assert out["approve_again"] == 409  # a repeated click cannot run it twice
