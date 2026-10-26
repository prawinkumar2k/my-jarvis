# JARVIS Ultimate: phased progress

Durable log for the phased plan (A–I). Each phase lists what changed, how it
was checked, and what is still open. Nothing here has been pushed to GitHub.

## Baseline

- Branch `feature/jarvis-ultimate`; local AI routing Gemini → Groq → Ollama
  (`qwen2.5:3b`), `JARVIS_AI_MODE=cloud_first`.
- `pytest -q`: 1065 passed before this phase work; 1077 passed, 1 skipped after
  Phase B; 1091 passed, 1 skipped after Phase A.

## Phase A: offline voice

Speech-to-text:
- Local speech-to-text uses faster-whisper `small` (464 MB, downloaded once
  with approval, cached under the Hugging Face cache). Set with
  `JARVIS_WHISPER_MODEL="small"`; the code default is still `medium`, which is
  not downloaded, so keep the setting in `.env`.
- Fixed a real breakage: PyAV 19 removed an argument faster-whisper 1.2.1
  passes, so every local transcription crashed. JARVIS now decodes audio
  itself (`utils.audio_conversion.decode_for_whisper`, stdlib for PCM WAV,
  FFmpeg for other formats) and hands Whisper a 16 kHz float32 array.
- Live check with the network blocked (`HF_HUB_OFFLINE=1`): Piper-spoken
  English sentences transcribed exactly (3/3 WAV, plus WebM/Opus and
  OGG/Opus after FFmpeg), 2.6–7 s each on CPU. Whisper stays on CPU so it
  does not compete with Ollama for the T500's 4 GB VRAM.

FFmpeg (installed 2026-10-26, with approval):
- Package `Gyan.FFmpeg` 9.0.2 from the official `winget` source, publisher
  Gyan (gyan.dev, the Windows build linked from ffmpeg.org), GPL-3.0, portable
  zip, user scope, no elevation. `winget install` exit 0; `ffmpeg -version`
  exit 0 in a fresh process.
- `utils.audio_conversion.ffmpeg_executable()` also looks in winget's
  per-user folders, so a JARVIS started before the PATH change still finds it
  (verified with FFmpeg removed from PATH).

Microphone selection and recovery:
- `voice/microphones.py` lists input devices (MME, deduplicated, full names),
  saves the choice by name in `memory/microphone.json`, and falls back to the
  Windows default with a clear message when the saved mic is missing.
- The offline listener opens one stream at a time, reports `state`
  (starting/listening/reconnecting/failed/stopped) and the device in use, and
  retries a failed stream at most 5 times in a row with 1–16 s backoff; 30 s
  of healthy audio resets the budget.
- API: `GET/POST /api/security/microphones` (protected like other
  `/api/security` routes; hostile origins get 403). Header selector in the
  UI; browser capture (recorder and Gemini Live) uses the same mic via label
  matching, falling back to the default if it is unplugged.
- Real machine: one physical mic (Intel Smart Sound array) listed as default;
  listener opened it, switched choice and reopened, rejected an unknown
  device, and fell back correctly for an unplugged saved choice.
  Not verified: physically unplugging a mic (only a built-in array is
  present); recovery is covered by fake-device tests.

Stop speaking:
- One `stopSpeaking()` action stops the local TTS queue and Gemini Live
  playback (the Live session stays open). Escape key and a STOP VOICE header
  button (shown only while speaking). Emergency stop already released audio.
- Fixed a gap: stopping between two queued sentences did not cancel the rest.
  A Node test runs the real `main.js` functions and failed on the old code.
- This is "press to stop", not barge-in by voice for the local TTS path;
  Gemini Live keeps its existing barge-in.

Tamil / Thanglish:
- BLOCKED on real recordings. `scripts/evaluate_stt.py` measures WER (English,
  Thanglish) and CER by Tamil letter (Tamil script) from a folder of genuine
  recordings plus `manifest.csv` (file, language, kind, reference). No numbers
  are reported because no real Tamil speech was available; synthetic speech
  would not be honest evidence.
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
