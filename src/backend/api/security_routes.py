"""
Security Routes: security policy, proactive alerts, quick control.
"""

import asyncio

from core.jarvis_observability import obs_snapshot
from quart import Blueprint, jsonify, request

security_bp = Blueprint("security", __name__)
_background_tasks: set = set()  # keep references so tasks are not garbage-collected

# Injected dependencies
_security_snapshot = None
_proactive_snapshot = None
_actualizar_security_policy = None
_ejecutar_accion_control = None
SECURITY_POLICY = None
PROACTIVE_STATE = None
PROACTIVE_LOCK = None
jarvis_brain = None


class SecurityRoutesConfig:
    def __init__(
        self,
        security_snapshot_fn,
        proactive_snapshot_fn,
        actualizar_security_policy_fn,
        ejecutar_accion_control_fn,
        security_policy,
        proactive_state,
        proactive_lock,
        brain,
    ):
        self.security_snapshot_fn = security_snapshot_fn
        self.proactive_snapshot_fn = proactive_snapshot_fn
        self.actualizar_security_policy_fn = actualizar_security_policy_fn
        self.ejecutar_accion_control_fn = ejecutar_accion_control_fn
        self.security_policy = security_policy
        self.proactive_state = proactive_state
        self.proactive_lock = proactive_lock
        self.brain = brain


def init_security_routes(config: SecurityRoutesConfig):
    global _security_snapshot, _proactive_snapshot, _actualizar_security_policy
    global _ejecutar_accion_control, SECURITY_POLICY, PROACTIVE_STATE, PROACTIVE_LOCK, jarvis_brain
    _security_snapshot = config.security_snapshot_fn
    _proactive_snapshot = config.proactive_snapshot_fn
    _actualizar_security_policy = config.actualizar_security_policy_fn
    _ejecutar_accion_control = config.ejecutar_accion_control_fn
    SECURITY_POLICY = config.security_policy
    PROACTIVE_STATE = config.proactive_state
    PROACTIVE_LOCK = config.proactive_lock
    jarvis_brain = config.brain


@security_bp.route("/api/security", methods=["GET"])
async def get_security():
    try:
        limit = int(request.args.get("limit", "60"))
    except Exception as e:
        print(f"[WARN get_security] limit parse error: {e}")
        limit = 60
    limit = max(1, min(limit, 200))
    obs = obs_snapshot()
    from services.security_manager import _security_tail

    return jsonify(
        {
            **_security_snapshot(),
            "metrics": {
                "blocked_total": int(obs.get("security_blocked_total", 0)),
                "warning_total": int(obs.get("security_warning_total", 0)),
            },
            "audit": _security_tail(limit=limit),
        }
    )


@security_bp.route("/api/security/policy", methods=["POST"])
async def update_security_policy():
    data = (await request.get_json(silent=True)) or {}
    return jsonify(
        {
            "message": "Security policy updated.",
            **_actualizar_security_policy(data),
        }
    )


def _emergency_stop_payload(state) -> dict:
    return {
        "engaged": state.engaged,
        "reason": state.reason,
        "engaged_at": state.engaged_at,
        "uninterrupted": list(state.hook_failures),
    }


@security_bp.route("/api/security/emergency-stop", methods=["GET"])
async def get_emergency_stop():
    from core.security import emergency_stop

    return jsonify(_emergency_stop_payload(emergency_stop.state()))


@security_bp.route("/api/security/emergency-stop", methods=["POST"])
async def set_emergency_stop():
    """Engage ({"engaged": true}) or release ({"engaged": false}) the emergency stop."""
    from core.security import emergency_stop
    from services.security_manager import _security_audit

    data = (await request.get_json(silent=True)) or {}
    engaged = data.get("engaged", True)
    if not isinstance(engaged, bool):
        return jsonify({"error": "Field 'engaged' must be a boolean."}), 400
    state = emergency_stop.engage("user") if engaged else emergency_stop.release()
    closed_sessions = 0
    if engaged:
        try:
            from voice.wake_word import wake_word_listener

            await asyncio.to_thread(wake_word_listener.stop)
        except Exception as exc:
            print(f"[WARN emergency_stop] wake word stop failed: {type(exc).__name__}")
        try:
            from voice.live_session import live_session_manager

            closed_sessions = await live_session_manager.close_all()
        except Exception as exc:
            print(f"[WARN emergency_stop] live session close failed: {type(exc).__name__}")
    _security_audit(
        "emergency_stop_engaged" if engaged else "emergency_stop_released",
        level="critical" if engaged else "info",
        tool="emergency_stop",
        reason="Requested from control API",
        source="control_panel",
    )
    return jsonify({**_emergency_stop_payload(state), "closed_live_sessions": closed_sessions})


