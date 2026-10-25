from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from core.reminders import ReminderStore


def test_reminders_survive_a_new_store_instance(tmp_path: Path):
    path = tmp_path / "reminders.json"
    now = datetime(2026, 10, 26, 9, 0, 0)
    ReminderStore(path).add("Call Amma", 30, now=now)
    restarted = ReminderStore(path)  # simulates a JARVIS restart
    pending = restarted.pending()
    assert [r["text"] for r in pending] == ["Call Amma"]
    assert pending[0]["due"] == "2026-10-26T09:30:00"


def test_due_reminders_fire_once_and_flag_missed(tmp_path: Path):
    store = ReminderStore(tmp_path / "r.json")
    start = datetime(2026, 10, 26, 9, 0, 0)
    store.add("on time", 1, now=start)
    store.add("while closed", 1, now=start - timedelta(hours=2))
    store.add("later", 60, now=start)
    shown = store.take_unshown(now=start + timedelta(minutes=1, seconds=5))
    assert {r["text"]: r["missed"] for r in shown} == {"on time": False, "while closed": True}
    assert store.take_unshown(now=start + timedelta(minutes=2)) == []  # never delivered twice
    assert [r["text"] for r in store.pending()] == ["later"]


def test_scheduler_fire_then_ui_still_shows_it(tmp_path: Path):
    store = ReminderStore(tmp_path / "r.json")
    now = datetime(2026, 10, 26, 9, 0, 0)
    store.add("standup", 0, now=now)
    assert [r["text"] for r in store.fire_due(now=now)] == ["standup"]
    assert [r["text"] for r in store.take_unshown(now=now)] == ["standup"]


def test_cancel_by_id_or_unique_text(tmp_path: Path):
    store = ReminderStore(tmp_path / "r.json")
    a = store.add("pay electricity bill", 10)
    store.add("pay internet bill", 20)
    assert store.cancel("pay") is None  # ambiguous: nothing cancelled
    assert store.cancel("electricity")["id"] == a["id"]
    assert [r["text"] for r in store.pending()] == ["pay internet bill"]
    assert store.cancel("nothing-like-this") is None


def test_corrupt_file_degrades_gracefully(tmp_path: Path):
    path = tmp_path / "r.json"
    path.write_text("{not json", encoding="utf-8")
    store = ReminderStore(path)
    assert store.pending() == []
    store.add("works again", 5)
    assert len(store.pending()) == 1


def test_tools_use_the_persistent_store(monkeypatch, tmp_path: Path):
    from core import reminders
    from core.service_container import services
    from tools import utilities

    store = ReminderStore(tmp_path / "r.json")
    monkeypatch.setattr(reminders, "reminder_store", store)
    monkeypatch.setattr(services, "log_event", lambda *a, **k: None)
    assert "saved" in utilities.poner_recordatorio.invoke({"texto": "drink water", "minutos": 15})
    assert "drink water" in utilities.listar_recordatorios.invoke({})
    assert "Cancelled" in utilities.cancelar_recordatorio.invoke({"id_o_texto": "water"})
    assert utilities.listar_recordatorios.invoke({}) == "No pending reminders."
