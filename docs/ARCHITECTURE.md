# Architecture

```text
 Browser / WebView2 UI (src/frontend)
   │  text, voice (MediaRecorder / Gemini Live WS), STOP button
   ▼
 Quart app (jarvis_backend.py) ── before_request: token / trusted-origin guard
   │
   ├─ /api/chat, /api/chat/stream, /api/voice ─► CommandOrchestrator
   │                                              │ router / planner → immutable plan
   │                                              ▼
   │                                      ToolExecutionService  ◄── emergency_stop
   │                                              │ (exactly once per request/step)
   │                                              ▼
   │                                      security_manager._security_guard ◄── emergency_stop
   │                                              │ tool_policy: risk, admin, confirmation
   │                                              ▼
   │                                      tools/* (files, system, browser, spotify, …)
   │
   ├─ /ws live voice ─► LiveSession ⇄ Gemini Live (tools via same guard)
   └─ /api/language, /api/status, /api/security/*
```

## Language layer

1. `utils/jarvis_i18n.py` holds the **session language** (`en`, `es`, `ta`): Whisper language, browser locale, Piper model, fixed messages.
2. `utils/language_detection.py` classifies **each message** as Tamil script, Thanglish, Spanish or English, offline and deterministically. It strips code spans, paths and URLs first.
3. `core/brain/prompts.py` replaces the fixed "reply in English/Spanish" sentence in the system prompt with a `LANGUAGE POLICY` line for that turn. `voice/live_context.py` does the same for Gemini Live using the session language (the next utterance is unknown when the session starts).
4. `JARVIS_RESPONSE_LANGUAGE` can pin the reply language instead of mirroring.

Fixed messages (Spotify, YouTube, weather, errors) exist only in English and Spanish; every non-Spanish language uses English.

## Safety layers

| Layer | Purpose |
| --- | --- |
| HTTP guard | Critical routes need `JARVIS_API_TOKEN` or a trusted browser origin from loopback. |
| Tool catalog | Terminal, text writes, and mutating file tools are absent unless opted in. |
| Tool policy | `public` / `elevated` / `critical`; critical tools need confirmation from the control panel or auth resume, not from the model. |
| Path confinement | `tools/files.py` resolves symlinks and `..` before checking `JARVIS_FILE_WRITE_ROOTS`; credential files are never visible. |
| Emergency stop | One flag checked by both execution gates; engaging it also closes live voice sessions and the UI stops local audio. |
| Audit | `security_manager._security_audit` records blocks, stop/release, and critical tool use. |

## Design decisions

- **No new frameworks or providers.** Tamil support uses the existing Gemini/Groq LLMs, Whisper and Gemini Live; no extra TTS service was added because no free, offline, license-clear Tamil Piper voice was available to bundle.
- **Detector over model call.** A lexicon detector costs nothing, works offline, and is testable. It mis-detects only borderline single-word inputs, which then fall back to the session language.
- **Recycle Bin over permanent delete** on Windows, so the highest-risk file action is reversible.
- **Stop at the existing boundaries** rather than adding a new cancellation framework, so every current and future tool is covered automatically.
