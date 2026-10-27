"""One-screen health check: what works, what is missing, and the exact next step.

Read-only. Nothing is downloaded, installed, opened or sent anywhere, and no key or secret is ever
included in the result (only "configured / not configured"). Each check is a dict:
    {"id", "label", "status": ok | warn | missing, "detail", "fix"}
A check that raises is reported as "warn / could not check", never as ok.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

OK, WARN, MISSING = "ok", "warn", "missing"


def _item(check_id: str, label: str, status: str, detail: str, fix: str = "") -> dict:
    return {"id": check_id, "label": label, "status": status, "detail": detail, "fix": fix}


def _ai() -> dict:
    from core.llm_providers import resolve_llm_provider_config

    config = resolve_llm_provider_config()
    if not config.configured:
        return _item("ai", "AI provider", MISSING, "No AI is configured.",
                     "Open the setup panel and paste a Gemini or Groq key, or install Ollama for a local model.")
    names = [p for p in (config.primary_provider, config.fallback_provider, *(e[0] for e in config.extra_fallbacks)) if p]
    return _item("ai", "AI provider", OK, f"{config.mode.replace('_', ' ')}: {' -> '.join(names)}")


def _ollama() -> dict:
    base = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
    wanted = (os.getenv("OLLAMA_MODEL") or "").strip()
    if not base.startswith(("http://127.0.0.1", "http://localhost")):
        return _item("ollama", "Local AI (Ollama)", WARN, "Ollama is set to a non-local address, so it was not checked.")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=2) as response:  # noqa: S310 - loopback only
            models = [m.get("name", "") for m in json.loads(response.read().decode()).get("models", [])]
    except Exception:
        return _item("ollama", "Local AI (Ollama)", WARN if wanted else MISSING, "Ollama is not running.",
                     "Start Ollama (it runs in the system tray) or install it from ollama.com for offline answers.")
    if wanted and wanted not in models:
        return _item("ollama", "Local AI (Ollama)", WARN, f"Running, but '{wanted}' is not installed.", f"ollama pull {wanted}")
    return _item("ollama", "Local AI (Ollama)", OK, f"Running with {len(models)} model(s): {', '.join(models[:4]) or 'none'}")


def _microphone() -> dict:
    try:
        from voice.microphones import list_input_devices, resolve_device

        devices = list_input_devices()
        if not devices:
            return _item("microphone", "Microphone", MISSING, "No microphone found.", "Connect a microphone and allow it in Windows privacy settings.")
        _index, name, note = resolve_device()
        return _item("microphone", "Microphone", WARN if note else OK, note or f"{len(devices)} found; using {name}")
    except Exception as exc:
        return _item("microphone", "Microphone", WARN, f"Could not check ({type(exc).__name__}).")


def _speech_model() -> dict:
    name = (os.getenv("JARVIS_WHISPER_MODEL") or "medium").strip()
    root = Path(os.getenv("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub"
    found = list(root.glob(f"models--*faster-whisper-{name}*/snapshots/*/model.bin")) if root.is_dir() else []
    if found:
        return _item("speech", "Offline speech recognition", OK, f"faster-whisper '{name}' is installed (runs on this PC).")
    return _item("speech", "Offline speech recognition", WARN, f"The '{name}' speech model is not downloaded.",
                 "Browser/Gemini speech still works; the offline model downloads on request.")


def _voice() -> dict:
    path = (os.getenv("JARVIS_TTS_MODEL_EN") or "").strip()
    if path and Path(path).is_file():
        return _item("voice", "Spoken replies (offline voice)", OK, f"{Path(path).name} found.")
    return _item("voice", "Spoken replies (offline voice)", WARN, "The configured offline voice file was not found.",
                 "Gemini voice or the browser voice is used instead.")


def _wake_word() -> dict:
    try:
        from voice.wake_word import MODEL_FILE, model_dir, wake_word_listener

        have = (Path(model_dir()) / MODEL_FILE).is_file()
        if not have:
            return _item("wakeword", "'Hey Jarvis' wake word", WARN, "The wake-word model is not downloaded yet.", "Turn HEY JARVIS on once; it downloads a small model.")
        state = wake_word_listener.status().get("state", "stopped")
        return _item("wakeword", "'Hey Jarvis' wake word", OK if state == "listening" else WARN, f"Model installed; listener {state}.",
                     "" if state == "listening" else "Turn HEY JARVIS: ON in the header.")
    except Exception as exc:
        return _item("wakeword", "'Hey Jarvis' wake word", WARN, f"Could not check ({type(exc).__name__}).")


def _tools() -> list[dict]:
    from core import diagnostics

    status = diagnostics.tool_status()
    web = status.get("browser_automation") or {}
    items = [
        _item("ffmpeg", "FFmpeg (audio conversion)", OK if status.get("ffmpeg") else MISSING,
              "Found." if status.get("ffmpeg") else "Not found.", "" if status.get("ffmpeg") else "winget install Gyan.FFmpeg"),
        _item("winget", "winget (software installs)", OK if status.get("winget") else WARN, status.get("winget") or "Not available.",
              "" if status.get("winget") else "Install 'App Installer' from the Microsoft Store."),
    ]
    if web:
        engine = "Playwright Chromium" if web.get("bundled_chromium") else ", ".join(web.get("installed_browsers") or []) or "none"
        items.append(_item("browser", "Browser automation", OK if web.get("ready") else WARN,
                           f"Ready ({engine})." if web.get("ready") else "No browser can be automated.",
                           "" if web.get("ready") else "Install Microsoft Edge or Chrome."))
    return items


def _mail() -> dict:
    from core import mail

    if mail.configured():
        return _item("mail", "Email (optional)", OK, "An address and app password are set (the password is never shown).")
    return _item("mail", "Email (optional)", WARN, "Not set up, so JARVIS cannot read or send email.",
                 "Add JARVIS_MAIL_ADDRESS and JARVIS_MAIL_APP_PASSWORD to .env (Google Account > Security > App passwords).")


def _startup() -> dict:
    try:
        from core.startup_manager import get_startup_status

        state = get_startup_status()
        if not state.supported:
            return _item("startup", "Start with Windows", WARN, "Not supported on this system.")
        return _item("startup", "Start with Windows", OK if state.enabled else WARN,
                     "JARVIS opens when you sign in." if state.enabled else "Off.",
                     "" if state.enabled else "Turn on AUTO-START in the header.")
    except Exception as exc:
        return _item("startup", "Start with Windows", WARN, f"Could not check ({type(exc).__name__}).")


def run_checks() -> dict:
    checks: list[dict] = []
    for build in (_ai, _ollama, _microphone, _speech_model, _voice, _wake_word, _mail, _startup):
        try:
            checks.append(build())
        except Exception as exc:  # a broken check must not look like a pass
            checks.append(_item(build.__name__.strip("_"), build.__name__.strip("_"), WARN, f"Could not check ({type(exc).__name__})."))
    try:
        checks.extend(_tools())
    except Exception as exc:
        checks.append(_item("tools", "Tools", WARN, f"Could not check ({type(exc).__name__})."))
    counts = {state: sum(1 for c in checks if c["status"] == state) for state in (OK, WARN, MISSING)}
    return {"checks": checks, "summary": counts, "ready": counts[MISSING] == 0}
