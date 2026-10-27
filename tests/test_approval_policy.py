"""Risk-tiered approvals: ask rarely, never twice for the same thing, never for the wrong thing.

Unit tests with fake tools and a fake clock; they prove the policy logic, not real Windows actions.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from core.security import approval_policy as ap
from core.security.approval_language import interpret_reply
from core.security.approval_policy import Tier


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
    monkeypatch.setattr(ap, "_prefs_path", lambda: tmp_path / "automation_prefs.json")
    monkeypatch.delenv("JARVIS_AI_MODE", raising=False)
    ap.grants.revoke_all()
    yield
    ap.grants.revoke_all()


# ── language ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "text",
    ["Okay", "yes", "Go ahead", "proceed", "Do it", "Seri", "sari da", "Pannu", "pannunga", "continue", "seri pannu",
     "ok go ahead", "Yes please!", "sí", "de acuerdo", "சரி", "aama"],
)
def test_clear_approvals_are_understood(text):
    assert interpret_reply(text) == "approve"


@pytest.mark.parametrize(
    "text",
    ["no", "cancel", "stop", "vendaam", "illa", "yes but don't", "don't do it", "do not", "wait", "no problem go ahead",
     "வேண்டாம்", "nevermind"],
)
def test_refusals_and_negations_never_approve(text):
    assert interpret_reply(text) == "reject"


@pytest.mark.parametrize(
    "text",
    ["yes and open chrome", "ok delete everything", "is it", "that is", "go", "do", "what will it do?", "", "   ",
     "okay " + "word " * 10, "seri ennoda files ellam delete pannu", "maybe"],
)
def test_anything_else_is_not_permission(text):
    assert interpret_reply(text) == "unclear"


# ── tiers ────────────────────────────────────────────────────────────────────
def tier(tool, **args):
    return ap.classify(tool, args).tier


def test_everyday_actions_do_not_ask():
    assert tier("leer_archivo", nombre_archivo="notes.txt") is Tier.AUTO
    assert tier("controlar_pc", accion="bloquear") is Tier.AUTO
    assert tier("abrir_aplicacion", nombre_app="chrome") is Tier.AUTO  # never needed confirmation


def test_scoped_actions_ask_once():
    assert tier("instalar_programa", id_paquete="VideoLAN.VLC") is Tier.TASK
    assert tier("mover_archivo", origen="a", destino="b") is Tier.TASK
    assert tier("click_en_navegador", selector="#search") is Tier.TASK
    assert tier("escribir_en_navegador", selector="#q", texto="cats") is Tier.TASK
    assert tier("computer_click", target="OK button") is Tier.TASK


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("controlar_pc", {"accion": "apagar"}),
        ("controlar_pc", {"accion": "reiniciar"}),
        ("matar_proceso", {"nombre": "chrome"}),
        ("borrar_memoria", {}),
        ("ejecutar_comando_terminal", {"comando": "dir"}),
        ("click_en_navegador", {"selector": "Place order"}),
        ("click_en_navegador", {"selector": "#checkout"}),
        ("escribir_en_navegador", {"selector": "#q", "texto": "x", "enter": True}),
        ("escribir_en_navegador", {"selector": "input[type=password]", "texto": "x"}),
        ("computer_hotkey", {"keys": "alt+f4"}),
        ("computer_hotkey", {"keys": "Ctrl + Alt + Delete"}),
    ],
)
def test_dangerous_actions_always_ask(tool, args):
    assert ap.classify(tool, args).tier is Tier.EXPLICIT


def test_unknown_confirmation_tool_defaults_to_explicit(monkeypatch):
    from core.security import tool_policy

    monkeypatch.setitem(tool_policy.DEFAULT_TOOL_POLICIES, "brand_new_tool",
                        tool_policy.ToolPolicy("brand_new_tool", "critical", ("admin",), True, True))
    assert tier("brand_new_tool") is Tier.EXPLICIT


def test_clipboard_stays_local_in_local_only_mode_and_asks_once_otherwise(monkeypatch):
    assert tier("leer_portapapeles") is Tier.TASK  # text may reach Gemini/Groq
    monkeypatch.setenv("JARVIS_AI_MODE", "local_only")
    assert tier("leer_portapapeles") is Tier.AUTO


def test_user_override_in_the_policy_always_wins():
    overrides = {"abrir_aplicacion": {"risk_level": "critical", "allowed_profiles": ["admin"], "requires_confirmation": True}}
    assert ap.classify("abrir_aplicacion", {}, overrides=overrides).tier is Tier.EXPLICIT


# ── scoped approvals ─────────────────────────────────────────────────────────
def test_one_approval_covers_the_rest_of_the_same_scope():
    first = ap.resolve("click_en_navegador", {"selector": "#a"}, confirmed=False)
    assert not first.effective_confirmed
    said_yes = ap.resolve("click_en_navegador", {"selector": "#a"}, confirmed=True, remember=True)
    assert said_yes.effective_confirmed and said_yes.grant_created
    later = ap.resolve("escribir_en_navegador", {"selector": "#q", "texto": "hi"}, confirmed=False)
    assert later.effective_confirmed and later.grant_used  # same browser scope: no second question


def test_approval_does_not_leak_to_other_scopes_or_dangerous_actions():
    ap.resolve("instalar_programa", {"id_paquete": "VideoLAN.VLC"}, confirmed=True, remember=True)
    assert ap.resolve("instalar_programa", {"id_paquete": "videolan.vlc"}, confirmed=False).effective_confirmed
    assert not ap.resolve("instalar_programa", {"id_paquete": "Other.App"}, confirmed=False).effective_confirmed
    assert not ap.resolve("mover_archivo", {}, confirmed=False).effective_confirmed  # different category
    ap.resolve("click_en_navegador", {"selector": "#a"}, confirmed=True, remember=True)
    assert not ap.resolve("click_en_navegador", {"selector": "Pay now"}, confirmed=False).effective_confirmed
    assert not ap.resolve("controlar_pc", {"accion": "apagar"}, confirmed=False).effective_confirmed


def test_approval_inside_an_approved_task_step_does_not_create_a_grant():
    ap.resolve("mover_archivo", {}, confirmed=True, remember=False)  # source task_approved
    assert not ap.resolve("mover_archivo", {}, confirmed=False).effective_confirmed


def test_approvals_expire(monkeypatch):
    ap.resolve("mover_archivo", {}, confirmed=True, remember=True)
    assert ap.resolve("mover_archivo", {}, confirmed=False).effective_confirmed
    real = time.time()
    monkeypatch.setattr(ap.time, "time", lambda: real + 3600)
    assert not ap.resolve("mover_archivo", {}, confirmed=False).effective_confirmed


def test_explicit_actions_are_never_covered_by_a_grant():
    ap.resolve("controlar_pc", {"accion": "apagar"}, confirmed=True, remember=True)
    assert ap.grants.snapshot() == []
    assert not ap.resolve("controlar_pc", {"accion": "apagar"}, confirmed=False).effective_confirmed


def test_emergency_stop_forgets_every_approval():
    from core.security import emergency_stop

    ap.resolve("mover_archivo", {}, confirmed=True, remember=True)
    try:
        emergency_stop.engage("test")
        assert ap.grants.snapshot() == []
    finally:
        emergency_stop.release()


# ── preferences ──────────────────────────────────────────────────────────────
def test_preferences_are_validated_and_persisted():
    saved = ap.save_prefs({"auto_low_risk": False, "always_confirm": ["install", "hack", "browser"], "junk": 1})
    assert saved == {"auto_low_risk": False, "ask_once_per_task": True, "always_confirm": ["browser", "install"],
                     "voice_autostart": True}
    assert ap.load_prefs() == saved
    assert ap.validate_prefs({"auto_low_risk": "yes"})["auto_low_risk"] is True  # wrong type is ignored


def test_forced_categories_and_ask_every_time_mode():
    ap.save_prefs({"always_confirm": ["install"]})
    assert tier("instalar_programa", id_paquete="x") is Tier.EXPLICIT
    assert tier("mover_archivo") is Tier.TASK
    ap.save_prefs({"ask_once_per_task": False})
    assert tier("mover_archivo") is Tier.EXPLICIT


def test_turning_off_auto_low_risk_makes_reads_ask_once():
    ap.save_prefs({"auto_low_risk": False})
    assert tier("leer_archivo", nombre_archivo="a.txt") is Tier.TASK


def test_saving_preferences_clears_remembered_approvals():
    ap.resolve("mover_archivo", {}, confirmed=True, remember=True)
    ap.save_prefs({"ask_once_per_task": True})
    assert ap.grants.snapshot() == []


# ── the real guard ───────────────────────────────────────────────────────────
@pytest.fixture
def guard(monkeypatch):
    from services import security_manager

    monkeypatch.setattr(security_manager, "_obs_event", MagicMock())
    monkeypatch.setattr(security_manager, "_obs_inc", MagicMock())
    monkeypatch.setattr(security_manager, "verificar_autorizacion", lambda pid: True)

    def call(tool, args, source):
        with patch.object(security_manager, "SECURITY_POLICY", {"blocked_tools": [], "strict_mode": False}):
            return security_manager._security_guard(tool, args, "x", source, profile_id="admin")

    return call


def test_guard_reads_run_and_one_yes_unlocks_the_browser_session_but_not_a_purchase(guard):
    assert guard("leer_archivo", {"nombre_archivo": "a.txt"}, "llm_loop") == (True, "")
    assert guard("click_en_navegador", {"selector": "#search"}, "llm_loop")[0] is False
    assert guard("click_en_navegador", {"selector": "#search"}, "auth_resume")[0] is True  # the user said yes
    assert guard("click_en_navegador", {"selector": "#next"}, "llm_loop")[0] is True  # no second question
    assert guard("escribir_en_navegador", {"selector": "#q", "texto": "cats"}, "llm_loop")[0] is True
    assert guard("click_en_navegador", {"selector": "Pay now"}, "llm_loop")[0] is False  # still asks
    assert guard("controlar_pc", {"accion": "apagar"}, "llm_loop")[0] is False


def test_guard_ignores_model_claims_of_confirmation(guard):
    assert guard("mover_archivo", {"_confirmed": True, "confirmed": True, "el_usuario_ya_confirmo": True}, "llm_loop")[0] is False


# ── chat replies ─────────────────────────────────────────────────────────────
@pytest.fixture
def chat(monkeypatch):
    from core.brain import history_manager, processor, tool_manager

    calls = []
    monkeypatch.setattr(tool_manager, "_invocar_tool_entry", lambda *a, **k: calls.append(a) or "done")
    history_manager._PENDING_AUTH_ACTIONS.clear()

    def ask(tool="mover_archivo", args=None):
        history_manager._registrar_accion_pendiente_auth("admin", tool, args or {"origen": "a"}, "move a")

    return processor, history_manager, calls, ask


def test_a_clean_yes_runs_only_the_pending_action(chat):
    processor, _history, calls, ask = chat
    ask()
    reply, _ = processor._resolve_pending_auth_confirmation("seri", "admin")
    assert reply == "done" and [c[0] for c in calls] == ["mover_archivo"] and calls[0][3] == "auth_resume"


@pytest.mark.parametrize("text", ["yes but don't", "no", "vendaam"])
def test_refusals_cancel_the_pending_action(chat, text):
    processor, history, calls, ask = chat
    ask()
    reply, _ = processor._resolve_pending_auth_confirmation(text, "admin")
    assert reply == "Action cancelled." and calls == []
    assert history._extraer_accion_pendiente_auth("admin") is None


def test_an_unrelated_message_drops_the_question_so_a_later_okay_is_not_blanket_permission(chat):
    processor, history, calls, ask = chat
    ask()
    assert processor._resolve_pending_auth_confirmation("what is the weather", "admin") == (None, False)
    assert history._extraer_accion_pendiente_auth("admin") is None
    assert processor._resolve_pending_auth_confirmation("okay", "admin") == (None, False)
    assert calls == []


def test_an_old_question_expires(chat, monkeypatch):
    processor, history, calls, ask = chat
    ask()
    real = time.time()
    monkeypatch.setattr(history._time, "time", lambda: real + 301)
    assert processor._resolve_pending_auth_confirmation("yes", "admin") == (None, False)
    assert calls == []
