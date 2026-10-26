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
