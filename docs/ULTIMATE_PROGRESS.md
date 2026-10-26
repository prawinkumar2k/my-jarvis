# JARVIS Ultimate: phased progress

Durable log for the phased plan (A–I). Each phase lists what changed, how it
was checked, and what is still open. Nothing here has been pushed to GitHub.

## Baseline

- Branch `feature/jarvis-ultimate`; local AI routing Gemini → Groq → Ollama
  (`qwen2.5:3b`), `JARVIS_AI_MODE=cloud_first`.
- `pytest -q`: 1065 passed before this phase work; 1077 passed, 1 skipped after.

## Phase A: offline voice (in progress)

Done:
- Local speech-to-text uses faster-whisper `small` (464 MB, downloaded once
  with approval, cached under the Hugging Face cache). Set with
  `JARVIS_WHISPER_MODEL="small"`; the code default is still `medium`, which is
  not downloaded, so keep the setting in `.env`.
- Fixed a real breakage: PyAV 19 removed an argument faster-whisper 1.2.1
  passes, so every local transcription crashed. JARVIS now decodes audio
  itself (`utils.audio_conversion.decode_for_whisper`, stdlib for PCM WAV,
  FFmpeg for other formats) and hands Whisper a 16 kHz float32 array.
- Live check with the network blocked (`HF_HUB_OFFLINE=1`): Piper-spoken
  sentences transcribed exactly (3/3), 4–7 s each on CPU. Whisper stays on CPU
  so it does not compete with Ollama for the T500's 4 GB VRAM.

Open:
- FFmpeg is not installed, so WebM/OGG recordings cannot be decoded; the
  browser path sends WAV. Installing FFmpeg needs your approval (winget).
- Tamil/Thanglish transcription accuracy not yet measured (no Tamil sample
  voice available locally).
- Microphone selection/recovery and interruptible playback: not yet changed.
- Tamil TTS: no local Tamil voice; spoken Tamil replies need Gemini TTS quota.

## Phase B: persistent task engine (done, unit-verified)

- `core/task_engine.py`: SQLite store `memory/tasks.db`; states pending,
  running, completed, failed, cancelled, interrupted, approval_required.
- Every step passes the existing security guard. Steps whose tool requires
  confirmation pause until approved; approval travels as a control-panel
  confirmation. Risky steps are never retried; others retry at most twice with
  backoff. Completed steps are never re-run. Running tasks are marked
  interrupted at startup and can be resumed. Emergency stop halts a task.
- Tools: `ejecutar_tarea_multipaso`, `ver_tareas`, `reanudar_tarea`,
  `cancelar_tarea`. API: `GET /api/security/tasks`,
  `POST /api/security/tasks/<id>/approve|resume|cancel`.
- Tests: `tests/test_task_engine.py` (8). Not yet exercised from the UI.

## Phases C–I

Not started.
