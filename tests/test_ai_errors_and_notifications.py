from __future__ import annotations

import asyncio

import pytest
from core import notifications
from core.errors import LLMServiceError, classify_llm_failure


class RateLimitError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class APITimeoutError(Exception):
    pass


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (RateLimitError(), "rate_limited"),
        (AuthenticationError(), "auth_failed"),
        (APITimeoutError(), "timeout"),
        (ValueError("other"), "unavailable"),
        (None, "unavailable"),
    ],
)
def test_classify_llm_failure(exc, kind):
    assert classify_llm_failure(exc) == kind


def _raise_service_error(inner: Exception) -> LLMServiceError:
    try:
        raise inner
    except Exception:
        return LLMServiceError()


def test_service_error_keeps_reason_but_not_raw_message():
    err = _raise_service_error(RateLimitError("quota for key AIza-secret exceeded"))
    assert err.kind == "rate_limited"
    assert err.public_code == "llm_rate_limited"
    assert "AIza" not in err.public_message and "minute" in err.public_message


def test_chat_route_reports_rate_limit_clearly(monkeypatch):
    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    import jarvis_backend
    from api import chat_routes

    def boom(*_args, **_kwargs):
        raise _raise_service_error(RateLimitError())

    monkeypatch.setattr(chat_routes.jarvis_brain, "procesar_mensaje", boom)

    async def run():
        client = jarvis_backend.app.test_client()
        res = await client.post("/api/chat", json={"message": "hello"}, headers={"Origin": "http://localhost:5002"})
        return res.status_code, await res.get_json()

    status, body = asyncio.run(run())
    assert status == 503
    assert body["error"] == "llm_rate_limited"
    assert "limit" in body["message"]


def test_ai_ping_reports_not_configured(monkeypatch):
    from core.brain import brain_state
    from tools import assistant_tools

    monkeypatch.setattr(brain_state, "llm", None)
    result = assistant_tools.ping_ai()
    assert result == {"ok": False, "model": "", "latency_ms": None, "problem": "not_configured"}


def test_toast_passes_text_by_environment_not_script(monkeypatch):
    captured = {}

    class Done:
        returncode = 0

    def fake_run(args, env, **_kwargs):
        captured["args"], captured["env"] = args, env
        return Done()

    monkeypatch.setattr(notifications.sys, "platform", "win32")
    monkeypatch.setattr(notifications.subprocess, "run", fake_run)
    assert notifications.show_toast("JARVIS", "'; Remove-Item C:\\ -Recurse; '") is True
    script = captured["args"][-1]
    assert "Remove-Item" not in script
    assert captured["env"]["JARVIS_TOAST_TEXT"].startswith("'; Remove-Item")
    assert "SecurityElement]::Escape($env:JARVIS_TOAST_TEXT)" in script
