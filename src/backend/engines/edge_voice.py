"""Free natural voices (Tamil and Indian English) through Microsoft Edge's read-aloud service.

No account, key or payment. Order for spoken replies: Gemini (when it has quota), this voice, then the offline
Piper voice. The text is sent to Microsoft, so it is blocked in local-only mode. The service is unofficial and
can change or rate-limit without notice; after a failure it rests for a few minutes and Piper is used.
Needs the optional `edge-tts` package and FFmpeg (to turn the MP3 into WAV).
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import time

FAILURE_COOLDOWN_SECONDS = 180
TIMEOUT_SECONDS = 25
SAMPLE_RATE = 24000
DEFAULT_VOICE = "en-IN-NeerjaNeural"  # Indian English: reads Thanglish naturally
DEFAULT_TAMIL_VOICE = "ta-IN-PallaviNeural"
_TAMIL = re.compile("[஀-௿]")
_blocked_until = 0.0


class EdgeTTSError(RuntimeError):
    """The free voice was unavailable; callers fall back to the offline voice."""


def _package_available() -> bool:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return True


def enabled() -> bool:
    provider = str(os.getenv("JARVIS_TTS_PROVIDER") or "auto").strip().lower()
    if provider not in {"auto", "edge"} or time.monotonic() < _blocked_until:
        return False
    from core.cloud_policy import cloud_ai_allowed

    return cloud_ai_allowed() and _package_available()


def pick_voice(text: str) -> str:
    if _TAMIL.search(text):
        return str(os.getenv("JARVIS_EDGE_TTS_VOICE_TA") or DEFAULT_TAMIL_VOICE).strip() or DEFAULT_TAMIL_VOICE
    return str(os.getenv("JARVIS_EDGE_TTS_VOICE") or DEFAULT_VOICE).strip() or DEFAULT_VOICE


async def _download_mp3(text: str, voice: str) -> bytes:
    import edge_tts

    chunks = []
    async for part in edge_tts.Communicate(text, voice).stream():
        if part["type"] == "audio":
            chunks.append(part["data"])
    return b"".join(chunks)


def _to_wav(mp3: bytes) -> bytes:
    from utils.audio_conversion import ffmpeg_executable

    exe = ffmpeg_executable()
    if not exe:
        raise EdgeTTSError("no_ffmpeg")
    try:
        done = subprocess.run(
            [exe, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
             "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "wav", "pipe:1"],
            input=mp3, capture_output=True, timeout=TIMEOUT_SECONDS, check=False, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (subprocess.TimeoutExpired, OSError):
        raise EdgeTTSError("ffmpeg_failed") from None
    if done.returncode != 0 or not done.stdout.startswith(b"RIFF"):
        raise EdgeTTSError("ffmpeg_failed")
    return done.stdout


def synthesize(text: str) -> bytes:
    """Return WAV bytes for `text`, or raise EdgeTTSError. Runs in a worker thread."""
    global _blocked_until
    from core.cloud_policy import cloud_ai_allowed

    if not cloud_ai_allowed():  # the text would leave the PC
        raise EdgeTTSError("local_only")
    if not _package_available():
        raise EdgeTTSError("not_installed")
    try:
        mp3 = asyncio.run(asyncio.wait_for(_download_mp3(text, pick_voice(text)), TIMEOUT_SECONDS))
    except Exception as exc:  # network, rate limit, service change: rest, then Piper
        _blocked_until = time.monotonic() + FAILURE_COOLDOWN_SECONDS
        raise EdgeTTSError(type(exc).__name__) from None
    if not mp3:
        _blocked_until = time.monotonic() + FAILURE_COOLDOWN_SECONDS
        raise EdgeTTSError("empty_audio")
    return _to_wav(mp3)
