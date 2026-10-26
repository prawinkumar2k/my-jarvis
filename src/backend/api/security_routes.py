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
    """approve (control-panel confirmation), resume or cancel a persistent task."""
    from core import task_engine

    if action not in {"approve", "resume", "cancel"}:
        return jsonify({"error": "Unknown action."}), 400
    if task_engine.get_task(task_id) is None:
        return jsonify({"error": "No such task."}), 404
    if action == "cancel":
        task = await asyncio.to_thread(task_engine.cancel_task, task_id)
    else:
        if action == "approve":
            await asyncio.to_thread(task_engine.approve_step, task_id)
        task = await asyncio.to_thread(task_engine.run_task, task_id)
    return jsonify({"task": task, "summary": task_engine.summarize(task)})


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


@security_bp.before_app_serving
async def _start_reminder_notifications():
    import os

    if os.getenv("JARVIS_TEST_MODE") != "1":
        _background_tasks.add(asyncio.create_task(_reminder_notification_loop()))


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
