from __future__ import annotations

import base64
import io
import json
import urllib.error
import wave

import pytest
from engines import gemini_tts


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(gemini_tts, "_blocked_until", 0.0)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("JARVIS_TTS_PROVIDER", raising=False)


def test_returns_wav_from_gemini_pcm(monkeypatch):
    pcm = b"\x01\x00" * 2400
    payload = {"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(pcm).decode()}}]}}]}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(gemini_tts.urllib.request, "urlopen", lambda req, timeout: Resp(json.dumps(payload).encode()))
    wav = gemini_tts.synthesize("Vanakkam")
    with wave.open(io.BytesIO(wav)) as w:
        assert w.getframerate() == 24000 and w.getnframes() == 2400


def test_quota_error_pauses_gemini_and_falls_back(monkeypatch):
    def quota(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(gemini_tts.urllib.request, "urlopen", quota)
    assert gemini_tts.enabled() is True
    with pytest.raises(gemini_tts.GeminiTTSError):
        gemini_tts.synthesize("Vanakkam")
    assert gemini_tts.enabled() is False  # no more slow 429 round-trips for a while


def test_disabled_without_key_or_when_forced_local(monkeypatch):
    monkeypatch.setenv("JARVIS_TTS_PROVIDER", "piper")
    assert gemini_tts.enabled() is False
    monkeypatch.delenv("JARVIS_TTS_PROVIDER")
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert gemini_tts.enabled() is False