@security_bp.route("/api/security/capabilities", methods=["GET"])
async def get_capabilities():
    """Truthful feature registry (verified / untested / needs setup / not implemented)."""
    from core.capability_catalog import STATE_LABELS, capability_snapshot

    return jsonify({"states": STATE_LABELS, "capabilities": capability_snapshot()})


@security_bp.route("/api/security/private-mode", methods=["GET", "POST"])
async def private_mode():
    from core.privacy import is_private_mode, set_private_mode

    if request.method == "POST":
        data = (await request.get_json(silent=True)) or {}
        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            return jsonify({"error": "Field 'enabled' must be a boolean."}), 400
        set_private_mode(enabled)
    return jsonify({"private_mode": is_private_mode()})


@security_bp.route("/api/security/startup-briefing", methods=["GET"])
async def startup_briefing():
    """Short spoken status report for app start: time, date, battery, CPU, memory."""
    from core.startup_briefing import build_briefing, collect_status
    from utils.jarvis_i18n import get_current_language

    status = await asyncio.to_thread(collect_status)
    return jsonify({"text": build_briefing(request.args.get("lang") or get_current_language(), status)})


@security_bp.route("/api/security/tasks", methods=["GET"])
async def list_persistent_tasks():
    from core import task_engine

    return jsonify({"tasks": await asyncio.to_thread(task_engine.list_tasks, 20)})


@security_bp.route("/api/security/tasks/<task_id>/<action>", methods=["POST"])
async def task_action(task_id: str, action: str):
    """Control-panel actions. approve/resume start the task in the background and return at once;
    poll GET /api/security/tasks for progress. Only eligible actions are accepted (409 otherwise)."""
    from core import task_engine

    if action not in {"approve", "reject", "resume", "cancel"}:
        return jsonify({"error": "Unknown action."}), 400
    task = await asyncio.to_thread(task_engine.get_task, task_id)
    if task is None:
        return jsonify({"error": "No such task."}), 404
    if action == "cancel":
        if task["state"] in task_engine.TERMINAL_STATES:
            return jsonify({"error": f"Task is already {task['state']}.", "task": task}), 409
        task = await asyncio.to_thread(task_engine.cancel_task, task_id)
        return jsonify({"task": task, "summary": task_engine.summarize(task)})
    if action in {"approve", "reject"} and task["state"] != "approval_required":
        return jsonify({"error": "Nothing is waiting for approval.", "task": task}), 409
    if action == "reject":
        task = await asyncio.to_thread(task_engine.reject_step, task_id)
        return jsonify({"task": task, "summary": task_engine.summarize(task)})
    if action == "resume" and not task_engine.can_resume(task):
        return jsonify({"error": f"Task is {task['state']}{' and already running' if task.get('active') else ''}; it cannot be resumed.", "task": task}), 409
    from core.security import emergency_stop

    if emergency_stop.is_engaged():
        return jsonify({"error": "Emergency stop is active.", "task": task}), 409
    if action == "approve":
        await asyncio.to_thread(task_engine.approve_step, task_id)
    _background_tasks.add(asyncio.create_task(asyncio.to_thread(task_engine.run_task, task_id)))
    await asyncio.sleep(0)
    task = await asyncio.to_thread(task_engine.get_task, task_id)
    return jsonify({"task": task, "summary": task_engine.summarize(task)}), 202


