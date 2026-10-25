"""Truthful feature registry for the companion experience.

Each feature has one of five states. Some are computed at runtime from the
actual configuration, so JARVIS (and the UI) describe what this installation
can really do. Update VERIFIED entries only with evidence in docs/TEST_REPORT.md.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import asdict, dataclass

VERIFIED = "verified"
UNTESTED = "untested_here"
NEEDS_CONFIG = "needs_configuration"
NEEDS_HARDWARE = "needs_hardware_or_permission"
NOT_IMPLEMENTED = "not_implemented"

STATE_LABELS = {
    VERIFIED: "Available and verified",
    UNTESTED: "Available, not tested on this machine",
    NEEDS_CONFIG: "Requires configuration or API credentials",
    NEEDS_HARDWARE: "Requires hardware or permissions",
    NOT_IMPLEMENTED: "Not implemented",
}


@dataclass(frozen=True)
class Capability:
    key: str
    name: str
    state: str
    note: str = ""


def _flag(name: str) -> bool:
    return str(os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _has_llm() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GROQ_API_KEY"))


def _when(condition: bool, yes: str, no: str) -> str:
    return yes if condition else no


def _entries() -> list[Capability]:
    llm = _has_llm()
    gemini = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    files_on = _flag("JARVIS_FILE_TOOLS_ENABLED") or _flag("JARVIS_SYSTEM_TOOLS_ENABLED")
    playwright = importlib.util.find_spec("playwright") is not None
    wake_engine = importlib.util.find_spec("openwakeword") is not None and importlib.util.find_spec("sounddevice") is not None
    return [
        Capability("conversation", "Conversation in Thanglish, English and Tamil", _when(llm, UNTESTED, NEEDS_CONFIG),
                   "Needs GEMINI_API_KEY or GROQ_API_KEY." if not llm else "Language detection is verified; reply quality depends on the AI model."),
        Capability("language_detection", "Detecting Tamil script / Thanglish / English per message", VERIFIED),
        Capability("open_apps", "Opening Windows applications", VERIFIED),
        Capability("system_info", "CPU, memory, disk, battery and uptime", VERIFIED),
        Capability("windows_settings", "Opening Windows Settings pages", UNTESTED),
        Capability("file_read", "Listing and searching files in allowed folders", VERIFIED),
        Capability("file_write", "Create, copy, move, rename, delete (Recycle Bin), organize files",
                   _when(files_on, VERIFIED, NEEDS_CONFIG), "" if files_on else "Set JARVIS_FILE_TOOLS_ENABLED=true."),
        Capability("memory", "Saving, listing, editing and forgetting memories; private mode", VERIFIED,
                   "Secrets (passwords, keys, codes, cards) are refused."),
        Capability("emergency_stop", "Emergency STOP of all actions and live voice", VERIFIED),
        Capability("login_startup", "Starting after Windows sign-in", VERIFIED, "Real sign-out/sign-in not yet tested."),
        Capability("voice_push_to_talk", "Voice button with speech-to-text", NEEDS_HARDWARE, "Needs a microphone and permission."),
        Capability("voice_live", "Real-time two-way voice with interruption (Gemini Live)", _when(gemini, NEEDS_HARDWARE, NEEDS_CONFIG),
                   "Needs a microphone." if gemini else "Needs GEMINI_API_KEY and a microphone."),
        Capability("speech_output", "Speaking replies (English voice; Thanglish pronounced by it)", VERIFIED),
        Capability("tamil_speech_offline", "Speaking Tamil offline", NOT_IMPLEMENTED, "No Tamil local voice is bundled."),
        Capability("wake_word_browser", "\"Jarvis\" wake phrase via browser speech recognition", NEEDS_HARDWARE, "Online; needs a microphone."),
        Capability("wake_word_offline", "Offline \"Hey Jarvis\" wake word (openWakeWord, audio stays on this PC)",
                   _when(wake_engine, UNTESTED, NEEDS_CONFIG),
                   "Engine verified with synthesized speech and this PC's microphone; your own voice not yet tested."
                   if wake_engine else "Install requirements-optional.txt."),
        Capability("browser_automation", "Browser automation (Playwright)", _when(playwright, UNTESTED, NEEDS_CONFIG),
                   "" if playwright else "Install requirements-optional.txt."),
        Capability("screen_analysis", "Analyzing a screenshot you approve", _when(llm, UNTESTED, NEEDS_CONFIG)),
        Capability("reminders", "Reminders saved across restarts, shown and spoken by JARVIS", VERIFIED,
                   "Delivered while the JARVIS window is open; missed ones show on next start."),
        Capability("spotify", "Spotify control", NEEDS_CONFIG, "Needs Spotify app credentials."),
        Capability("clipboard", "Clipboard read/write on request (secrets withheld)", VERIFIED),
        Capability("calendar_email", "Calendar and email", NOT_IMPLEMENTED),
        Capability("coding_agent", "Editing and testing code projects", NOT_IMPLEMENTED),
        Capability("duplicates", "Duplicate-file and large-file finder (read-only)", VERIFIED),
        Capability("monitors", "Multi-monitor window layouts", NOT_IMPLEMENTED),
    ]


def capability_snapshot() -> list[dict]:
    items = []
    for cap in _entries():
        data = asdict(cap)
        data["state_label"] = STATE_LABELS[cap.state]
        items.append(data)
    return items


def capability_prompt_summary() -> str:
    """Compact, model-facing summary grouped by state."""
    groups: dict[str, list[str]] = {state: [] for state in STATE_LABELS}
    for cap in _entries():
        groups[cap.state].append(cap.name + (f" ({cap.note})" if cap.note and cap.state != VERIFIED else ""))
    lines = ["CAPABILITIES (live registry; describe only these, never claim anything else):"]
    for state, names in groups.items():
        if names:
            lines.append(f"- {STATE_LABELS[state]}: " + "; ".join(names))
    return "\n".join(lines)
