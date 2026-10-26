"""Deterministic English / Thanglish intents that run without any AI call.

Each matcher returns ``(tool_name, arguments)`` or ``None``. Patterns are
deliberately narrow: anything ambiguous falls through to the AI planner.
Arguments are validated by the tools themselves before execution.
"""

from __future__ import annotations

import re

# App names JARVIS can open directly (abrir_aplicacion resolves the rest).
APP_ALIASES = {
    "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "microsoft edge": "msedge",
    "firefox": "firefox", "vs code": "code", "vscode": "code", "visual studio code": "code",
    "notepad": "notepad", "calculator": "calc", "calc": "calc", "paint": "mspaint",
    "explorer": "explorer", "file explorer": "explorer", "files": "explorer", "settings": "ms-settings:",
    "task manager": "taskmgr", "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "outlook": "outlook", "whatsapp": "whatsapp", "spotify": "spotify", "terminal": "wt",
    "command prompt": "cmd", "cmd": "cmd", "powershell": "powershell", "teams": "teams",
    "discord": "discord", "zoom": "zoom", "camera": "microsoft.windows.camera:", "photos": "ms-photos:",
}

_PLEASE = r"(?:\s+(?:please|pls|da|bro|ji))?"
_DO = r"(?:pannu|pannunga|pannu\s+da|pannuda|panni\s+vidu|pannidu|podu|edu|eduthu\s+vai)"


def _clean(text: str) -> str:
    text = re.sub(r"^\s*(?:hey\s+)?jarvis[\s,]+", "", text.strip().lower())
    return re.sub(r"[.!?]+$", "", text).strip()


def _app(name: str) -> str | None:
    name = re.sub(r"^(?:the|my)\s+", "", name.strip())
    name = re.sub(r"\s+(?:app|application)$", "", name)
    return APP_ALIASES.get(name)


