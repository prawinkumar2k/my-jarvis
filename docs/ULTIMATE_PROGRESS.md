# JARVIS Ultimate: phased progress

Durable log for the phased plan (A–I). Each phase lists what changed, how it
was checked, and what is still open. Nothing here has been pushed to GitHub.

## Baseline

- Branch `feature/jarvis-ultimate`; local AI routing Gemini → Groq → Ollama
  (`qwen2.5:3b`), `JARVIS_AI_MODE=cloud_first`.
- `pytest -q`: 1065 passed before this phase work; 1077 passed, 1 skipped after
  Phase B; 1091 passed, 1 skipped after Phase A; 1125 passed, 1 skipped after
  Phase C and the task panel; 1146 passed, 1 skipped after the Gemini/browser/voice
  continuation. `ruff check src/backend` clean throughout; `pip_audit` found no
  known vulnerabilities.

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
- Real browser (Edge, headless, real backend): the spoken startup briefing
  showed STOP VOICE; Esc stopped it mid-sentence ("Audio detenido") and hid
  the button. Fixed a second bug found there: the button stayed visible after
  speech ended on its own; verified hidden once the queue finished.
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

## Phase B follow-up: task control panel

- Right-hand control panel lists real tasks from `GET /api/security/tasks`
  (refresh every 4 s): state, goal, id, active step / total, failed steps,
  retries, started / finished time, the exact step and arguments awaiting
  approval, last error, and per-step history.
- Actions are offered only when eligible and re-checked on the backend (409
  otherwise): approve, reject (the risky step never runs; task cancelled),
  resume (pending/interrupted only; never skips an approval), cancel.
  Approve/resume run in the background (202) so the UI never blocks.
- Duplicate protection: buttons lock while a request is in flight, and the
  engine refuses a second concurrent run of the same task.
- After a restart, tasks left `running` show as stopped/interrupted and can be
  resumed; completed steps are not repeated. Emergency stop blocks approve and
  resume. Old `tasks.db` files are upgraded in place (new timestamp columns).
- Task text is rendered with `textContent` only (no HTML injection).
- Real end-to-end check (Edge + real backend, isolated data folder): a task
  of `diagnostico_sistema` -> `listar_pantallas` -> `instalar_programa
  Gyan.FFmpeg` was resumed from the panel, paused at NEEDS APPROVAL, approved
  from the panel and finished DONE 3/3 (FFmpeg was already installed, so
  nothing on the PC changed).

## Phase C: Windows automation

Already present and reused: window list/focus/minimize/maximize/restore/close
by handle (`desktop_control.py`), split/grid layouts, clipboard read/write with
secret filtering, file tools confined to allowed roots (symlink and `..`
resolution before the check, no overwrite, protected `.env`/keys, Recycle Bin
delete, confirmation for move/organize/delete, SHA-256 duplicate finder),
Playwright browser tools.

Added:
- Multi-monitor (`tools/displays.py`): live monitor list (screen 1 =
  primary), which screen each window is on, `mover_ventana_a_pantalla`
  (full/left/right/top/bottom/center focus layout), and `organizar_ventanas`
  now takes a screen. Targets are validated against the current monitors.
  Display settings are never changed.
  Real check (one 1920x1080 screen): a Notepad window JARVIS opened was placed
  at exactly (0,0,960,1008), (240,126,1440,756) and (960,0,960,1008); screen 2
  and bad positions were refused. Multi-monitor geometry (negative
  coordinates, unplugged screen, straddling) is unit-tested only; no second
  monitor was available.
- Clipboard: `limpiar_portapapeles`; non-text content (images, files) is
  reported as such. Reading the clipboard now needs a yes each time, and the
  question says whether the text may go to a cloud AI (Gemini/Groq).
- Files: `informacion_archivo` (type, size, dates, read-only, link) inside
  allowed roots only.
- winget (`tools/winget.py`): `buscar_programa`, `ver_programa`,
  `instalar_programa`, `cancelar_instalacion`. Argument lists only, validated
  ids and queries, official `winget` source only, user scope only (a package
  needing an admin install is reported, never elevated), one install at a
  time, identity re-verified before install, result checked with
  `winget list`. The confirmation question shows id, name, version,
  publisher, source and license (new `confirmation_preview` hook).
  Real checks: searches for vlc/7zip returned real ids; unknown and malformed
  ids refused; "install Gyan.FFmpeg" verified identity and stopped as already
  installed. No new package was installed (only FFmpeg was authorized).
- Diagnostics (`core/diagnostics.py`, `diagnostico_sistema`,
  `GET /api/security/diagnostics`): CPU, memory, every drive, disk health
  (WMI), battery with time left, GPUs (NVIDIA utilization/VRAM via
  nvidia-smi; others marked "utilization unavailable"), top memory processes,
  winget/FFmpeg/Ollama status. Unavailable readings are null, never 0. Real
  run: 3.5 s at 100% CPU; KIOXIA SSD Healthy, T500 and Iris Xe listed.
