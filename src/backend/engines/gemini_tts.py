"""Natural-sounding speech through Gemini text-to-speech.

Used for spoken replies, greetings and the startup report when a Gemini key
is configured; the local Piper voice remains the offline fallback. Gemini TTS
handles Tamil, Thanglish and English pronunciation. Text is sent to Google.
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
import urllib.error
import urllib.request
import wave

from core.llm_providers import resolve_gemini_api_key

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
SAMPLE_RATE = 24000
TIMEOUT_SECONDS = 20
QUOTA_COOLDOWN_SECONDS = 600  # free-tier TTS quota is small; don't retry on every sentence
_blocked_until = 0.0


class GeminiTTSError(RuntimeError):
    """Gemini TTS was unavailable; callers fall back to the local voice."""


def enabled() -> bool:
    provider = str(os.getenv("JARVIS_TTS_PROVIDER") or "auto").strip().lower()
    if time.monotonic() < _blocked_until:
        return False
    return provider in {"auto", "gemini"} and bool(resolve_gemini_api_key())


def _style_prompt(text: str) -> str:
    style = os.getenv(
        "JARVIS_GEMINI_TTS_STYLE",
        "Say this in a warm, natural, human voice at a calm, unhurried pace, like a friendly assistant",
    ).strip()
    return f"{style}: {text}" if style else text


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def synthesize(text: str) -> bytes:
    """Return WAV bytes for `text`, or raise GeminiTTSError."""
    from core.cloud_policy import cloud_ai_allowed

    if not cloud_ai_allowed():  # the text would leave the PC; the local voice is used instead
        raise GeminiTTSError("local_only")
    key = resolve_gemini_api_key()
    if not key:
        raise GeminiTTSError("no_key")
    model = os.getenv("JARVIS_GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts").strip()
    voice = os.getenv("JARVIS_GEMINI_TTS_VOICE", os.getenv("JARVIS_GEMINI_LIVE_VOICE", "Charon")).strip() or "Charon"
    body = {
        "contents": [{"parts": [{"text": _style_prompt(text)}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    request = urllib.request.Request(
        f"{API_ROOT}/{model}:generateContent",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            global _blocked_until
            _blocked_until = time.monotonic() + QUOTA_COOLDOWN_SECONDS
        raise GeminiTTSError(f"http_{exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise GeminiTTSError(type(exc).__name__) from None
    try:
        part = payload["candidates"][0]["content"]["parts"][0]["inlineData"]
        pcm = base64.b64decode(part["data"])
    except (KeyError, IndexError, TypeError, ValueError):
        raise GeminiTTSError("no_audio") from None
    if not pcm:
        raise GeminiTTSError("empty_audio")
    return pcm_to_wav(pcm)