@security_bp.route("/api/security/reminders", methods=["GET"])
async def reminders_status():
    """Pending reminders plus any that are due now (each due reminder is returned once)."""
    from core.reminders import reminder_store

    due = await asyncio.to_thread(reminder_store.take_unshown)
    return jsonify({"pending": reminder_store.pending(), "due": due})


async def _reminder_notification_loop(interval: float = 10.0) -> None:
    """Fire due reminders and show a Windows notification for each (window may be minimized)."""
    from core.notifications import show_toast
    from core.reminders import reminder_store

    while True:
        try:
            for item in await asyncio.to_thread(reminder_store.fire_due):
                prefix = "Missed while JARVIS was closed: " if item.get("missed") else ""
                await asyncio.to_thread(show_toast, "JARVIS reminder", prefix + item["text"])
        except Exception as exc:
            print(f"[WARN reminders] notification loop: {type(exc).__name__}")
        await asyncio.sleep(interval)


@security_bp.before_app_serving
async def _recover_tasks():
    """Tasks that were running when JARVIS stopped become 'interrupted' (never auto-resumed)."""
    try:
        from core import task_engine

        await asyncio.to_thread(task_engine.recover_after_restart)
    except Exception as exc:
        print(f"[WARN tasks] recovery failed: {type(exc).__name__}")


async def _routine_loop(interval: float = 30.0) -> None:
    """Run due routines (daily summary ...) and show each result as a Windows notification."""
    from core import routines
    from core.notifications import show_toast

    while True:
        try:
            for result in await asyncio.to_thread(routines.run_due):
                title = f"JARVIS: {result['name']}" + (" (missed while JARVIS was closed)" if result.get("missed") else "")
                body = result["text"] if result["ok"] else f"Could not run: {result['text']}"
                await asyncio.to_thread(show_toast, title, body[:240])
        except Exception as exc:
            print(f"[WARN routines] loop: {type(exc).__name__}")
        await asyncio.sleep(interval)


@security_bp.route("/api/security/routines", methods=["GET", "POST"])
async def routines_api():
    """List routines and recent results (GET), or create one (POST name, time, repeat, tool, args)."""
    from core import routines

    if request.method == "POST":
        data = await request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Send a JSON object."}), 400
        try:
            routine = await asyncio.to_thread(
                routines.add, data.get("name"), data.get("time"), str(data.get("repeat") or "daily"),
                str(data.get("tool") or ""), data.get("args") if isinstance(data.get("args"), dict) else {})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"routine": routine, **routines.list_all(), "tools": list(routines.SUGGESTED_TOOLS)}), 201
    return jsonify({**await asyncio.to_thread(routines.list_all), "tools": list(routines.SUGGESTED_TOOLS)})


@security_bp.route("/api/security/routines/<routine_id>/<action>", methods=["POST"])
async def routine_action(routine_id: str, action: str):
    """delete a routine, or run it now (a manual run does not use up the next scheduled one)."""
    from core import routines

    if action == "delete":
        removed = await asyncio.to_thread(routines.remove, routine_id)
        if removed is None:
            return jsonify({"error": "No such routine."}), 404
    elif action == "run":
        if not any(r["id"] == routine_id for r in routines.list_all()["routines"]):
            return jsonify({"error": "No such routine."}), 404
        await asyncio.to_thread(routines.run_due, None, force_id=routine_id)
    else:
        return jsonify({"error": "Unknown action."}), 400
    return jsonify({**await asyncio.to_thread(routines.list_all), "tools": list(routines.SUGGESTED_TOOLS)})


@security_bp.before_app_serving
async def _start_reminder_notifications():
    import os

    if os.getenv("JARVIS_TEST_MODE") != "1":
        _background_tasks.add(asyncio.create_task(_reminder_notification_loop()))
        _background_tasks.add(asyncio.create_task(_routine_loop()))


@security_bp.before_app_serving
async def _restore_wake_word():
    """Turn "Hey Jarvis" back on at startup if the user left it on."""
    import os

    if os.getenv("JARVIS_TEST_MODE") == "1":
        return  # never open the real microphone during tests
    try:
        from voice.wake_word import remembered_enabled, wake_word_listener

        if remembered_enabled():
            # Load the models in the background so the server starts serving now.
            _background_tasks.add(asyncio.create_task(asyncio.to_thread(wake_word_listener.start)))
    except Exception as exc:
        print(f"[WARN wake_word] restore failed: {type(exc).__name__}")


