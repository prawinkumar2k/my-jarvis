"""
Security Routes: security policy, proactive alerts, quick control.
"""

from core.jarvis_observability import obs_snapshot
from quart import Blueprint, jsonify, request

security_bp = Blueprint("security", __name__)

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


@security_bp.route("/api/security/startup", methods=["GET"])
async def get_startup():
    from core.startup_manager import get_startup_status

    return jsonify(get_startup_status().to_dict())


@security_bp.route("/api/security/startup", methods=["POST"])
async def set_startup():
    """Enable ({"enabled": true, "method": "Shortcut"|"TaskScheduler"}) or disable login auto-start."""
    import asyncio

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
