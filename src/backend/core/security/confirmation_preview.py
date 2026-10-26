"""Plain-language details added to a confirmation question.

A generic "this needs confirmation" is not enough for consequential actions:
the user must see exactly what will happen before saying yes. Each preview
is read-only and must never perform the action itself.
"""

from __future__ import annotations

from collections.abc import Callable


def _winget_install(args: dict) -> str:
    from tools.winget import describe_for_confirmation

    return describe_for_confirmation(args)


def _clipboard_read(_args: dict) -> str:
    import os

    mode = str(os.getenv("JARVIS_AI_MODE") or "cloud_first").strip().lower()
    where = "stays on this PC (local AI only)" if mode == "local_only" else "may be sent to the cloud AI (Gemini or Groq) to answer you"
    return f"Read your clipboard text? It {where}. Things that look like passwords or keys are withheld."


def _browser_click(args: dict) -> str:
    return f"Click '{str(args.get('selector', ''))[:80]}' on the current web page? This may submit, buy or send."


def _browser_type(args: dict) -> str:
    text = str(args.get("texto", ""))
    submit = " and press Enter (this usually submits the form)" if args.get("enter") else ""
    return f"Type {len(text)} characters into '{str(args.get('selector', ''))[:80]}'{submit}?"


PREVIEWS: dict[str, Callable[[dict], str]] = {
    "click_en_navegador": _browser_click,
    "escribir_en_navegador": _browser_type,
    "instalar_programa": _winget_install,
    "leer_portapapeles": _clipboard_read,
}


def preview(tool_name: str, args: dict) -> str:
    builder = PREVIEWS.get(str(tool_name or ""))
    if builder is None:
        return ""
    try:
        return str(builder(dict(args or {})) or "").strip()
    except Exception as exc:
        return f"Details could not be checked ({type(exc).__name__})."