@security_bp.route("/api/security/wakeword", methods=["GET", "POST"])
async def wakeword():
    """Offline "Hey Jarvis" listener. GET ?since=<event_id> returns new detections."""

    from voice.wake_word import remember_enabled, wake_word_listener

    if request.method == "POST":
        data = (await request.get_json(silent=True)) or {}
        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            return jsonify({"error": "Field 'enabled' must be a boolean."}), 400
        if enabled:
            from core.security import emergency_stop

            if emergency_stop.is_engaged():
                return jsonify({**wake_word_listener.status(), "error": "Emergency stop is active."}), 409
            ok, message = await asyncio.to_thread(wake_word_listener.start)
            if not ok:
                return jsonify({**wake_word_listener.status(), "error": message}), 503
            remember_enabled(True)
        else:
            await asyncio.to_thread(wake_word_listener.stop)
            remember_enabled(False)
    try:
        since = int(request.args.get("since", "0"))
    except ValueError:
        since = 0
    return jsonify(wake_word_listener.status(since))


def _memory_view(profile_id: str | None, query: str = "") -> dict:
    from core import memory_admin
    from core.privacy import is_private_mode

    facts = memory_admin.list_facts(profile_id, query)
    return {"facts": facts, "count": len(memory_admin.list_facts(profile_id)), "private_mode": is_private_mode()}


@security_bp.route("/api/security/memory", methods=["GET", "POST"])
async def memory_facts():
    """List/search (GET ?q=&profile_id=) or add (POST {"text"}) saved memories. Secrets are refused
    and nothing is saved in private mode (same rules as telling JARVIS directly)."""
    from core import memory_admin

    profile_id = request.args.get("profile_id") or None
    if request.method == "POST":
        data = await request.get_json(silent=True)
        text = str((data or {}).get("text") or "").strip() if isinstance(data, dict) else ""
        if not text or len(text) > 500:
            return jsonify({"error": "Send a memory of 1 to 500 characters."}), 400
        ok, message = await asyncio.to_thread(memory_admin.add_fact, profile_id, text)
        view = await asyncio.to_thread(_memory_view, profile_id)
        return jsonify({**view, "ok": ok, "message": message}), (200 if ok else 409)
    view = await asyncio.to_thread(_memory_view, profile_id, request.args.get("q", ""))
    return jsonify(view)


@security_bp.route("/api/security/memory/<int:number>/<action>", methods=["POST"])
async def memory_fact_action(number: int, action: str):
    """edit ({"text"}) or delete one saved memory by its number."""
    from core import memory_admin

    profile_id = request.args.get("profile_id") or None
    if action == "delete":
        ok, message = await asyncio.to_thread(memory_admin.forget_fact, profile_id, number)
    elif action == "edit":
        data = await request.get_json(silent=True)
        text = str((data or {}).get("text") or "").strip() if isinstance(data, dict) else ""
        if not text or len(text) > 500:
            return jsonify({"error": "Send the new memory text (1 to 500 characters)."}), 400
        ok, message = await asyncio.to_thread(memory_admin.edit_fact, profile_id, number, text)
    else:
        return jsonify({"error": "Unknown action."}), 400
    view = await asyncio.to_thread(_memory_view, profile_id)
    return jsonify({**view, "ok": ok, "message": message}), (200 if ok else 409)


@security_bp.route("/api/security/memory/export", methods=["GET"])
async def memory_export():
    """Download everything JARVIS remembers as a JSON file."""
    import json

    from core import memory_admin

    payload = await asyncio.to_thread(memory_admin.export_facts, request.args.get("profile_id") or None)
    return (
        json.dumps(payload, ensure_ascii=False, indent=2),
        200,
        {"Content-Type": "application/json; charset=utf-8",
         "Content-Disposition": 'attachment; filename="jarvis-memory.json"', "Cache-Control": "no-store"},
    )


