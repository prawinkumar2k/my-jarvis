"""Scheduled routines: schedule math, safety (only AUTO-tier tools), downtime, quiet hours, STOP, API, chat tools."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

import pytest
from core import routines
from core.security import emergency_stop


@pytest.fixture(autouse=True)
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(routines, "_path_override", tmp_path / "routines.json")
    monkeypatch.delenv("JARVIS_QUIET_HOURS", raising=False)
    monkeypatch.delenv("JARVIS_AI_MODE", raising=False)
    emergency_stop.release()
    yield
    emergency_stop.release()


def ran(log):
    def execute(routine, _profile):
        log.append(routine["tool"])
        return True, f"{routine['tool']} output"

    return execute


NOON = datetime(2026, 10, 27, 12, 0)


def test_daily_summary_is_scheduled_for_the_next_8am_and_survives_a_restart():
    routine = routines.add("Morning summary", "8:00", "daily", "resumen_del_dia", now=NOON)
    assert routine["time"] == "08:00" and routine["next_run"] == "2026-10-28T08:00:00"
    assert [r["name"] for r in routines.list_all()["routines"]] == ["Morning summary"]  # read back from disk


def test_runs_when_due_then_reschedules_and_records_the_result():
    routines.add("Summary", "08:00", "daily", "resumen_del_dia", now=NOON)
    log: list[str] = []
    assert routines.run_due(datetime(2026, 10, 27, 23, 0), execute=ran(log)) == []  # not due yet
    out = routines.run_due(datetime(2026, 10, 28, 8, 0, 20), execute=ran(log))
    assert log == ["resumen_del_dia"] and out[0]["ok"] and out[0]["missed"] is False
    assert routines.list_all()["routines"][0]["next_run"] == "2026-10-29T08:00:00"
    assert routines.run_due(datetime(2026, 10, 28, 8, 0, 40), execute=ran(log)) == []  # exactly once per day


def test_a_week_of_downtime_runs_once_flagged_missed_not_seven_times():
    routines.add("Summary", "08:00", "daily", "resumen_del_dia", now=NOON)
    log: list[str] = []
    out = routines.run_due(datetime(2026, 11, 3, 9, 30), execute=ran(log))
    assert len(out) == 1 and out[0]["missed"] is True
    assert routines.list_all()["routines"][0]["next_run"] == "2026-11-04T08:00:00"


def test_weekdays_skip_the_weekend_and_once_turns_itself_off():
    friday = datetime(2026, 10, 30, 12, 0)
    assert routines.next_run("08:00", "weekdays", friday) == datetime(2026, 11, 2, 8, 0)  # Monday
    routines.add("One shot", "13:00", "once", "estado_jarvis", now=NOON)
    routines.run_due(datetime(2026, 10, 27, 13, 1), execute=ran([]))
    assert routines.list_all()["routines"][0]["enabled"] is False
    assert routines.run_due(datetime(2026, 10, 28, 13, 1), execute=ran([])) == []


def test_quiet_hours_hold_routines_until_they_end(monkeypatch):
    monkeypatch.setenv("JARVIS_QUIET_HOURS", "22:00-07:00")
    routines.add("Night check", "23:00", "daily", "estado_jarvis", now=NOON)
    log: list[str] = []
    assert routines.run_due(datetime(2026, 10, 27, 23, 5), execute=ran(log)) == [] and log == []
    out = routines.run_due(datetime(2026, 10, 28, 7, 1), execute=ran(log))
    assert len(out) == 1 and out[0]["missed"] is True


def test_emergency_stop_prevents_runs():
    routines.add("Summary", "08:00", "daily", "resumen_del_dia", now=NOON)
    emergency_stop.engage("test")
    assert routines.run_due(datetime(2026, 10, 28, 8, 1), execute=ran([])) == []


@pytest.mark.parametrize(
    ("tool", "args", "why"),
    [("instalar_programa", {"id_paquete": "x"}, "approval"), ("controlar_pc", {"accion": "apagar"}, "approval"),
     ("matar_proceso", {"nombre": "chrome"}, "approval"), ("programar_rutina", {}, "cannot be scheduled"),
     ("no_such_tool", {}, "cannot be scheduled")],
)
def test_nothing_that_needs_approval_can_be_scheduled(tool, args, why):
    with pytest.raises(ValueError, match=why):
        routines.add("x", "08:00", "daily", tool, args, now=NOON)


@pytest.mark.parametrize(("clock", "repeat"), [("25:00", "daily"), ("8am", "daily"), ("08:00", "hourly"), ("", "daily")])
def test_bad_times_and_repeats_are_rejected(clock, repeat):
    with pytest.raises(ValueError):
        routines.add("x", clock, repeat, "resumen_del_dia", now=NOON)
    with pytest.raises(ValueError, match="name"):
        routines.add("  ", "08:00", "daily", "resumen_del_dia", now=NOON)


def test_a_tool_that_became_risky_is_not_run_unattended(monkeypatch):
    # In local-only mode the clipboard stays on this PC, so it may be scheduled...
    monkeypatch.setenv("JARVIS_AI_MODE", "local_only")
    routines.add("Clipboard peek", "08:00", "daily", "leer_portapapeles", now=NOON)
    # ...but if the mode later changes, reading it would need a yes, so the routine must not run on its own.
    monkeypatch.setenv("JARVIS_AI_MODE", "cloud_first")
    ok, text = routines._execute(routines.list_all()["routines"][0], "admin")
    assert ok is False and "needs approval" in text


def test_the_real_executor_runs_a_real_tool_through_the_guard(monkeypatch):
    seen = []
    from services import security_manager

    monkeypatch.setattr(security_manager, "_security_guard",
                        lambda tool, args, goal, source, profile_id: seen.append((tool, source)) or (True, ""))
    routines.add("Health", "08:00", "daily", "estado_jarvis", now=NOON)
    monkeypatch.setattr(routines, "_tool", lambda name: type("T", (), {"invoke": staticmethod(lambda a: "all good")})())
    out = routines.run_due(datetime(2026, 10, 28, 8, 1))
    assert seen == [("estado_jarvis", "routine")] and out[0]["ok"] and out[0]["text"] == "all good"
    monkeypatch.setattr(security_manager, "_security_guard", lambda *a, **k: (False, "blocked by policy"))
    routines.add("Health 2", "09:00", "daily", "estado_jarvis", now=NOON)
    blocked = routines.run_due(datetime(2026, 10, 28, 9, 1))
    assert blocked and blocked[0]["ok"] is False and "blocked" in blocked[0]["text"]


def test_manual_run_does_not_use_up_the_scheduled_run():
    routine = routines.add("Summary", "08:00", "daily", "resumen_del_dia", now=NOON)
    routines.run_due(datetime(2026, 10, 27, 14, 0), execute=ran([]), force_id=routine["id"])
    assert routines.list_all()["routines"][0]["next_run"] == routine["next_run"]
    assert routines.list_all()["results"][-1]["missed"] is False


def test_chat_tools_create_list_and_cancel():
    from tools import assistant_tools as tools

    assert "Routine 'Morning' set" in tools.programar_rutina.invoke({"nombre": "Morning", "hora": "07:30"})
    assert "Morning" in tools.ver_rutinas.invoke({})
    assert "not created" in tools.programar_rutina.invoke({"nombre": "Bad", "hora": "07:30", "herramienta": "instalar_programa"})
    assert "deleted" in tools.cancelar_rutina.invoke({"id_o_nombre": "morning"})
    assert "No routines" in tools.ver_rutinas.invoke({})


def test_api_create_list_run_delete_and_validation(monkeypatch):
    import jarvis_backend

    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    monkeypatch.setattr(routines, "_execute", lambda routine, profile: (True, "summary text"))
    origin = {"Origin": "http://localhost:5002"}

    async def run():
        client = jarvis_backend.app.test_client()
        bad = await client.post("/api/security/routines", json={"name": "x", "time": "99:00", "tool": "resumen_del_dia"}, headers=origin)
        risky = await client.post("/api/security/routines", json={"name": "x", "time": "08:00", "tool": "instalar_programa"}, headers=origin)
        created = await client.post("/api/security/routines", json={"name": "Summary", "time": "08:00", "repeat": "daily", "tool": "resumen_del_dia"}, headers=origin)
        rid = (await created.get_json())["routine"]["id"]
        await client.post(f"/api/security/routines/{rid}/run", headers=origin)
        listing = await (await client.get("/api/security/routines", headers=origin)).get_json()
        hostile = await client.post(f"/api/security/routines/{rid}/delete", headers={"Origin": "https://evil.example"})
        gone = await client.post(f"/api/security/routines/{rid}/delete", headers=origin)
        missing = await client.post("/api/security/routines/nope/run", headers=origin)
        return bad.status_code, risky.status_code, created.status_code, listing, hostile.status_code, gone.status_code, missing.status_code

    bad, risky, created, listing, hostile, gone, missing = asyncio.run(run())
    assert (bad, risky, created, hostile, gone, missing) == (400, 400, 201, 403, 200, 404)
    assert listing["routines"][0]["name"] == "Summary" and listing["results"][-1]["text"] == "summary text"
    assert "resumen_del_dia" in listing["tools"]
    assert json.dumps(listing)  # serialisable
