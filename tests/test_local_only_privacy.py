"""Local-only mode keeps data on the PC; the AI route endpoint tells the truth and leaks no secrets.

Unit tests with fakes: they prove JARVIS does not *attempt* cloud calls in local-only mode, not that no
other software on the PC does.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
from types import SimpleNamespace

import pytest
from core import cloud_policy
from core.security import approval_policy as ap


@pytest.fixture
def local_only(monkeypatch):
    monkeypatch.setenv("JARVIS_AI_MODE", "local_only")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("a cloud request was attempted"))


def test_switch_follows_the_mode(monkeypatch):
    monkeypatch.delenv("JARVIS_AI_MODE", raising=False)
    assert cloud_policy.cloud_ai_allowed()
    monkeypatch.setenv("JARVIS_AI_MODE", "local_first")
    assert cloud_policy.cloud_ai_allowed()
    monkeypatch.setenv("JARVIS_AI_MODE", "LOCAL_ONLY")
    assert not cloud_policy.cloud_ai_allowed()


def test_gemini_speech_is_not_requested(local_only, monkeypatch):
    from engines import gemini_tts

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    with pytest.raises(gemini_tts.GeminiTTSError, match="local_only"):
        gemini_tts.synthesize("hello")


def test_cloud_transcription_is_off(monkeypatch):
    from voice.transcription import GroqAudioTranscriber

    stt = GroqAudioTranscriber("test-key", "whisper", 5)
    monkeypatch.delenv("JARVIS_AI_MODE", raising=False)
    assert stt.configured
    monkeypatch.setenv("JARVIS_AI_MODE", "local_only")
    assert not stt.configured
    assert stt.transcribe(b"audio", "en") == ""  # the recording is never uploaded


def test_screen_analysis_captures_nothing_in_local_only_mode(local_only, monkeypatch):
    from tools import utilities

    monkeypatch.setattr(utilities, "_bloqueo_si_no_autorizado", lambda: None)
    text = utilities.analizar_pantalla.invoke({})
    assert "Local-only" in text and "did not capture" in text


def test_clipboard_asks_once_normally_and_not_at_all_in_local_only(monkeypatch):
    monkeypatch.delenv("JARVIS_AI_MODE", raising=False)
    assert ap.classify("leer_portapapeles", {}).tier is ap.Tier.TASK  # the text may reach the cloud AI
    monkeypatch.setenv("JARVIS_AI_MODE", "local_only")
    assert ap.classify("leer_portapapeles", {}).tier is ap.Tier.AUTO
    assert ap.classify("analizar_pantalla", {}).tier is ap.Tier.AUTO  # explicit request; the tool refuses by itself


def test_live_voice_refuses_to_open_the_microphone_stream_in_local_only_mode(local_only):
    import jarvis_backend

    async def run():
        client = jarvis_backend.app.test_client()
        async with client.websocket("/api/voice/stream", headers={"Origin": "http://localhost:5002"}) as ws:
            return json.loads(await asyncio.wait_for(ws.receive(), 5))

    message = asyncio.run(run())
    assert message["type"] == "error" and message["code"] == "local_only"
    assert "nothing is sent" in message["message"]


# ── /api/security/ai-route ───────────────────────────────────────────────────
def test_ai_route_reports_the_chain_and_never_a_key(monkeypatch):
    import jarvis_backend

    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    monkeypatch.setenv("JARVIS_AI_MODE", "cloud_first")
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-GEMINI-VALUE-123")
    monkeypatch.setenv("GROQ_API_KEY", "SECRET-GROQ-VALUE-456")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")

    async def run():
        client = jarvis_backend.app.test_client()
        response = await client.get("/api/security/ai-route", headers={"Origin": "http://localhost:5002"})
        return response.status_code, await response.get_data(as_text=True)

    status, body = asyncio.run(run())
    data = json.loads(body)
    assert status == 200 and "SECRET" not in body
    assert data["mode"] == "cloud_first" and data["local_only"] is False and data["configured"] is True
    assert [(c["role"], c["provider"]) for c in data["chain"]] == [
        ("primary", "gemini"), ("backup", "gemini"), ("fallback", "groq"), ("fallback", "ollama")]
    assert data["speech_to_text"]["where"] == "local (this PC)"


def test_ai_route_in_local_only_mode_lists_only_the_local_model(monkeypatch):
    import jarvis_backend

    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    monkeypatch.setenv("JARVIS_AI_MODE", "local_only")
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-GEMINI-VALUE-123")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")

    async def run():
        response = await jarvis_backend.app.test_client().get("/api/security/ai-route", headers={"Origin": "http://localhost:5002"})
        return json.loads(await response.get_data(as_text=True))

    data = asyncio.run(run())
    assert data["local_only"] is True
    assert [c["provider"] for c in data["chain"]] == ["ollama"]  # Gemini is not even in the chain


# ── who answered ─────────────────────────────────────────────────────────────
def test_the_model_that_answered_is_recorded(monkeypatch):
    from core.brain import brain_state, processor

    class Model:
        def __init__(self, name, fail=False):
            self.model_name, self.fail = name, fail

        def invoke(self, _messages):
            if self.fail:
                raise RuntimeError("quota")
            return SimpleNamespace(content="ok")

    monkeypatch.setattr(brain_state, "llm_primary_provider", "gemini")
    monkeypatch.setattr(brain_state, "llm_fallback_provider", "groq")
    monkeypatch.setattr(brain_state, "last_answer", {})
    primary, fallback = Model("gemini-2.5-flash"), Model("openai/gpt-oss-120b")
    monkeypatch.setattr(brain_state, "llm_fallback", fallback)

    processor._invoke_with_fallback(primary, [], event="t")
    assert brain_state.last_answer["provider"] == "gemini" and brain_state.last_answer["role"] == "primary"

    processor._invoke_with_fallback(Model("gemini-2.5-flash", fail=True), [], event="t")
    assert brain_state.last_answer["model"] == "openai/gpt-oss-120b"
    assert brain_state.last_answer["provider"] == "groq" and brain_state.last_answer["role"] == "fallback"
