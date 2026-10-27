"""Repeating reminders and quiet hours (fixed clock, temporary store)."""

from __future__ import annotations

from datetime import datetime

import pytest
from core import reminders
from core.reminders import ReminderStore, in_quiet_hours, next_occurrence, quiet_hours


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("JARVIS_QUIET_HOURS", raising=False)
    return ReminderStore(tmp_path / "reminders.json")


def test_daily_reminder_fires_and_schedules_the_next_day(store):
    now = datetime(2026, 10, 27, 20, 0)
    item = store.add("medicine", 60, now, repeat="daily")  # 21:00 today
    fired = store.fire_due(datetime(2026, 10, 27, 21, 0, 30))
    assert [f["id"] for f in fired] == [item["id"]]
    nxt = store.pending()
    assert len(nxt) == 1 and nxt[0]["due"] == "2026-10-28T21:00:00" and nxt[0]["repeat"] == "daily"


def test_long_downtime_gives_one_missed_fire_not_a_flood(store):
    store.add("standup", 60, datetime(2026, 10, 20, 8, 0), repeat="daily")  # first due 2026-10-20 09:00
    fired = store.fire_due(datetime(2026, 10, 27, 12, 0))  # JARVIS was off for a week
    assert len(fired) == 1 and fired[0]["missed"] is True
    assert [p["due"] for p in store.pending()] == ["2026-10-28T09:00:00"]


def test_weekdays_skip_the_weekend(store):
    friday = datetime(2026, 10, 30, 9, 0)
    assert friday.weekday() == 4
    assert next_occurrence(friday, "weekdays", friday) == datetime(2026, 11, 2, 9, 0)  # Monday
    item = store.add("work", 60 * 24, friday, repeat="weekdays")  # would land on Saturday
    assert item["due"].startswith("2026-11-02")


def test_unknown_repeat_is_rejected(store):
    with pytest.raises(ValueError):
        store.add("x", 5, repeat="hourly")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("22:00-07:00", (1320, 420)), ("13:00-14:30", (780, 870)), ("", None), ("junk", None), ("25:00-07:00", None), ("08:00-08:00", None)],
)
def test_quiet_hours_parsing(value, expected):
    assert quiet_hours(value) == expected


def test_quiet_window_across_midnight():
    window = quiet_hours("22:00-07:00")
    assert in_quiet_hours(datetime(2026, 10, 27, 23, 30), window)
    assert in_quiet_hours(datetime(2026, 10, 28, 6, 59), window)
    assert not in_quiet_hours(datetime(2026, 10, 28, 7, 0), window)
    assert not in_quiet_hours(datetime(2026, 10, 27, 21, 59), window)


def test_quiet_hours_hold_reminders_but_not_alarms_or_timers(store, monkeypatch):
    monkeypatch.setenv("JARVIS_QUIET_HOURS", "22:00-07:00")
    start = datetime(2026, 10, 27, 22, 0)
    reminder = store.add("call ravi", 30, start)
    alarm = store.add("Alarm (6 am)", 8 * 60, start, kind="alarm")
    timer = store.add("Tea done", 10, start, kind="timer")
    assert [f["id"] for f in store.fire_due(datetime(2026, 10, 27, 22, 40))] == [timer["id"]]
    assert [f["id"] for f in store.fire_due(datetime(2026, 10, 28, 6, 0))] == [alarm["id"]]  # alarm rings in quiet hours
    held = store.fire_due(datetime(2026, 10, 28, 7, 1))  # quiet hours over
    assert [f["id"] for f in held] == [reminder["id"]] and held[0]["missed"] is True


def test_recurring_reminder_tool(monkeypatch, tmp_path):
    from tools import assistant_tools

    test_store = ReminderStore(tmp_path / "r.json")
    monkeypatch.setattr(reminders, "reminder_store", test_store)
    out = assistant_tools.recordatorio_recurrente.invoke({"texto": "walk", "hora": "7 pm", "repetir": "every day"})
    assert "daily" in out and test_store.pending()[0]["repeat"] == "daily"
    assert "Repeat must be" in assistant_tools.recordatorio_recurrente.invoke({"texto": "x", "hora": "7 pm", "repetir": "hourly"})
    assert "Give a time" in assistant_tools.recordatorio_recurrente.invoke({"texto": "x", "hora": "soon"})
