"""Setup health check: honest statuses, exact fixes, no secrets, a broken check never looks like a pass."""

from __future__ import annotations

import asyncio
import json

import pytest
from core import setup_check


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "OLLAMA_MODEL", "JARVIS_AI_MODE", "JARVIS_LLM_PROVIDER"):
        monkeypatch.delenv(name, raising=False)


def by_id(result):
    return {c["id"]: c for c in result["checks"]}


def test_no_ai_configured_is_missing_with_a_fix(monkeypatch):
    check = setup_check._ai()
    assert check["status"] == "missing" and "key" in check["fix"].lower()


def test_ai_chain_is_reported_without_any_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-ONE-123456")
    monkeypatch.setenv("GROQ_API_KEY", "SECRET-TWO-654321")
    result = setup_check._ai()
    assert result["status"] == "ok" and "gemini -> groq" in result["detail"]
    assert "SECRET" not in json.dumps(result)


def test_ollama_states(monkeypatch):
    import urllib.request

    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")

    class Reply:
        def __init__(self, names):
            self.body = json.dumps({"models": [{"name": n} for n in names]}).encode()

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Reply(["qwen2.5:3b"]))
    assert setup_check._ollama()["status"] == "ok"
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Reply(["other:1b"]))
    wrong = setup_check._ollama()
    assert wrong["status"] == "warn" and wrong["fix"] == "ollama pull qwen2.5:3b"

    def down(*a, **k):
        raise OSError("refused")

    monkeypatch.setattr(urllib.request, "urlopen", down)
    assert setup_check._ollama()["status"] == "warn"  # a model is expected, so a stopped server is a warning
    monkeypatch.delenv("OLLAMA_MODEL")
    assert setup_check._ollama()["status"] == "missing"


def test_remote_ollama_address_is_not_probed(monkeypatch):
    import urllib.request

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.50:11434")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("must not contact a remote host"))
    assert setup_check._ollama()["status"] == "warn"


def test_missing_microphone_and_voice_file(monkeypatch, tmp_path):
    monkeypatch.setattr("voice.microphones.list_input_devices", lambda *a, **k: [])
    assert setup_check._microphone()["status"] == "missing"
    monkeypatch.setenv("JARVIS_TTS_MODEL_EN", str(tmp_path / "nope.onnx"))
    assert setup_check._voice()["status"] == "warn"
    (tmp_path / "ok.onnx").write_bytes(b"x")
    monkeypatch.setenv("JARVIS_TTS_MODEL_EN", str(tmp_path / "ok.onnx"))
    assert setup_check._voice()["status"] == "ok"


def test_speech_model_found_only_when_the_weights_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setenv("JARVIS_WHISPER_MODEL", "small")
    assert setup_check._speech_model()["status"] == "warn"
    weights = tmp_path / "hub" / "models--Systran--faster-whisper-small" / "snapshots" / "abc"
    weights.mkdir(parents=True)
    (weights / "model.bin").write_bytes(b"x")
    assert setup_check._speech_model()["status"] == "ok"


def test_a_check_that_crashes_is_a_warning_never_ok(monkeypatch):
    def boom():
        raise RuntimeError("secret internals")

    monkeypatch.setattr(setup_check, "_ollama", boom)
    monkeypatch.setattr(setup_check, "_tools", lambda: [])
    result = setup_check.run_checks()
    crashed = [c for c in result["checks"] if "Could not check (RuntimeError)" in c["detail"]]
    assert crashed and crashed[0]["status"] == "warn" and "secret internals" not in json.dumps(result)


def test_summary_and_ready_flag(monkeypatch):
    for name in ("_ai", "_ollama", "_microphone", "_speech_model", "_voice", "_wake_word", "_startup"):
        monkeypatch.setattr(setup_check, name, lambda n=name: setup_check._item(n, n, "ok", "fine"))
    monkeypatch.setattr(setup_check, "_tools", lambda: [setup_check._item("ffmpeg", "FFmpeg", "missing", "no", "winget install Gyan.FFmpeg")])
    result = setup_check.run_checks()
    assert result["summary"] == {"ok": 7, "warn": 0, "missing": 1} and result["ready"] is False


def test_route_returns_the_report_and_refuses_hostile_origins(monkeypatch):
    import jarvis_backend

    monkeypatch.setenv("JARVIS_TEST_MODE", "1")

    async def run():
        client = jarvis_backend.app.test_client()
        good = await client.get("/api/security/setup-check", headers={"Origin": "http://localhost:5002"})
        bad = await client.get("/api/security/setup-check", headers={"Origin": "https://evil.example"})
        return good.status_code, await good.get_json(), bad.status_code

    status, body, hostile = asyncio.run(run())
    assert status == 200 and {"checks", "summary", "ready"} <= body.keys() and hostile == 403
    assert all({"id", "label", "status", "detail", "fix"} <= c.keys() for c in body["checks"])
