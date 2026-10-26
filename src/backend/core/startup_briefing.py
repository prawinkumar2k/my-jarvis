"""Spoken status report when JARVIS opens: time, date and system health.

All values come from the live system (psutil, clock, reminder store); nothing
is invented. Text is short so the voice reads it in a few seconds.
"""

from __future__ import annotations

import os
from datetime import datetime

import psutil

_DAYS_TA = ("Thingal", "Sevvai", "Budhan", "Vyazhan", "Velli", "Sani", "Nyayiru")


def collect_status() -> dict:
    status: dict = {"now": datetime.now()}
    try:
        status["cpu"] = round(psutil.cpu_percent(interval=0.3))
        status["ram"] = round(psutil.virtual_memory().percent)
        status["disk_free_gb"] = round(psutil.disk_usage(os.path.abspath(os.sep)).free / 1024**3)
    except Exception:
        pass
    try:
        battery = psutil.sensors_battery()
    except Exception:
        battery = None
    if battery is not None:
        status["battery"] = round(battery.percent)
        status["charging"] = bool(battery.power_plugged)
    try:
        from core.reminders import reminder_store

        status["reminders"] = len(reminder_store.pending())
    except Exception:
        status["reminders"] = 0
    return status


def _time_12h(now: datetime) -> str:
    return now.strftime("%I:%M %p").lstrip("0")


def build_briefing(language: str, status: dict | None = None) -> str:
    s = status or collect_status()
    now: datetime = s["now"]
    lang = str(language or "en").lower()
    hour = now.hour
    if lang.startswith("ta"):
        greet = "Kaalai vanakkam" if hour < 12 else ("Madhiya vanakkam" if hour < 17 else "Maalai vanakkam")
        parts = [f"{greet}! Ippo time {_time_12h(now)}, inniku {_DAYS_TA[now.weekday()]}kizhamai, {now.day} {now.strftime('%B')}."]
        if "battery" in s:
            charge = "charge aagudhu" if s["charging"] else "battery-la odudhu"
            parts.append(f"Battery {s['battery']} percent, {charge}.")
        if "cpu" in s:
            parts.append(f"CPU {s['cpu']} percent, memory {s['ram']} percent use-la irukku.")
        if s.get("reminders"):
            parts.append(f"{s['reminders']} reminder pending-la irukku.")
        parts.append("Ella systems-um ready. Enna pannanum?")
    elif lang.startswith("es"):
        greet = "Buenos días" if hour < 12 else ("Buenas tardes" if hour < 20 else "Buenas noches")
        parts = [f"{greet}. Son las {now.strftime('%H:%M')} del {now.day}/{now.month}/{now.year}."]
        if "battery" in s:
            parts.append(f"Batería al {s['battery']} por ciento{', cargando' if s['charging'] else ''}.")
        if "cpu" in s:
            parts.append(f"CPU al {s['cpu']} por ciento y memoria al {s['ram']} por ciento.")
        if s.get("reminders"):
            parts.append(f"Tienes {s['reminders']} recordatorios pendientes.")
        parts.append("Todos los sistemas listos.")
    else:
        greet = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
        parts = [f"{greet}. It is {_time_12h(now)}, {now.strftime('%A')}, {now.day} {now.strftime('%B')}."]
        if "battery" in s:
            parts.append(f"Battery at {s['battery']} percent{', charging' if s['charging'] else ''}.")
        if "cpu" in s:
            parts.append(f"CPU at {s['cpu']} percent, memory at {s['ram']} percent.")
        if s.get("reminders"):
            parts.append(f"You have {s['reminders']} pending reminder{'s' if s['reminders'] != 1 else ''}.")
        parts.append("All systems ready.")
    return " ".join(parts)
