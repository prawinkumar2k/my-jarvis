"""Risk-tiered approvals: ask rarely, ask clearly, never ask twice for the same thing.

Every tool call is classified into one of three tiers:

  AUTO      runs without asking (reads inside allowed folders, locking the PC ...)
  TASK      needs ONE approval; that approval then covers the rest of the same
            task or scope (a task plan, a browser session, one package install),
            for a limited time
  EXPLICIT  needs its own confirmation every time (shutdown, killing processes,
            wiping memory, submitting forms, risky hotkeys ...). A grant never
            covers these.

This module only decides; it creates no approval by itself. Grants are created
by the caller only after a real user event (control-panel click or a reply the
approval-language parser accepted), never from model output, and never survive
a restart or the emergency STOP. Unknown tools that need confirmation default
to EXPLICIT.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

from core.security.tool_policy import get_tool_policy


class Tier(IntEnum):
    AUTO = 1
    TASK = 2
    EXPLICIT = 3


@dataclass(frozen=True)
class Classification:
    tier: Tier
    category: str
    key: str = "*"
    ttl: int = 0  # seconds a TASK grant lasts
    reason: str = ""


@dataclass(frozen=True)
class Resolution:
    tier: Tier
    category: str
    effective_confirmed: bool
    grant_used: bool = False
    grant_created: bool = False
    reason: str = ""


# Categories the user can force back to "ask every time" in the automation settings.
USER_CATEGORIES = ("install", "file_changes", "delete", "browser", "desktop_control", "clipboard", "plans")
DEFAULT_PREFS: dict[str, Any] = {"auto_low_risk": True, "ask_once_per_task": True, "always_confirm": [],
                                 "voice_autostart": True}  # listen as soon as JARVIS opens (needs the mic already allowed)

_SUBMIT_WORDS = re.compile(
    r"\b(submit|pay|payment|purchase|buy|order|checkout|check out|confirm|send|post|publish|delete|remove|"
    r"sign ?in|log ?in|login|password|enviar|comprar|pagar|publicar|eliminar|borrar)\b",
    re.IGNORECASE,
)
_RISKY_HOTKEYS = {"alt+f4", "ctrl+alt+delete", "ctrl+alt+del", "ctrl+shift+delete", "win+r", "alt+shift+f4"}
_LOCK_ACTIONS = {"bloquear", "lock", "cancelar", "cancel"}


# ── preferences ──────────────────────────────────────────────────────────────
_prefs_lock = threading.RLock()


def _prefs_path() -> Path:
    from core.runtime_paths import resolve_runtime_paths

    return resolve_runtime_paths().memory / "automation_prefs.json"


def load_prefs() -> dict[str, Any]:
    try:
        raw = json.loads(_prefs_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    return validate_prefs(raw if isinstance(raw, dict) else {})


def validate_prefs(raw: dict[str, Any]) -> dict[str, Any]:
    prefs = dict(DEFAULT_PREFS)
    for flag in ("auto_low_risk", "ask_once_per_task", "voice_autostart"):
        if isinstance(raw.get(flag), bool):
            prefs[flag] = raw[flag]
    forced = raw.get("always_confirm")
    prefs["always_confirm"] = sorted({c for c in forced if c in USER_CATEGORIES}) if isinstance(forced, list) else []
    return prefs


def save_prefs(raw: dict[str, Any]) -> dict[str, Any]:
    prefs = validate_prefs(raw)
    with _prefs_lock:
        path = _prefs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(prefs, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    grants.revoke_all()  # new rules apply from a clean slate
    return prefs


# ── grants ───────────────────────────────────────────────────────────────────
class _Grants:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = threading.RLock()

    def add(self, category: str, key: str, ttl: int, source: str = "user") -> None:
        if ttl <= 0:
            return
        with self._lock:
            self._items[(category, key)] = {"category": category, "key": key, "source": source,
                                            "granted": time.time(), "expires": time.time() + ttl}

    def covers(self, category: str, key: str) -> bool:
        now = time.time()
        with self._lock:
            for probe in ((category, key), (category, "*")):
                item = self._items.get(probe)
                if item and item["expires"] > now:
                    return True
                if item:
                    self._items.pop(probe, None)
        return False

    def revoke_all(self) -> int:
        with self._lock:
            count = len(self._items)
            self._items.clear()
        return count

    def snapshot(self) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            return [{"category": i["category"], "key": i["key"], "seconds_left": int(i["expires"] - now)}
                    for i in self._items.values() if i["expires"] > now]


grants = _Grants()


# ── classification ───────────────────────────────────────────────────────────
def _local_only() -> bool:
    return str(os.getenv("JARVIS_AI_MODE") or "").strip().lower() == "local_only"


def _rule(tool: str, args: dict) -> Classification | None:
    """Tier rules for tools whose confirmation depends on what they do."""
    args = args or {}
    text = " ".join(str(v) for v in args.values())[:300]
    if tool == "leer_archivo":
        return Classification(Tier.AUTO, "read_file", reason="reads a file inside the allowed folders")
    if tool == "leer_portapapeles":
        if _local_only():
            return Classification(Tier.AUTO, "clipboard", reason="clipboard text stays on this PC (local-only mode)")
        return Classification(Tier.TASK, "clipboard", "*", 1800, "clipboard text may be sent to the cloud AI to answer you")
    if tool == "controlar_pc":
        if str(args.get("accion", "")).strip().lower() in _LOCK_ACTIONS:
            return Classification(Tier.AUTO, "lock", reason="locking is reversible")
        return Classification(Tier.EXPLICIT, "power", reason="shutdown, restart or sleep interrupts everything running")
    if tool in {"matar_proceso", "ejecutar_comando_terminal", "borrar_memoria", "ejecutar_accion_proactiva"}:
        return Classification(Tier.EXPLICIT, "process_control" if tool == "matar_proceso" else tool, reason="hard to undo")
    if tool == "instalar_programa":
        return Classification(Tier.TASK, "install", str(args.get("id_paquete", "")).strip().lower(), 600,
                              "installs software for this Windows user")
    if tool in {"mover_archivo", "renombrar_archivo", "organizar_carpeta", "crear_archivo_texto"}:
        return Classification(Tier.TASK, "file_changes", "*", 600, "changes files inside the allowed folders")
    if tool == "eliminar_archivo":
        if sys.platform == "win32":  # goes to the Recycle Bin, so it can be undone
            return Classification(Tier.TASK, "delete", str(args.get("ruta", "")).strip().lower(), 300,
                                  "moves one item to the Recycle Bin")
        return Classification(Tier.EXPLICIT, "delete", reason="permanent deletion")
    if tool == "click_en_navegador":
        if _SUBMIT_WORDS.search(text):
            return Classification(Tier.EXPLICIT, "browser_submit", reason="this click may submit, buy, send or sign in")
        return Classification(Tier.TASK, "browser", "*", 900, "clicks on the page in the automation browser")
    if tool == "escribir_en_navegador":
        if args.get("enter") or _SUBMIT_WORDS.search(str(args.get("selector", ""))):
            return Classification(Tier.EXPLICIT, "browser_submit", reason="typing here may submit a form or a password")
        return Classification(Tier.TASK, "browser", "*", 900, "types into the automation browser")
    if tool == "computer_hotkey":
        keys = re.sub(r"\s+", "", str(args.get("keys", "")).lower())
        if keys in _RISKY_HOTKEYS:
            return Classification(Tier.EXPLICIT, "desktop_hotkey", reason="this shortcut can close apps or run commands")
        return Classification(Tier.TASK, "desktop_control", "*", 600, "presses keys on your desktop")
    if tool in {"computer_click", "computer_type", "computer_drag_and_drop"}:
        return Classification(Tier.TASK, "desktop_control", "*", 600, "controls the mouse and keyboard")
    if tool in {"ejecutar_plan_acciones", "ejecutar_procedimiento"}:
        key = str(args.get("plan_id") or args.get("nombre") or "*").strip().lower()
        return Classification(Tier.TASK, "plans", key, 1800, "runs a plan you reviewed")
    return None


def classify(tool_name: str, args: dict | None = None, *, prefs: dict[str, Any] | None = None,
             overrides: dict[str, Any] | None = None) -> Classification:
    name = str(tool_name or "").strip()
    policy = get_tool_policy(name, overrides=overrides)
    prefs = prefs if prefs is not None else load_prefs()
    if overrides and name in overrides:  # an explicit user override always wins
        tier = Tier.EXPLICIT if policy.requires_confirmation else Tier.AUTO
        return Classification(tier, "user_override", reason="set in your tool policy")
    if not policy.requires_confirmation:
        return Classification(Tier.AUTO, "none")
    found = _rule(name, dict(args or {})) or Classification(Tier.EXPLICIT, name, reason="needs your confirmation")
    if found.tier is Tier.AUTO and not prefs["auto_low_risk"]:
        found = Classification(Tier.TASK, found.category, "*", 300, found.reason)
    if found.tier is Tier.TASK and (found.category in prefs["always_confirm"] or not prefs["ask_once_per_task"]):
        found = Classification(Tier.EXPLICIT, found.category, found.key, 0, found.reason)
    return found


def resolve(tool_name: str, args: dict | None = None, *, confirmed: bool, remember: bool = False,
            prefs: dict[str, Any] | None = None, overrides: dict[str, Any] | None = None) -> Resolution:
    """Decide whether this call may run now.

    `confirmed` is True only for transport-level approvals (control panel, an accepted
    "yes" reply, an approved task step). `remember` additionally lets a TASK-tier approval
    cover later calls in the same scope; it is set only for a fresh user "yes".
    """
    c = classify(tool_name, args, prefs=prefs, overrides=overrides)
    if c.tier is Tier.AUTO:
        return Resolution(c.tier, c.category, True, reason=c.reason)
    if c.tier is Tier.EXPLICIT:
        return Resolution(c.tier, c.category, confirmed, reason=c.reason)
    if confirmed:
        created = False
        if remember and c.ttl > 0:
            grants.add(c.category, c.key, c.ttl, source="user_approval")
            created = True
        return Resolution(c.tier, c.category, True, grant_created=created, reason=c.reason)
    if grants.covers(c.category, c.key):
        return Resolution(c.tier, c.category, True, grant_used=True, reason=c.reason)
    return Resolution(c.tier, c.category, False, reason=c.reason)


def scope_note(tool_name: str, args: dict | None = None) -> str:
    """One sentence for the confirmation question: what a "yes" will cover."""
    c = classify(tool_name, args)
    if c.tier is Tier.TASK:
        minutes = max(1, c.ttl // 60)
        return f"One yes covers the rest of this task ({c.reason}); it lasts about {minutes} min."
    if c.tier is Tier.EXPLICIT:
        return f"This needs a yes every time ({c.reason})."
    return ""


def _revoke_on_stop() -> None:
    grants.revoke_all()


def _register_stop_hook() -> None:
    try:
        from core.security import emergency_stop

        emergency_stop.register_cancel_hook("approval_grants", _revoke_on_stop)
    except Exception:  # never break import over the hook
        pass


_register_stop_hook()
