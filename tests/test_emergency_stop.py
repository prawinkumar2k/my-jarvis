from __future__ import annotations

import asyncio

import pytest
from core.command_pipeline.execution import ToolExecutionService
from core.command_pipeline.models import ActionStep, CommandRequest, ReceiptStatus
from core.security import emergency_stop
from services import security_manager


@pytest.fixture(autouse=True)
def _released():
    emergency_stop.release()
    yield
    emergency_stop.release()


def _request(request_id: str) -> CommandRequest:
    return CommandRequest.create(
        text="open notepad", profile_id="admin", channel="chat", language="en", request_id=request_id
    )


def _step() -> ActionStep:
    return ActionStep(step_id="s1", tool_name="abrir_aplicacion", arguments={"nombre_app": "notepad"})


def test_engaged_stop_blocks_pipeline_without_invoking_tool():
    calls: list[str] = []
    service = ToolExecutionService(lambda _r, _s: calls.append("ran") or "ok")
    emergency_stop.engage("test")

    receipt = service.execute(_request("r1"), _step())

    assert calls == []
    assert receipt.status is ReceiptStatus.BLOCKED
    assert receipt.diagnostic_code == "emergency_stop_active"
    assert receipt.verified is False


def test_release_allows_new_requests_but_does_not_replay_blocked_ones():
    calls: list[str] = []
    service = ToolExecutionService(lambda _r, _s: calls.append("ran") or "ok")
    emergency_stop.engage("test")
    service.execute(_request("r1"), _step())
    emergency_stop.release()

    # The blocked request stays blocked (no automatic retry after release).
    assert service.execute(_request("r1"), _step()).status is ReceiptStatus.DUPLICATE
    assert calls == []
    assert service.execute(_request("r2"), _step()).status is ReceiptStatus.SUCCEEDED
    assert calls == ["ran"]


def test_security_guard_refuses_any_tool_while_engaged():
    emergency_stop.engage("test")
    allowed, reason = security_manager._security_guard("ver_procesos_pesados", {}, "", "chat", "admin")
    assert allowed is False
    assert "Emergency stop" in reason


def test_cancel_hooks_run_and_failures_are_reported():
    ran: list[str] = []
    emergency_stop.register_cancel_hook("ok", lambda: ran.append("ok"))

    def _boom() -> None:
        raise RuntimeError("cannot interrupt")

    emergency_stop.register_cancel_hook("stuck", _boom)
    try:
        state = emergency_stop.engage("test")
    finally:
        emergency_stop.unregister_cancel_hook("ok")
        emergency_stop.unregister_cancel_hook("stuck")
    assert ran == ["ok"]
    assert state.engaged is True
    assert state.hook_failures == ("stuck",)


def test_live_session_manager_close_all_closes_sessions():
    from voice.live_session import LiveSessionManager

    async def _run() -> tuple[int, object]:
        manager = LiveSessionManager()

        async def _noop(_data):
            return None

        await manager.create_session("a", _noop, _noop)
        await manager.create_session("b", _noop, _noop)
        closed = await manager.close_all()
        return closed, await manager.get_session("a")

    closed, remaining = asyncio.run(_run())
    assert closed == 2
    assert remaining is None


def test_emergency_stop_route_engages_and_releases(monkeypatch):
    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    import jarvis_backend

    async def _run():
        client = jarvis_backend.app.test_client()
        headers = {"Origin": "http://localhost:5002"}
        engaged = await client.post("/api/security/emergency-stop", json={"engaged": True}, headers=headers)
        status = await client.get("/api/security/emergency-stop", headers=headers)
        bad = await client.post("/api/security/emergency-stop", json={"engaged": "yes"}, headers=headers)
        hostile = await client.post(
            "/api/security/emergency-stop", json={"engaged": False}, headers={"Origin": "https://evil.example"}
        )
        still = emergency_stop.is_engaged()
        released = await client.post("/api/security/emergency-stop", json={"engaged": False}, headers=headers)
        return engaged, await status.get_json(), bad.status_code, hostile.status_code, still, released

    engaged, status, bad, hostile, still, released = asyncio.run(_run())
    assert engaged.status_code == 200
    assert status["engaged"] is True
    assert bad == 400
    assert hostile in (401, 403)
    assert still is True
    assert released.status_code == 200
    assert emergency_stop.is_engaged() is False
