"""Memory management for the UI: list, search, add, edit, forget, export, clear, private mode.

A thin layer over the existing memory tools (`tools/memory.py`), so the same rules apply as when the
user talks to JARVIS: private mode blocks writes, secrets (passwords, keys, card numbers, one-time codes)
are refused, and forgetting also removes the copy in the cognitive memory graph. Nothing here talks to
the cloud.
"""

from __future__ import annotations

from datetime import datetime

DEFAULT_PROFILE = "web_default"


def _pid(profile_id: str | None) -> str:
    from tools._common import _normalizar_profile_id

    return _normalizar_profile_id(profile_id or DEFAULT_PROFILE)


def list_facts(profile_id: str | None = None, query: str = "") -> list[dict]:
    from tools.memory import _fact_lines

    needle = str(query or "").strip().lower()
    return [
        {"n": number, "text": text}
        for number, text in enumerate(_fact_lines(_pid(profile_id)), 1)
        if not needle or needle in text.lower()
    ]


def _run(tool, profile_id: str | None, **args) -> str:
    from core import jarvis_state

    with jarvis_state.active_profile(_pid(profile_id)):
        return str(tool.invoke(args))


def add_fact(profile_id: str | None, text: str) -> tuple[bool, str]:
    from tools.memory import guardar_dato_memoria

    before = len(list_facts(profile_id))
    message = _run(guardar_dato_memoria, profile_id, dato=text)
    return len(list_facts(profile_id)) > before or "already" in message.lower(), message


def edit_fact(profile_id: str | None, number: int, text: str) -> tuple[bool, str]:
    from tools.memory import editar_memoria

    message = _run(editar_memoria, profile_id, numero_o_texto=str(number), nuevo_texto=text)
    return message.startswith("Memory updated"), message


def forget_fact(profile_id: str | None, number: int) -> tuple[bool, str]:
    from tools.memory import olvidar_memoria

    message = _run(olvidar_memoria, profile_id, numero_o_texto=str(number))
    return message.startswith("Forgotten"), message


def clear_all(profile_id: str | None) -> int:
    """Forget every saved memory (and its graph copy). Returns how many were removed."""
    removed = 0
    while list_facts(profile_id):
        ok, _ = forget_fact(profile_id, 1)
        if not ok:
            break
        removed += 1
    return removed


def export_facts(profile_id: str | None = None) -> dict:
    from core.privacy import is_private_mode

    facts = list_facts(profile_id)
    return {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "profile": _pid(profile_id),
        "private_mode": is_private_mode(),
        "count": len(facts),
        "memories": [fact["text"] for fact in facts],
        "note": "Passwords, keys, card numbers and one-time codes are never stored as memory.",
    }