def match_local_intent(raw: str) -> tuple[str, dict] | None:
    text = _clean(raw)
    if not text or len(text) > 120:
        return None

    # Open an app: "open chrome", "launch vs code", "chrome open pannu"
    m = re.fullmatch(r"(?:open|launch|start)\s+(.+?)" + _PLEASE, text) or re.fullmatch(
        r"(.+?)\s+(?:open|on)\s*" + f"(?:{_DO})?" + _PLEASE, text
    )
    if m and (app := _app(m.group(1))):
        return "abrir_aplicacion", {"nombre_app": app}

    # Media: "pause music", "next song", "song niruthu", "adutha song podu"
    media_words = r"(?:the\s+)?(?:music|song|video|track|paattu|pattu)"
    # A bare "stop" usually means "stop talking", so it needs a media word.
    if re.fullmatch(rf"(?:pause|play|resume)(?:\s+{media_words})?{_PLEASE}|stop\s+{media_words}{_PLEASE}", text) or re.fullmatch(
        rf"{media_words}\s+(?:pause|play|niruthu|nirutthu|podu|stop)(?:\s+{_DO})?{_PLEASE}", text
    ):
        action = "stop" if "stop" in text else "play_pause"
        return "control_multimedia", {"accion": action}
    if re.fullmatch(rf"(?:next|skip)(?:\s+{media_words})?{_PLEASE}|adutha\s+{media_words}(?:\s+{_DO})?{_PLEASE}", text):
        return "control_multimedia", {"accion": "next"}
    if re.fullmatch(rf"(?:previous|prev|last)(?:\s+{media_words})?{_PLEASE}|munnadi\s+{media_words}(?:\s+{_DO})?{_PLEASE}", text):
        return "control_multimedia", {"accion": "previous"}

    # Brightness: "brightness 60", "brightness kammi pannu", "increase brightness"
    m = re.fullmatch(r"(?:set\s+)?brightness\s+(?:to\s+)?(\d{1,3})\s*%?" + f"(?:\\s+{_DO})?" + _PLEASE, text)
    if m:
        return "ajustar_brillo", {"nivel": m.group(1)}
    if re.search(r"\bbrightness\b", text):
        if re.search(r"\b(kammi|kuraivu|kuraichu|down|decrease|lower|reduce|dim)\b", text):
            return "ajustar_brillo", {"nivel": "down"}
        if re.search(r"\b(athigam|adhigam|jaasthi|up|increase|raise|brighter)\b", text):
            return "ajustar_brillo", {"nivel": "up"}

    # Screenshot
    if re.fullmatch(r"(?:take\s+(?:a\s+)?)?screen\s?shot(?:\s+(?:edu|eduthu\s+vai|take|capture|" + _DO + r"))?" + _PLEASE, text):
        return "captura_pantalla", {}

    # Timer: "5 minute timer", "timer for 90 seconds", "10 nimisham timer vai"
    duration = r"(\d+(?:\.\d+)?\s*(?:h|hr|hrs|hour|hours|mani|m|min|mins|minute|minutes|nimisham|s|sec|secs|second|seconds))"
    m = re.fullmatch(rf"(?:set\s+(?:a\s+)?)?{duration}\s+timer(?:\s+(?:vai|vechu|set|{_DO}))?{_PLEASE}", text) or re.fullmatch(
        rf"(?:set\s+(?:a\s+)?)?timer\s+(?:for\s+)?{duration}(?:\s+(?:vai|{_DO}))?{_PLEASE}", text
    )
    if m:
        return "poner_temporizador", {"duracion": m.group(1)}

    # Alarm: "alarm for 7:30", "7:30-ku alarm vai", "wake me up at 6 am"
    clock = r"(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?)"
    m = re.fullmatch(rf"(?:set\s+(?:an?\s+)?)?alarm\s+(?:for|at)\s+{clock}{_PLEASE}", text) or re.fullmatch(
        rf"{clock}\s*(?:-|\s)?(?:ku|kku|ukku)?\s+alarm(?:\s+(?:vai|vechu|set|{_DO}))?{_PLEASE}", text
    ) or re.fullmatch(rf"wake\s+me\s+(?:up\s+)?at\s+{clock}{_PLEASE}", text)
    if m:
        return "poner_alarma", {"hora": m.group(1).strip()}

    # Notes: "note: buy milk", "idha note pannu: call ravi", "read my notes"
    m = re.fullmatch(r"(?:save\s+a\s+note|take\s+a\s+note|note(?:\s+(?:this|down))?|(?:idha|ithai|idhu)\s+note\s+" + _DO + r")\s*[:,-]\s*(.+)", text)
    if m:
        return "guardar_nota", {"texto": m.group(1).strip()}
    if re.fullmatch(r"(?:read|show|list)\s+(?:my\s+)?notes" + _PLEASE + r"|(?:en|enoda|ennoda)\s+notes\s+(?:sollu|kaattu|padi)" + _PLEASE, text):
        return "leer_notas", {}

    # Daily summary and self check
    if re.fullmatch(r"(?:today'?s|daily|inniku|indraya)\s+summary(?:\s+(?:sollu|kudu|please))?" + _PLEASE, text):
        return "resumen_del_dia", {}
    if re.fullmatch(r"(?:are\s+you\s+(?:ok|okay|working|alright)|nee\s+ok(?:-?a|ay)?|self[\s-]?check|system\s+check|health\s+check)" + _PLEASE, text):
        return "estado_jarvis", {}

    # Window layout: "left-la chrome, right-la vs code" / "chrome left vs code right"
    m = re.fullmatch(r"left(?:-la|\s+la|\s+side)?\s+(.+?)\s*,?\s+right(?:-la|\s+la|\s+side)?\s+(.+?)", text) or re.fullmatch(
        r"(.+?)\s+left(?:-la|\s+la)?\s*,?\s+(.+?)\s+right(?:-la|\s+la)?", text
    )
    if m:
        return "organizar_ventanas", {"ventanas": f"{m.group(1).strip()}, {m.group(2).strip()}", "distribucion": "split"}

    return None
