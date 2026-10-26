"""Microphone discovery and the user's saved choice for the local listener.

Windows lists one physical microphone under several audio APIs. JARVIS opens
devices through MME (PortAudio's default on Windows, which resamples to the
16 kHz the wake-word model needs) and shows the fuller name another API
reports, because MME cuts names at 31 characters.

The choice is saved by name, not index: indexes shift when devices are
plugged in or out. A saved microphone that is no longer present falls back to
the Windows default and says so.
"""

from __future__ import annotations

import json
import os

from core.runtime_logger import log_warning

_HIDDEN = ("sound mapper", "primary sound capture")


def _sd():
    import sounddevice

    return sounddevice


def _clean(name: str) -> str:
    return " ".join(str(name or "").replace("�", "").split())


def list_input_devices(sd=None) -> list[dict]:
    """Input devices the listener can open: [{"name", "label", "default"}]."""
    sd = sd or _sd()
    devices = list(sd.query_devices())
    apis = list(sd.query_hostapis())
    default_in = sd.default.device[0] if sd.default.device else -1
    if default_in is None or default_in < 0:
        default_in = -1
    # Prefer MME on Windows; elsewhere use the host API of the default input.
    api_index = next((i for i, a in enumerate(apis) if a.get("name") == "MME"), None)
    if api_index is None and 0 <= default_in < len(devices):
        api_index = devices[default_in]["hostapi"]
    full_names = [_clean(d["name"]) for d in devices if d.get("max_input_channels", 0) > 0]
    result, seen = [], set()
    for idx, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) <= 0 or (api_index is not None and dev["hostapi"] != api_index):
            continue
        name = _clean(dev["name"])
        if not name or any(hidden in name.lower() for hidden in _HIDDEN) or name in seen:
            continue
        seen.add(name)
        label = max((f for f in full_names if f.startswith(name)), key=len, default=name)
        result.append({"name": name, "label": label, "default": idx == default_in})
    if result and not any(d["default"] for d in result):
        result[0]["default"] = True  # the mapper was the default; its first device is what Windows uses
    return result


def _find_index(sd, name: str) -> int | None:
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0 and _clean(dev["name"]) == name:
            api = sd.query_hostapis(dev["hostapi"]).get("name")
            if api in {"MME", None} or os.name != "nt":
                return idx
    return None


# ── saved choice ──────────────────────────────────────────────
def _pref_path():
    from core.runtime_paths import resolve_runtime_paths

    return resolve_runtime_paths().memory / "microphone.json"


def selected_name() -> str | None:
    try:
        value = json.loads(_pref_path().read_text(encoding="utf-8")).get("name")
    except (OSError, ValueError):
        return None
    return str(value) if value else None


def select(name: str | None, sd=None) -> tuple[bool, str]:
    """Save the chosen microphone (None = Windows default). Only listed devices are accepted."""
    name = _clean(name) if name else None
    if name and name not in {d["name"] for d in list_input_devices(sd)}:
        return False, "That microphone is not connected."
    try:
        path = _pref_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"name": name}), encoding="utf-8")
    except OSError as exc:
        log_warning("microphone_pref_save_failed", error=type(exc).__name__)
        return False, "Could not save the microphone choice."
    return True, name or "Windows default"


def resolve_device(sd=None) -> tuple[int | None, str, str]:
    """(device index or None for default, display name, note for the user)."""
    sd = sd or _sd()
    name = selected_name()
    if name:
        index = _find_index(sd, name)
        if index is not None:
            return index, name, ""
        note = f"Selected microphone '{name}' is not connected; using the Windows default."
    else:
        note = ""
    try:
        default_name = next((d["label"] for d in list_input_devices(sd) if d["default"]), "")
    except Exception:
        default_name = ""
    return None, default_name or "Windows default", note
