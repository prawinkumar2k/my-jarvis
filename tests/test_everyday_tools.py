from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from core.reminders import ReminderStore
from core.security.tool_policy import get_tool_policy
from tools import _get_base_tools_impl, assistant_tools, pc_control

NEW_TOOLS = (
    "control_multimedia", "ajustar_brillo", "captura_pantalla", "organizar_ventanas",
    "poner_temporizador", "poner_alarma", "guardar_nota", "leer_notas", "borrar_nota",
    "estado_jarvis", "resumen_del_dia",
)


def test_new_tools_are_registered():
    names = {t.name for t in _get_base_tools_impl()}
    assert set(NEW_TOOLS) <= names
    assert get_tool_policy("control_multimedia").allowed_profiles == ("admin",)


@pytest.mark.parametrize(
    ("text", "minutes"),
    [("10", 10.0), ("5 min", 5.0), ("90 seconds", 1.5), ("1 hour 30 min", 90.0), ("2 mani", 120.0), ("soon", None)],
)
def test_duration_parsing(text, minutes):
    assert assistant_tools._parse_duration_minutes(text) == minutes


def test_alarm_time_parsing_rolls_to_tomorrow():
    now = datetime(2026, 10, 26, 8, 0)
    assert assistant_tools.minutes_until("7:30", now) == pytest.approx(23.5 * 60)
    assert assistant_tools.minutes_until("6 pm", now) == pytest.approx(10 * 60)
    assert assistant_tools.minutes_until("18:45", now) == pytest.approx(10.75 * 60)
    assert assistant_tools.minutes_until("25:00", now) is None


def test_timer_and_alarm_use_persistent_reminders(monkeypatch, tmp_path: Path):
    from core import reminders

    store = ReminderStore(tmp_path / "r.json")
    monkeypatch.setattr(reminders, "reminder_store", store)
    assert "Timer set for 5 min" in assistant_tools.poner_temporizador.invoke({"duracion": "5 min"})
    assert "Alarm set" in assistant_tools.poner_alarma.invoke({"hora": "7:30"})
    texts = [r["text"] for r in store.pending()]
    assert any("Timer done" in t for t in texts) and any("Alarm (7:30)" in t for t in texts)
    assert "Give a duration" in assistant_tools.poner_temporizador.invoke({"duracion": "forever"})


def test_notes_save_read_delete(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(assistant_tools, "_notes_path", lambda: tmp_path / "notes.json")
    assert "saved" in assistant_tools.guardar_nota.invoke({"texto": "Buy milk"})
    assert "saved" in assistant_tools.guardar_nota.invoke({"texto": "Call Ravi at 6"})
    assert "Not saved" in assistant_tools.guardar_nota.invoke({"texto": "my password is hunter2"})
    listing = assistant_tools.leer_notas.invoke({})
    assert listing.index("Call Ravi") < listing.index("Buy milk")  # newest first
    assert "Deleted" in assistant_tools.borrar_nota.invoke({"id_o_texto": "milk"})
    assert "Buy milk" not in assistant_tools.leer_notas.invoke({})


def test_health_check_reports_each_area(monkeypatch):
    monkeypatch.setattr(assistant_tools, "_internet_ok", lambda: False)
    report = assistant_tools.estado_jarvis.invoke({})
    assert "internet: PROBLEM (offline)" in report
    assert "ai:" in report and "microphone:" in report


def test_layout_math_covers_every_window():
    area = (0, 0, 1920, 1040)
    assert pc_control.layout_rects("split", 2, area) == [(0, 0, 960, 1040), (960, 0, 960, 1040)]
    assert len(pc_control.layout_rects("split", 3, area)) == 3  # falls back to grid
    assert pc_control.layout_rects("full", 1, area) == [(0, 0, 1920, 1040)]


def test_media_keys_validate_and_press(monkeypatch):
    pressed = []
    monkeypatch.setattr(pc_control, "IS_WINDOWS", True)
    monkeypatch.setattr(pc_control, "_press_key", pressed.append)
    assert "next" in pc_control.control_multimedia.invoke({"accion": "skip"})
    assert "play/pause" in pc_control.control_multimedia.invoke({"accion": "pause"})
    assert "Use one of" in pc_control.control_multimedia.invoke({"accion": "rewind"})
    assert pressed == [0xB0, 0xB3]


def test_brightness_reports_actual_value(monkeypatch):
    levels = iter([40, 50])
    monkeypatch.setattr(pc_control, "IS_WINDOWS", True)
    monkeypatch.setattr(pc_control, "read_brightness", lambda: next(levels))
    monkeypatch.setattr(pc_control, "_powershell", lambda script, timeout=15: None)
    assert pc_control.ajustar_brillo.invoke({"nivel": "up"}) == "Brightness set to 50%."
    monkeypatch.setattr(pc_control, "read_brightness", lambda: None)
    assert "does not allow" in pc_control.ajustar_brillo.invoke({"nivel": "70"})
