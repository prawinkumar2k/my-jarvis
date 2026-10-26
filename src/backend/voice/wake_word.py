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
MAX_RECONNECTS = 5  # bounded retries after a microphone error
STABLE_SECONDS = 30.0  # a stream that ran this long resets the retry budget


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
        self.state = "stopped"  # stopped | listening | reconnecting | failed
        self.device_name = ""
        self.reconnects = 0
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
            self.state = "stopped"
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
        self.state = "stopped"

    def restart(self) -> tuple[bool, str]:
        """Reopen the microphone (after the user picks a different one)."""
        if not self.running:
            return True, "not listening"
        self.stop()
        return self.start()

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

    def _open_stream(self, device):
        import sounddevice as sd

        return sd.InputStream(device=device, samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME_SAMPLES)

    def _run(self, model, clock=time.monotonic) -> None:
        """One stream at a time; on a device error retry with backoff, at most MAX_RECONNECTS times in a row."""
        from voice.microphones import resolve_device

        self.reconnects = 0
        while not self._stop.is_set():
            try:
                device, self.device_name, note = resolve_device()
                with self._open_stream(device) as stream:
                    opened = clock()
                    self.state, self.error = "listening", note
                    while not self._stop.is_set():
                        frames, _overflow = stream.read(FRAME_SAMPLES)
                        self.process_frame(model, frames[:, 0])
                        if self.reconnects and clock() - opened > STABLE_SECONDS:
                            self.reconnects = 0
            except Exception as exc:
                log_warning("wake_word_stream_failed", error=type(exc).__name__, attempt=self.reconnects + 1)
                if self.reconnects >= MAX_RECONNECTS:
                    self.state, self.error = "failed", self._explain(exc)
                    return
                self.reconnects += 1
                self.state = "reconnecting"
                self.error = f"Microphone problem; retrying ({self.reconnects}/{MAX_RECONNECTS})."
                self._stop.wait(min(16.0, 2.0 ** (self.reconnects - 1)))
        self.state = "stopped"

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
            "state": ("starting" if self.state == "stopped" else self.state) if self.running else ("failed" if self.state == "failed" else "stopped"),
            "device": self.device_name,
            "reconnects": self.reconnects,
            "threshold": self.threshold,
            "cooldown_seconds": self.cooldown,
            "error": self.error,
            "events": events,
            "local_only": True,
        }


def _pref_path():
    from core.runtime_paths import resolve_runtime_paths

    return resolve_runtime_paths().memory / "wake_word.json"


def remembered_enabled() -> bool:
    """Whether the user left the wake word ON last time (restored at startup)."""
    import json

    try:
        return bool(json.loads(_pref_path().read_text(encoding="utf-8")).get("enabled"))
    except (OSError, ValueError):
        # No saved choice yet: on by default for a voice-first assistant.
        return str(os.getenv("JARVIS_WAKE_WORD_DEFAULT") or "true").strip().lower() not in {"0", "false", "no", "off"}


def remember_enabled(enabled: bool) -> None:
    import json

    try:
        path = _pref_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"enabled": bool(enabled)}), encoding="utf-8")
    except OSError as exc:
        log_warning("wake_word_pref_save_failed", error=type(exc).__name__)


wake_word_listener = WakeWordListener()
