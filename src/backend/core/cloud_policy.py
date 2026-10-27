"""Single answer to "may this request leave the PC for a cloud AI service?".

JARVIS_AI_MODE=local_only means no text, audio, image or file content is sent to
Gemini, Groq or any other cloud AI. Every cloud-facing feature (chat models, Gemini
voice and speech, Groq transcription, screenshot analysis, Google Search grounding)
checks this before sending anything and falls back to a local path or says so.
"""

from __future__ import annotations

import os

LOCAL_ONLY_MESSAGE = "Local-only mode is on, so nothing is sent to cloud AI services."


def cloud_ai_allowed() -> bool:
    return str(os.getenv("JARVIS_AI_MODE") or "").strip().lower() != "local_only"
