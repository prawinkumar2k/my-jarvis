# Implementation Audit

Audit of the JARVIS source as imported on 2026-10-25, before and during the
`feature/jarvis-ultimate` work. Every statement below was checked against the
code, not the README.

## Baseline

| Item | Finding |
| --- | --- |
| Source | ZIP download of upstream `SrDarkoll/JARVIS` (v0.1.0-alpha.4 era). Not a git repository. |
| Git | Initialized locally. `main` = untouched import (upstream links removed only). No remote. |
| Python | 3.11 / 3.12 supported (`setup.ps1` enforces). Verified on 3.12.10. |
| Size | ~35k lines backend Python (149 files), vanilla JS frontend, 88 test files. |
| Tests on `main` | 801 passed, 2 failed, 1 skipped, 95 errors when run from a temp worktree. The 95 errors were pytest `tmp_path` creation failures in that location (environment). In the project folder the same suite collects cleanly. |
| Pre-existing failures | `test_frontend_i18n::test_conversation_layout_is_not_clipped_by_center_stage` (CSS assertion; still fails, untouched). |
| Voice models | `models/*.onnx` were Git LFS **pointer files**, not models. Local Piper TTS could not work from the ZIP. `setup.ps1` tried `git lfs pull`, which cannot work without a remote. |

## Architecture found

- **Entry points:** `start_app.py` (desktop shell via pywebview, re-execs into `venv`), `src/backend/jarvis_backend.py` (Quart + Hypercorn on port 5002).
- **LLM providers:** Gemini (primary) and Groq (fallback) through an OpenAI-compatible client (`core/brain/llm_engine.py`, `core/llm_providers.py`).
- **Command pipeline:** `core/command_pipeline/` — router/planner produce immutable plans; `ToolExecutionService` is the only side-effect boundary with request/step idempotency. Chat, streaming and voice share `CommandOrchestrator`.
- **Voice:** Gemini Live bidirectional WebSocket (`voice/live_gemini.py`, `live_session.py`, `live_transport.py`) with barge-in, reconnection, and fallback to a hybrid STT → LLM → TTS path. STT: Groq Whisper or local faster-whisper. TTS: Piper (local), per-language `.onnx` model.
- **Wake word:** browser `SpeechRecognition` regex for "jarvis" (`main.js`). It is not a local wake-word engine; in Chromium/WebView2 recognition audio is processed by the browser vendor's online service.
- **Voice identity:** SpeechBrain-based (`voice/identifier.py`), disabled unless `JARVIS_VOICE_ID_ENABLED=true`.
- **Security:** `core/security/tool_policy.py` (public/elevated/critical, admin-only, confirmation), `services/security_manager.py` (`_security_guard`, strict mode, domain/app allowlists, audit trail). Confirmation is transport state (`control_panel`/`auth_resume`), never a model argument. Critical HTTP routes require token or trusted origin + loopback.
- **Tools:** apps, volume, power, processes, windows (Win32), Playwright browser, YouTube, Spotify (API + Windows UIA), weather, reminders, math, computer-use, action plans, procedural/cognitive memory, vault notes. Terminal and text-file writes are opt-in.
- **Memory:** SQLite stores (`modules/memory/store.py`, `engines/db.py`), Obsidian-style vault, optional FAISS RAG.
- **Background:** APScheduler monitoring/briefing, proactive desktop observer, Telegram — all off in core mode.
- **CI:** ruff, pyright (basic, baseline file list), pytest with coverage ≥ 50%, compileall.

## Gaps against the requested scope

| Gap | Evidence |
| --- | --- |
| No Tamil / Thanglish | `LANGUAGE_CONFIG` had only `en`/`es`; ~21 call sites treated "not English" as Spanish. |
| No file management tools | Only `leer_archivo` (read) and opt-in `crear_archivo_texto`. |
| No system-info / Settings tools | Only `ver_procesos_pesados`. |
| No emergency stop | No global cancellation; no UI control. |
| Setup broken for ZIP installs | LFS pointer models + mandatory `git lfs pull`. |
| No local wake-word engine | Browser recognition only. |
| No clipboard, duplicate finder, winget, monitor-layout, calendar/email, Docker/DB tools | Not present. |

## What this branch changed

See [FEATURE_MATRIX.md](FEATURE_MATRIX.md) for status and [TEST_REPORT.md](TEST_REPORT.md) for evidence.
