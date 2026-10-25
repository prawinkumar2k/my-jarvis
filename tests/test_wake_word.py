from __future__ import annotations

import asyncio
import importlib.util
import io
import os
import wave
from pathlib import Path

import numpy as np
import pytest
from voice import wake_word
from voice.wake_word import WakeWordListener


class FakeModel:
    def __init__(self, scores):
        self.scores = list(scores)
        self.resets = 0

    def predict(self, _frame):
        return {"hey_jarvis": self.scores.pop(0)}

    def reset(self):
        self.resets += 1


def test_detection_respects_threshold_and_cooldown():
    listener = WakeWordListener()
    listener.threshold, listener.cooldown = 0.5, 2.0
    model = FakeModel([0.2, 0.9, 0.95, 0.8])
    frame = np.zeros(1280, dtype=np.int16)
    assert listener.process_frame(model, frame, now=100.0) is None  # below threshold
    first = listener.process_frame(model, frame, now=100.1)
    assert first is not None and first.score == 0.9
    assert listener.process_frame(model, frame, now=101.0) is None  # inside cooldown
    second = listener.process_frame(model, frame, now=103.0)
    assert second is not None and second.event_id == first.event_id + 1
    assert model.resets == 2
    status = listener.status(since_id=first.event_id)
    assert [e["event_id"] for e in status["events"]] == [second.event_id]
    assert status["local_only"] is True and status["listening"] is False


def test_start_failure_is_explained_not_raised(monkeypatch):
    listener = WakeWordListener()

    def boom():
        raise ModuleNotFoundError("openwakeword")

    monkeypatch.setattr(listener, "_load_model", boom)
    ok, message = listener.start()
    assert ok is False and "pip install -r requirements-optional.txt" in message
    assert listener.status()["error"] == message


def test_wakeword_route_validation_and_emergency_stop(monkeypatch):
    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    import jarvis_backend
    from core.security import emergency_stop

    stopped: list[bool] = []
    monkeypatch.setattr(wake_word.wake_word_listener, "stop", lambda: stopped.append(True))
    monkeypatch.setattr(wake_word.wake_word_listener, "start", lambda: (False, "No usable microphone"))

    async def run():
        client = jarvis_backend.app.test_client()
        h = {"Origin": "http://localhost:5002"}
        bad = await client.post("/api/security/wakeword", json={"enabled": "yes"}, headers=h)
        fail = await client.post("/api/security/wakeword", json={"enabled": True}, headers=h)
        await client.post("/api/security/emergency-stop", json={"engaged": True}, headers=h)
        blocked = await client.post("/api/security/wakeword", json={"enabled": True}, headers=h)
        await client.post("/api/security/emergency-stop", json={"engaged": False}, headers=h)
        return bad.status_code, fail.status_code, (await fail.get_json())["error"], blocked.status_code

    try:
        bad, fail, error, blocked = asyncio.run(run())
    finally:
        emergency_stop.release()
    assert bad == 400
    assert fail == 503 and "microphone" in error
    assert blocked == 409
    assert stopped, "emergency stop must stop the wake-word listener"


def _installed_model_dir() -> str | None:
    """Model folder from the test runtime or the user's real JARVIS data folder."""
    if importlib.util.find_spec("openwakeword") is None:
        return None
    candidates = [wake_word.model_dir()]
    if os.getenv("LOCALAPPDATA"):
        candidates.append(os.path.join(os.environ["LOCALAPPDATA"], "Jarvis", "models", "wakeword"))
    return next((d for d in candidates if os.path.isfile(os.path.join(d, wake_word.MODEL_FILE))), None)


@pytest.mark.skipif(_installed_model_dir() is None, reason="openWakeWord or the hey_jarvis model is not installed")
def test_real_engine_detects_spoken_hey_jarvis_offline(monkeypatch):
    folder = _installed_model_dir()
    monkeypatch.setattr(wake_word, "model_dir", lambda: folder)
    from piper import PiperVoice
    from scipy.signal import resample_poly

    root = Path(__file__).resolve().parents[1]
    voice = PiperVoice.load(str(root / "models" / "en_GB-northern_english_male-medium.onnx"))

    def speech(text):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            voice.synthesize_wav(text, wav)
        buf.seek(0)
        with wave.open(buf, "rb") as wav:
            rate = wav.getframerate()
            pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
        pad = np.zeros(16000, dtype=np.int16)
        return np.concatenate([pad, resample_poly(pcm.astype(np.float32), 16000, rate).astype(np.int16), pad])

    listener = WakeWordListener()
    model = listener._load_model()

    def detections(text):
        model.reset()
        audio = speech(text)
        return [e for i in range(0, len(audio) - 1280, 1280) if (e := listener.process_frame(model, audio[i:i + 1280], now=1000.0 + i))]

    assert len(detections("Hey Jarvis!")) == 1
    assert detections("Open notepad please.") == []