- Browser: click and type now require admin plus a yes each time (they can
  submit, buy or send); the question says what will be clicked/typed and
  whether Enter submits. Page text returned to the AI is labelled as web
  content, not instructions. BLOCKED: the Playwright Chromium browser is not
  downloaded (about 150 MB, needs your approval:
  `python -m playwright install chromium`); the default mode opens your
  normal browser.
- UI fix found during the real-browser check: the microphone selector with a
  long device name pushed the header off-screen; its width is now capped.

## Continuation: Gemini, browser, voice, automatic tasks

Gemini (real API, key from `.env`, never printed or logged; 0 key matches in
the backend log):
- Key valid (model list works). `gemini-2.5-flash` returned 429
  RESOURCE_EXHAUSTED: free tier is 20 requests/day per model, so the daily
  quota was used up. Free quotas are per model, so JARVIS now tries a backup
  Gemini model (`gemini-3.1-flash-lite`, verified to make tool calls) before
  Groq. `gemini-2.5-flash-lite` is retired for new users (404);
  `gemini-flash-latest` returned 503 (busy) when tested.
- Real results through the app: AI test OK in 2.2 s (reports the model that
  actually answered); battery/CPU question ran `informacion_sistema` and the
  answer used its result; a codeword was remembered on the next turn; one
  request chained `listar_pantallas` and `informacion_sistema`.
- Natural language -> plan -> tools: "Create a saved multi-step task called
  Evening check ... run it now" made Gemini call `ejecutar_tarea_multipaso`
  with three real tools; diagnostics and screen listing ran, the winget step
  paused for approval, and the reply described exactly that. Before a fix,
  Gemini picked the older `crear_plan_acciones` (limited tool list) and the
  user only saw "The requested action failed"; both tool descriptions now say
  which to use.
- Streaming: on the default pipeline `/api/chat/stream` delivers the reply in
  one final event (no token-by-token output). Token streaming exists only in
  the legacy pipeline; it now falls back to the backup provider when the
  primary fails before the first token and reports the real error code.
- Timeouts (10 s cloud, no automatic retries), quota/auth/network error codes
  and the UI's AI test were already in place.

Browser automation (no Chromium download needed):
- JARVIS now launches Playwright's Chromium if present, else the installed
  Microsoft Edge, else Chrome (`JARVIS_BROWSER_CHANNEL`), with a fresh
  separate profile (no user cookies or logins). A browser that cannot start
  gives one clear error instead of a 35 s timeout.
- Real check with Edge on a local test page: navigate (1.4 s), type, click,
  read the result ("Hello, Prawin"); the page's "ignore previous
  instructions" text came back labelled as web content; a missing element
  gives a one-line error after 8 s and the browser keeps working.
- Fixed: an explicit local URL (`http://127.0.0.1:8765/`) was turned into a
  Google search, sending it to Google. Loopback URLs now open directly.
- Emergency STOP now also cancels a running winget install and closes the
  automation browser (it does not undo completed actions).

Voice:
- Installed model: faster-whisper `small` (model.bin 484 MB), multilingual,
  100 languages including Tamil.
- `JARVIS_STT_LANGUAGE`: follow the UI language (default), `auto` (Whisper
  detects; for mixed Tamil/English), or a fixed code. Real: English audio was
  detected as `en` (probability 1.0) with the UI in Tamil. The transcriber
  reports the detected language and audio length (never the words) and that
  processing was local.
- Tamil/Thanglish accuracy: still BLOCKED. Needed: 20+ WAV (or WebM/OGG)
  clips, 16 kHz+ mono, 2–10 s each, your own voice, a mix of pure Tamil,
  Thanglish and English commands, plus `manifest.csv` with
  `file,language,kind,reference` where `reference` is exactly what was said
  (Tamil in Tamil script, Thanglish in English letters). Then run
  `scripts/evaluate_stt.py <folder>`.
- Tamil text-to-speech: no offline option is installed. Piper has no Tamil
  voice (178 voices, 58 languages). Windows has only English voices here; the
  free "Microsoft Valluvar" Tamil voice can be added in Settings > Time &
  language > Speech (an OS step only you can do; JARVIS would then also need
  a Windows-voice engine). Cloud options: Gemini TTS (quota-limited).

Setup and startup: the first-run wizard already takes the provider and key,
validates it with a live call, optionally saves it to `.env` and switches the
running AI without a restart; auto-start uses a visible Startup-folder
shortcut or logon task with a header toggle; the launcher has a watchdog. No
tray icon (needs the `pystray` package: approval).

Not changed: an orphaned test backend from the previous session was still
listening on port 5002 when this continuation started; stopping it was
refused by the tool permission system, so it must be closed manually (Task
Manager: the `python.exe` running `src/backend/jarvis_backend.py` started at
19:14) before starting JARVIS normally.

## Phases D–I

Not started.
