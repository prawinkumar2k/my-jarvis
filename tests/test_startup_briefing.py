from __future__ import annotations

from datetime import datetime

from core.startup_briefing import build_briefing, collect_status

STATUS = {
    "now": datetime(2026, 10, 26, 9, 5),
    "cpu": 12,
    "ram": 48,
    "battery": 80,
    "charging": True,
    "reminders": 2,
}


def test_english_briefing_has_time_date_and_status():
    text = build_briefing("en", STATUS)
    assert text.startswith("Good morning. It is 9:05 AM, Monday, 26 October.")
    assert "Battery at 80 percent, charging." in text
    assert "CPU at 12 percent, memory at 48 percent." in text
    assert "2 pending reminders" in text


def test_thanglish_briefing_uses_english_letters_only():
    text = build_briefing("ta", {**STATUS, "now": datetime(2026, 10, 26, 18, 30), "charging": False})
    assert text.startswith("Maalai vanakkam! Ippo time 6:30 PM, inniku Thingalkizhamai, 26 October.")
    assert "battery-la odudhu" in text
    assert all(ord(ch) < 0x0B80 or ord(ch) > 0x0BFF for ch in text)


def test_missing_sensors_are_omitted_not_invented():
    text = build_briefing("en", {"now": datetime(2026, 10, 26, 14, 0), "reminders": 0})
    assert "Battery" not in text and "CPU" not in text and "reminder" not in text
    assert text == "Good afternoon. It is 2:00 PM, Monday, 26 October. All systems ready."


def test_collect_status_reads_live_values():
    status = collect_status()
    assert isinstance(status["now"], datetime)
    assert 0 <= status.get("cpu", 0) <= 100
