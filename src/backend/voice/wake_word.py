"""Offline "Hey Jarvis" wake word with openWakeWord.

The microphone is opened only while the user has the listener enabled. Audio
is processed in memory in 80 ms frames and is never stored or sent anywhere;
only detection events (time + score) leave this module. Models are downloaded
once into %LOCALAPPDATA%\\Jarvis\\models\\wakeword. The pretrained "hey_jarvis"
model is CC BY-NC-SA 4.0 (non-commercial use).
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass

from core.runtime_logger import log_info, log_warning

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # 80 ms, the frame size openWakeWord expects
MODEL_NAME = "hey_jarvis"
MODEL_FILE = "hey_jarvis_v0.1.onnx"


def _float_env(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name) or default)
    except ValueError:
        value = default
    return max(low, min(high, value))


def model_dir() -> str:
    from core.runtime_paths import resolve_runtime_paths

    return str(resolve_runtime_paths().models_cache / "wakeword")


@dataclass(frozen=True)
class WakeEvent:
    event_id: int
    at: float
    score: float


class WakeWordListener:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._events: deque[WakeEvent] = deque(maxlen=20)
        self._next_id = 1
        self.error = ""
        self.threshold = _float_env("JARVIS_WAKE_WORD_THRESHOLD", 0.5, 0.1, 0.95)
        self.cooldown = _float_env("JARVIS_WAKE_WORD_COOLDOWN", 2.0, 0.5, 10.0)

    # ── lifecycle ──────────────────────────────────────────
    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> tuple[bool, str]:
        with self._lock:
            if self.running:
                return True, "already listening"
            try:
                model = self._load_model()
                import sounddevice  # noqa: F401
            except Exception as exc:
                self.error = self._explain(exc)
                log_warning("wake_word_start_failed", error=type(exc).__name__)
                return False, self.error
            self.error = ""
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, args=(model,), name="jarvis-wake-word", daemon=True)
            self._thread.start()
            log_info("wake_word_listening", engine="openwakeword", threshold=self.threshold)
            return True, "listening"

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=3)
        self._thread = None

    # ── detection ─────────────────────────────────────────
    def _load_model(self):
        from openwakeword.model import Model
        from openwakeword.utils import download_models

        target = model_dir()
        os.makedirs(target, exist_ok=True)
        needed = (MODEL_FILE, "melspectrogram.onnx", "embedding_model.onnx")
        if not all(os.path.isfile(os.path.join(target, name)) for name in needed):
            download_models(model_names=[MODEL_NAME], target_directory=target)
        return Model(
            wakeword_models=[os.path.join(target, MODEL_FILE)],
            inference_framework="onnx",
            melspec_model_path=os.path.join(target, "melspectrogram.onnx"),
            embedding_model_path=os.path.join(target, "embedding_model.onnx"),
        )

    def process_frame(self, model, frame, now: float | None = None) -> WakeEvent | None:
        """Score one 80 ms int16 frame; record an event above threshold outside the cooldown."""
        scores = model.predict(frame)
        score = float(max(scores.values())) if scores else 0.0
        if score < self.threshold:
            return None
        now = time.time() if now is None else now
        with self._lock:
            if self._events and now - self._events[-1].at < self.cooldown:
                return None
            event = WakeEvent(self._next_id, now, round(score, 3))
            self._next_id += 1
            self._events.append(event)
        model.reset()  # avoid re-triggering on the tail of the same phrase
        return event

    def _run(self, model) -> None:
        import sounddevice as sd

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME_SAMPLES) as stream:
                while not self._stop.is_set():
                    frames, _overflow = stream.read(FRAME_SAMPLES)
                    self.process_frame(model, frames[:, 0])
        except Exception as exc:
            self.error = self._explain(exc)
            log_warning("wake_word_stream_failed", error=type(exc).__name__)

    @staticmethod
    def _explain(exc: Exception) -> str:
        name = type(exc).__name__
        if isinstance(exc, ModuleNotFoundError):
            return "Wake-word engine not installed. Run: pip install -r requirements-optional.txt"
        if "PortAudio" in name or "PortAudio" in str(exc):
            return "No usable microphone (check it is connected and allowed in Windows privacy settings)."
        return f"Wake-word engine failed ({name})."

    # ── status ────────────────────────────────────────────
    def status(self, since_id: int = 0) -> dict:
        with self._lock:
            events = [asdict(e) for e in self._events if e.event_id > since_id]
        return {
            "engine": "openwakeword",
            "phrase": "Hey Jarvis",
            "listening": self.running,
            "threshold": self.threshold,
            "cooldown_seconds": self.cooldown,
            "error": self.error,
            "events": events,
            "local_only": True,
        }


wake_word_listener = WakeWordListener()