@security_bp.route("/api/security/memory/private", methods=["POST"])
async def memory_private_mode():
    """Private mode: while on, nothing new is saved to long-term memory (kept across restarts)."""
    from core.privacy import set_private_mode

    data = await request.get_json(silent=True)
    enabled = (data or {}).get("enabled") if isinstance(data, dict) else None
    if not isinstance(enabled, bool):
        return jsonify({"error": "Field 'enabled' must be true or false."}), 400
    return jsonify({"private_mode": set_private_mode(enabled)})


@security_bp.route("/api/security/memory/clear", methods=["POST"])
async def memory_clear():
    """Forget every saved memory. Needs {"confirm": "DELETE ALL"} so it cannot happen by accident."""
    from core import memory_admin

    data = await request.get_json(silent=True)
    if not isinstance(data, dict) or data.get("confirm") != "DELETE ALL":
        return jsonify({"error": "Send {\"confirm\": \"DELETE ALL\"} to forget every memory."}), 400
    removed = await asyncio.to_thread(memory_admin.clear_all, request.args.get("profile_id") or None)
    return jsonify({"removed": removed, **await asyncio.to_thread(_memory_view, request.args.get("profile_id") or None)})


@security_bp.route("/api/security/setup-check", methods=["GET"])
async def setup_check():
    """Read-only health check: AI, local model, microphone, speech, voice, FFmpeg, browser, startup."""
    from core import setup_check as checks

    return jsonify(await asyncio.to_thread(checks.run_checks))


@security_bp.route("/api/security/ai-route", methods=["GET"])
async def ai_route():
    """Which AI JARVIS will use, in what order, and which one answered last. No keys, no prompts."""
    import os

    from core.brain import brain_state
    from core.llm_providers import gemini_backup_model, resolve_llm_provider_config

    config = resolve_llm_provider_config()
    chain = []
    if config.primary_provider:
        chain.append({"role": "primary", "provider": config.primary_provider, "model": config.primary_model})
        backup = gemini_backup_model(config)
        if backup:
            chain.append({"role": "backup", "provider": "gemini", "model": backup})
    if config.fallback_provider:
        chain.append({"role": "fallback", "provider": config.fallback_provider, "model": config.fallback_model})
    for provider, model, _key in config.extra_fallbacks:
        chain.append({"role": "fallback", "provider": provider, "model": model})
    return jsonify({
        "mode": config.mode,
        "local_only": config.mode == "local_only",
        "configured": config.configured,
        "ready": brain_state.llm is not None,
        "chain": chain,
        "last_answer": dict(brain_state.last_answer or {}),
        "speech_to_text": {
            "where": "local (this PC)",
            "model": os.getenv("JARVIS_WHISPER_MODEL") or "default",
        },
    })


@security_bp.route("/api/security/automation", methods=["GET", "POST"])
async def automation_preferences():
    """How much JARVIS may do without asking. GET shows preferences and the approvals currently
    active; POST {"auto_low_risk", "ask_once_per_task", "always_confirm": [...]} saves them (all
    active approvals are cleared so the new rules start clean)."""
    from core.security import approval_policy

    if request.method == "POST":
        data = await request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Send a JSON object."}), 400
        for flag in ("auto_low_risk", "ask_once_per_task", "voice_autostart"):
            if flag in data and not isinstance(data[flag], bool):
                return jsonify({"error": f"Field '{flag}' must be true or false."}), 400
        forced = data.get("always_confirm", [])
        if not isinstance(forced, list) or any(c not in approval_policy.USER_CATEGORIES for c in forced):
            return jsonify({"error": "always_confirm must list known categories.",
                            "categories": list(approval_policy.USER_CATEGORIES)}), 400
        current = approval_policy.load_prefs()
        await asyncio.to_thread(approval_policy.save_prefs, {**current, **data})
    return jsonify({
        "preferences": approval_policy.load_prefs(),
        "categories": list(approval_policy.USER_CATEGORIES),
        "active_approvals": approval_policy.grants.snapshot(),
    })


