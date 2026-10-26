"""
Companion tools: timers, alarms, voice notes, health check and daily summary.

Timers and alarms use the persistent reminder store, so they survive restarts
and are spoken by the UI when due. Notes are kept in the runtime data folder.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.request
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from langchain_core.tools import tool

_notes_lock = threading.RLock()


# ── Timers and alarms ─────────────────────────────────────────────
def _parse_duration_minutes(value: str) -> float | None:
    text = str(value or "").strip().lower()
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return float(text)
    total, found = 0.0, False
    for amount, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(h|hr|hour|hours|mani|m|min|mins|minute|minutes|nimisham|s|sec|secs|second|seconds)\b", text):
        found = True
        n = float(amount)
        total += n * 60 if unit in {"h", "hr", "hour", "hours", "mani"} else (n / 60 if unit.startswith("s") else n)
    return total if found else None


@tool
def poner_temporizador(duracion: str, etiqueta: str = "Timer") -> str:
    """Start a countdown timer, e.g. duracion '5 min', '90 seconds', '1 hour 30 min' or just minutes '10'.
    JARVIS announces it when done (survives restarts)."""
    from core.reminders import reminder_store

    minutes = _parse_duration_minutes(duracion)
    if minutes is None or minutes <= 0 or minutes > 24 * 60:
        return "Give a duration like '5 min' or '90 seconds' (up to 24 hours)."
    label = str(etiqueta or "Timer").strip()[:80] or "Timer"
    item = reminder_store.add(f"{label} done ({_human_minutes(minutes)})", minutes)
    return f"Timer set for {_human_minutes(minutes)}. Ends at {item['due'][11:16]}."


def _human_minutes(minutes: float) -> str:
    seconds = round(minutes * 60)
    if seconds < 60:
        return f"{seconds} seconds"
    hours, rest = divmod(seconds // 60, 60)
    return f"{hours} h {rest} min" if hours else f"{rest} min"


def minutes_until(clock: str, now: datetime | None = None) -> float | None:
    """Minutes from now until the next occurrence of HH:MM (24 h) or H:MM am/pm."""
    now = now or datetime.now()
    match = re.fullmatch(r"\s*(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\s*", str(clock or "").lower())
    if not match:
        return None
    hour, minute, meridiem = int(match.group(1)), int(match.group(2) or 0), match.group(3)
    if meridiem:
        hour = hour % 12 + (12 if meridiem.startswith("p") else 0)
    if hour > 23 or minute > 59:
        return None
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds() / 60


@tool
def poner_alarma(hora: str, etiqueta: str = "Alarm") -> str:
    """Set an alarm for a clock time today or tomorrow, e.g. '7:30', '6 am', '18:45'."""
    from core.reminders import reminder_store

    minutes = minutes_until(hora)
    if minutes is None:
        return "Give a time like '7:30', '6 am' or '18:45'."
    label = str(etiqueta or "Alarm").strip()[:80] or "Alarm"
    item = reminder_store.add(f"{label} ({hora.strip()})", minutes)
    day = "tomorrow" if item["due"][:10] != datetime.now().strftime("%Y-%m-%d") else "today"
    return f"Alarm set for {item['due'][11:16]} {day}."


# ── Notes ─────────────────────────────────────────────────────────
def _notes_path() -> Path:
    from core.runtime_paths import resolve_runtime_paths

    return resolve_runtime_paths().memory / "notes.json"


def _load_notes() -> list[dict]:
    try:
        data = json.loads(_notes_path().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save_notes(notes: list[dict]) -> None:
    path = _notes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notes[-500:], ensure_ascii=False, indent=1), encoding="utf-8")


@tool
def guardar_nota(texto: str) -> str:
    """Save a quick note the user dictates ('idha note pannu: ...', 'note: buy milk')."""
    from core.privacy import looks_sensitive

    text = str(texto or "").strip()
    if not text:
        return "The note is empty."
    if looks_sensitive(text):
        return "Not saved: that looks like a password, key, code or card number."
    with _notes_lock:
        notes = _load_notes()
        notes.append({"id": uuid.uuid4().hex[:6], "text": text[:1000], "at": datetime.now().isoformat(timespec="minutes")})
        _save_notes(notes)
    return f"Note saved ({len(notes)} total)."


@tool
def leer_notas(cantidad: int = 10) -> str:
    """Read the most recent notes (newest first)."""
    notes = _load_notes()
    if not notes:
        return "No notes yet."
    count = max(1, min(int(cantidad or 10), 50))
    lines = [f"- [{n['id']}] {n['at'].replace('T', ' ')}: {n['text']}" for n in reversed(notes[-count:])]
    return "Your notes:\n" + "\n".join(lines)


@tool
def borrar_nota(id_o_texto: str) -> str:
    """Delete one note by its id from leer_notas or a unique word in it."""
    ref = str(id_o_texto or "").strip().lower()
    with _notes_lock:
        notes = _load_notes()
        matches = [n for n in notes if n["id"] == ref] or [n for n in notes if ref and ref in n["text"].lower()]
        if len(matches) != 1:
            return "I could not find exactly one note matching that."
        notes.remove(matches[0])
        _save_notes(notes)
    return f"Deleted note: '{matches[0]['text'][:80]}'."


# ── Health check and daily summary ────────────────────────────────
def _internet_ok() -> bool:
    try:
        with urllib.request.urlopen("https://www.google.com/generate_204", timeout=4) as response:
            return response.status in (200, 204)
    except Exception:
        return False


def ping_ai(timeout: float = 15.0) -> dict:
    """One tiny request to the active AI model: ok, model, latency_ms, problem."""
    import time

    from core.brain import brain_state
    from core.errors import LLM_FAILURE_MESSAGES, classify_llm_failure

    model = brain_state.llm
    if model is None:
        return {"ok": False, "model": "", "latency_ms": None, "problem": "not_configured"}
    name = str(getattr(model, "model_name", "") or getattr(model, "model", "") or "")
    outcome: dict = {}

    def call():
        start = time.monotonic()
        try:
            from langchain_core.messages import HumanMessage

            model.invoke([HumanMessage(content="Reply with the single word OK.")])
            outcome["latency_ms"] = int((time.monotonic() - start) * 1000)
        except Exception as exc:
            outcome["problem"] = classify_llm_failure(exc)

    worker = threading.Thread(target=call, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        outcome["problem"] = "timeout"
    problem = outcome.get("problem")
    answered = str(getattr(model, "last_model", "") or "")
    return {
        "ok": problem is None,
        "model": answered if problem is None and answered else name,
        "latency_ms": outcome.get("latency_ms"),
        "problem": problem,
        "message": LLM_FAILURE_MESSAGES.get(problem or "", "") if problem else "",
    }


def collect_health() -> dict:
    checks: dict[str, tuple[bool, str]] = {}
    checks["internet"] = (ok := _internet_ok(), "online" if ok else "offline")
    try:
        ai = ping_ai()
        detail = f"{ai['model']} answered in {ai['latency_ms']} ms" if ai["ok"] else (ai["problem"] or "unavailable")
        checks["ai"] = (ai["ok"], detail)
    except Exception:
        checks["ai"] = (False, "unavailable")
    try:
        import sounddevice

        mic = sounddevice.query_devices(kind="input")
        checks["microphone"] = (True, str(mic.get("name", "found"))[:40])
    except Exception:
        checks["microphone"] = (False, "not found")
    try:
        from voice.wake_word import wake_word_listener

        on = wake_word_listener.running
        checks["wake_word"] = (on, "listening" if on else (wake_word_listener.error or "off"))
    except Exception:
        checks["wake_word"] = (False, "unavailable")
    try:
        from core.security import emergency_stop

        stopped = emergency_stop.is_engaged()
        checks["actions"] = (not stopped, "emergency stop ON" if stopped else "allowed")
    except Exception:
        pass
    try:
        import psutil

        battery = psutil.sensors_battery()
        if battery is not None:
            low = battery.percent < 20 and not battery.power_plugged
            checks["battery"] = (not low, f"{round(battery.percent)}%{' charging' if battery.power_plugged else ''}")
    except Exception:
        pass
    return checks


@tool
def estado_jarvis() -> str:
    """JARVIS self check ('nee ok-a?', 'are you working?'): internet, AI, microphone, wake word, actions, battery."""
    checks = collect_health()
    problems = [k for k, (ok, _) in checks.items() if not ok]
    lines = [f"- {name}: {'OK' if ok else 'PROBLEM'} ({detail})" for name, (ok, detail) in checks.items()]
    head = "All systems OK." if not problems else f"{len(problems)} problem(s): {', '.join(problems)}."
    return head + "\n" + "\n".join(lines)


@tool
def resumen_del_dia() -> str:
    """Summary of today: notes taken today, reminders due today and pending, and system status."""
    from core.reminders import reminder_store

    today = datetime.now().strftime("%Y-%m-%d")
    notes_today = [n["text"] for n in _load_notes() if n.get("at", "").startswith(today)]
    pending = reminder_store.pending()
    due_today = [r["text"] for r in pending if r["due"].startswith(today)]
    parts = [f"Notes today: {len(notes_today)}" + (f" ({'; '.join(t[:40] for t in notes_today[-3:])})" if notes_today else "") + "."]
    parts.append(f"Reminders still due today: {len(due_today)}" + (f" ({'; '.join(due_today[:3])})" if due_today else "") + ".")
    if len(pending) > len(due_today):
        parts.append(f"{len(pending) - len(due_today)} more reminder(s) later.")
    health = collect_health()
    problems = [k for k, (ok, _) in health.items() if not ok]
    parts.append("All systems OK." if not problems else "Needs attention: " + ", ".join(problems) + ".")
    return " ".join(parts)


@tool
def diagnostico_sistema() -> str:
    """Full live system report: CPU, memory, every drive and its health, battery, GPU usage and VRAM,
    biggest processes, and whether winget, FFmpeg and Ollama are available."""
    from core import diagnostics

    return diagnostics.summarize(diagnostics.collect())
