"""Free Edge voice: voice choice, privacy, resting after failures, fallback order. No network is used."""

from __future__ import annotations

import asyncio

import pytest
from engines import edge_voice


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv("JARVIS_AI_MODE", raising=False)
    monkeypatch.delenv("JARVIS_TTS_PROVIDER", raising=False)
    monkeypatch.delenv("JARVIS_EDGE_TTS_VOICE", raising=False)
    monkeypatch.delenv("JARVIS_EDGE_TTS_VOICE_TA", raising=False)
    monkeypatch.setattr(edge_voice, "_blocked_until", 0.0)
    monkeypatch.setattr(edge_voice, "_package_available", lambda: True)


def test_tamil_text_gets_the_tamil_voice_and_everything_else_indian_english():
    assert edge_voice.pick_voice("வணக்கம் jarvis") == "ta-IN-PallaviNeural"
    assert edge_voice.pick_voice("Battery 80 percent") == "en-IN-NeerjaNeural"
    assert edge_voice.pick_voice("Naan ready, bro") == "en-IN-NeerjaNeural"  # Thanglish reads fine in Indian English


def test_voices_can_be_overridden(monkeypatch):
    monkeypatch.setenv("JARVIS_EDGE_TTS_VOICE", "en-IN-PrabhatNeural")
    monkeypatch.setenv("JARVIS_EDGE_TTS_VOICE_TA", "ta-IN-ValluvarNeural")
    assert edge_voice.pick_voice("hello") == "en-IN-PrabhatNeural"
    assert edge_voice.pick_voice("வணக்கம்") == "ta-IN-ValluvarNeural"


def test_local_only_and_piper_only_never_reach_microsoft(monkeypatch):
    monkeypatch.setattr(edge_voice, "_download_mp3", lambda *_a: pytest.fail("text must not leave the PC"))
    monkeypatch.setenv("JARVIS_AI_MODE", "local_only")
    assert not edge_voice.enabled()
    with pytest.raises(edge_voice.EdgeTTSError, match="local_only"):
        edge_voice.synthesize("hello")
    monkeypatch.delenv("JARVIS_AI_MODE")
    monkeypatch.setenv("JARVIS_TTS_PROVIDER", "piper")
    assert not edge_voice.enabled()
    monkeypatch.setenv("JARVIS_TTS_PROVIDER", "gemini")
    assert not edge_voice.enabled()


def test_enabled_by_default_when_the_package_is_installed(monkeypatch):
    assert edge_voice.enabled()
    monkeypatch.setattr(edge_voice, "_package_available", lambda: False)
    assert not edge_voice.enabled()


def test_success_returns_wav_and_uses_the_chosen_voice(monkeypatch):
    seen = []

    async def fake(text, voice):
        seen.append(voice)
        return b"ID3mp3"

    monkeypatch.setattr(edge_voice, "_download_mp3", fake)
    monkeypatch.setattr(edge_voice, "_to_wav", lambda mp3: b"RIFF" + mp3)
    assert edge_voice.synthesize("வணக்கம்") == b"RIFFID3mp3" and seen == ["ta-IN-PallaviNeural"]


def test_a_failure_rests_the_service_so_piper_takes_over(monkeypatch):
    async def broken(text, voice):
        raise ConnectionError("offline")

    monkeypatch.setattr(edge_voice, "_download_mp3", broken)
    with pytest.raises(edge_voice.EdgeTTSError, match="ConnectionError"):
        edge_voice.synthesize("hello")
    assert not edge_voice.enabled()  # resting for a few minutes


def test_empty_audio_is_a_failure_too(monkeypatch):
    async def empty(text, voice):
        return b""

    monkeypatch.setattr(edge_voice, "_download_mp3", empty)
    with pytest.raises(edge_voice.EdgeTTSError, match="empty_audio"):
        edge_voice.synthesize("hello")


def test_missing_ffmpeg_is_reported_not_hidden(monkeypatch):
    monkeypatch.setattr("utils.audio_conversion.ffmpeg_executable", lambda: None)
    with pytest.raises(edge_voice.EdgeTTSError, match="no_ffmpeg"):
        edge_voice._to_wav(b"mp3")


def test_the_route_uses_edge_when_gemini_is_unavailable_and_piper_when_edge_fails(monkeypatch):
    import threading

    from api import tts_routes
    from engines import gemini_tts
    from quart import Quart

    monkeypatch.setattr(gemini_tts, "enabled", lambda: False)
    monkeypatch.setattr(tts_routes, "_tts_engine", type("E", (), {"voice": object()})())
    monkeypatch.setattr(tts_routes, "_tts_api_lock", threading.Lock())
    monkeypatch.setattr(tts_routes, "_synthesize_audio", lambda text: b"RIFFpiper")
    monkeypatch.setattr(tts_routes, "_check_rate_limit", lambda *_a: (True, 0))
    app = Quart(__name__)
    app.register_blueprint(tts_routes.tts_bp)

    async def speak():
        client = app.test_client()
        response = await client.post("/api/tts", json={"text": "hello"})
        return response.status_code, await response.get_data()

    monkeypatch.setattr(edge_voice, "synthesize", lambda text: b"RIFFedge")
    assert asyncio.run(speak()) == (200, b"RIFFedge")

    def fail(text):
        raise edge_voice.EdgeTTSError("down")

    monkeypatch.setattr(edge_voice, "synthesize", fail)
    assert asyncio.run(speak()) == (200, b"RIFFpiper")