@security_bp.route("/api/security/automation/revoke", methods=["POST"])
async def revoke_automation_approvals():
    """Forget every approval that is currently remembered (they also expire and end at STOP)."""
    from core.security import approval_policy

    return jsonify({"revoked": approval_policy.grants.revoke_all()})


@security_bp.route("/api/security/diagnostics", methods=["GET"])
async def system_diagnostics():
    """Live readings for the control panel; unavailable values are null, never 0."""
    from core import diagnostics

    return jsonify(await asyncio.to_thread(diagnostics.collect))


@security_bp.route("/api/security/microphones", methods=["GET", "POST"])
async def microphones():
    """List input devices and the saved choice; POST {"name": str|null} selects one (null = Windows default)."""
    from voice import microphones as mics
    from voice.wake_word import wake_word_listener

    if request.method == "POST":
        data = (await request.get_json(silent=True)) or {}
        name = data.get("name")
        if name is not None and not isinstance(name, str):
            return jsonify({"error": "Field 'name' must be a string or null."}), 400
        try:
            ok, message = await asyncio.to_thread(mics.select, name)
        except Exception as exc:
            return jsonify({"error": f"Microphones unavailable ({type(exc).__name__})."}), 503
        if not ok:
            return jsonify({"error": message}), 409
        await asyncio.to_thread(wake_word_listener.restart)
    try:
        devices = await asyncio.to_thread(mics.list_input_devices)
        error = ""
    except Exception as exc:
        devices, error = [], f"Microphones unavailable ({type(exc).__name__})."
    status = wake_word_listener.status()
    return jsonify({
        "devices": devices,
        "selected": mics.selected_name(),
        "in_use": status["device"],
        "listener_state": status["state"],
        "error": error or status["error"],
    })


@security_bp.route("/api/security/ai-test", methods=["POST"])
async def ai_connection_test():
    """Send one tiny request to the configured AI model and report model, latency or the problem."""
    from tools.assistant_tools import ping_ai

    return jsonify(await asyncio.to_thread(ping_ai))


@security_bp.route("/api/security/startup", methods=["GET"])
async def get_startup():
    from core.startup_manager import get_startup_status

    return jsonify(get_startup_status().to_dict())


@security_bp.route("/api/security/startup", methods=["POST"])
async def set_startup():
    """Enable ({"enabled": true, "method": "Shortcut"|"TaskScheduler"}) or disable login auto-start."""

    from core.startup_manager import set_startup_enabled

    data = (await request.get_json(silent=True)) or {}
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        return jsonify({"error": "Field 'enabled' must be a boolean."}), 400
    method = str(data.get("method") or "Shortcut")
    ok, message, status = await asyncio.to_thread(set_startup_enabled, enabled, method)
    return jsonify({"ok": ok, "message": message, **status.to_dict()}), (200 if ok else 500)


@security_bp.route("/api/proactive", methods=["GET"])
async def get_proactive():
    try:
        limit = int(request.args.get("limit", "40"))
    except Exception as e:
        print(f"[WARN get_proactive] limit parse error: {e}")
        limit = 40
    return jsonify(_proactive_snapshot(limit=max(1, min(limit, 200))))


@security_bp.route("/api/proactive/clear", methods=["POST"])
async def clear_proactive_alerts():
    with PROACTIVE_LOCK:
        PROACTIVE_STATE["alerts"] = []
    return jsonify({"message": "Proactive alerts cleared."})


@security_bp.route("/api/control/quick", methods=["POST"])
async def control_quick_action():
    data = (await request.get_json(silent=True)) or {}
    action = str(data.get("action", "")).strip()
    print(f"\n[PANEL] Executing action: {action}")
    result = _ejecutar_accion_control(action)
    print(f"[PANEL] Result ({action}): {result}")
    return jsonify(
        {
            "action": action,
            "result": result,
            "security": _security_snapshot(),
            "proactive": _proactive_snapshot(limit=20),
            "plugins": {
                "last_reload": jarvis_brain.PLUGIN_STATE.get("last_reload", ""),
                "loaded": jarvis_brain.PLUGIN_STATE.get("loaded", {}),
                "errors": jarvis_brain.PLUGIN_STATE.get("errors", {}),
            },
        }
    )
