# Ultimate JARVIS Feature Matrix

Status as of 2026-10-26 on Prawin's Windows 11 laptop. Categories:
**VERIFIED** = implemented and checked on this machine or by automated tests ·
**UNVERIFIED** = implemented, not yet observed end-to-end · **PARTIAL** ·
**MISSING** · **BLOCKED** = needs an external account, key, hardware or payment.

Evidence: `pytest -q` (all passing, see TEST_REPORT.md), live checks noted below.

## Intelligence (Gemini)

| Feature | Status | Notes |
| --- | --- | --- |
| Gemini chat with tools (function calling), Thanglish replies | VERIFIED | Live: "system condition enna" → tool run → Thanglish answer |
| Clear rate-limit / bad-key / network errors | VERIFIED | `llm_rate_limited`, `llm_auth_failed`, `llm_timeout`, `llm_network` (tested) |
| Connection test (model, latency, problem) | VERIFIED (unit) | `POST /api/security/ai-test`; "nee ok-a?" uses it |
| Backup AI when Gemini is rate-limited | VERIFIED | Gemini backup model `gemini-3.1-flash-lite` (real: answered while 2.5-flash daily quota was exhausted), then Groq, then Ollama |
| Real Gemini tool use, context, multi-step | VERIFIED | Live: tool ran and result fed back; codeword remembered across turns; two tools chained in one request |
| Local AI (Ollama `qwen2.5:3b`, Q4_K_M, 1.93 GB) | VERIFIED | Real inference: cold load 150 s once, then 0.2–3.5 s; 100% on the T500 GPU; tool calling works; Thanglish quality poor |
| AI mode `cloud_first` / `local_first` / `local_only` | VERIFIED (unit) | Default cloud_first: Gemini → Groq → Ollama |
| Offline everyday commands (no AI call) | VERIFIED (unit) | apps, media, brightness, screenshot, timers, alarms, notes, summary, self check, layouts |
| Streaming text while typing | PARTIAL | `/api/chat/stream` on the default pipeline sends the reply in one final event; token streaming exists only in the legacy pipeline (now with fallback) |

## Voice

| Feature | Status | Notes |
| --- | --- | --- |
| Offline speech-to-text (faster-whisper `small`, CPU int8) | VERIFIED | Network blocked: English WAV, WebM/Opus, OGG/Opus transcribed exactly; 2.6–7 s each |
| FFmpeg audio conversion | VERIFIED | `Gyan.FFmpeg` 9.0.2 via winget (user scope) |
| Microphone selection, unplugged fallback, reconnect | PARTIAL | Real mic listed/selected/reopened; physical unplug not tested (built-in mic only) |
| Stop speaking (Esc / STOP VOICE) | VERIFIED | Real browser: Esc stopped the spoken briefing; button hides after speech |
| Tamil / Thanglish transcription accuracy | BLOCKED | Needs real recordings; harness `scripts/evaluate_stt.py` ready |
| STT language: follow UI / auto-detect / forced | VERIFIED | Real: English audio detected as en (p=1.0) with UI in Tamil and `JARVIS_STT_LANGUAGE=auto` |
| Tamil spoken replies (offline) | BLOCKED | No Piper Tamil voice exists; Windows Tamil voice must be added in Settings first |
| Offline "Hey Jarvis" wake word | UNVERIFIED | Engine + real mic verified; your own voice not yet confirmed |
| Gemini Live two-way voice, interruption | UNVERIFIED | Used by voice button and wake word; natural voice |
| Spoken replies | VERIFIED | Gemini voice when quota allows, otherwise local `ryan-high` |
| Natural voice for every reply | BLOCKED | Gemini TTS free quota is tiny (HTTP 429); needs billing |
| Voice closes after 45 s silence | UNVERIFIED | Code + tests |
| Language switch by voice | VERIFIED (unit) | "switch to English", "Tamil-la pesu" |

## Windows control

| Feature | Status | Notes |
| --- | --- | --- |
| Open apps, close/focus windows | VERIFIED | Notepad, WhatsApp, PowerPoint seen in logs |
| Window layouts (split / grid) | VERIFIED | Two Notepads placed at exact half screens |
| Move window to a screen / focus layout | VERIFIED (1 screen) | Exact rects on the real display; multi-monitor geometry unit-tested only |
| Volume, mute/unmute (exact via pycaw) | VERIFIED | |
| Media keys for any player | UNVERIFIED | Not pressed during tests to avoid pausing your music |
| Brightness | VERIFIED | Read and set on the built-in screen |
| Screenshot | VERIFIED | Saved to Pictures\JARVIS Screenshots |
| Screen analysis (vision) | UNVERIFIED | Enabled; uses Gemini |
| Clipboard read/write/clear, secrets withheld, yes before reading | VERIFIED (unit) | Reading may send text to the cloud AI, so it asks first |
| Lock / shutdown / restart with confirmation | existing | `controlar_pc` |
| Windows Settings pages | UNVERIFIED | |
| Wi-Fi / Bluetooth on/off | MISSING | Needs admin rights; opens Settings instead |
| Windows notifications | VERIFIED | Toast shown on this laptop |

## Files

| Feature | Status | Notes |
| --- | --- | --- |
| List / search / create / copy / move / rename / organize | VERIFIED | Allowed folders only |
| Delete to Recycle Bin with confirmation | PARTIAL | Recycle Bin path not exercised by tests |
| Duplicate finder (SHA-256), large files | VERIFIED | |
| File details (size, dates, read-only, link) | VERIFIED (unit) | Allowed folders only |
| Install software with winget (approval, user scope) | PARTIAL | Real search and identity check; real install path stopped as already installed; installs unit-tested only |
| Full diagnostics (GPU, disk health, battery time) | VERIFIED | Real readings; unavailable shown as unavailable |
| Browser click/type need approval | VERIFIED (unit) | |
| Browser automation (navigate, type, click, read) | VERIFIED | Real: installed Edge via Playwright, local test page; no Chromium download needed |
| Emergency STOP stops winget install and closes automation browser | VERIFIED (unit) | Does not undo actions already completed |
| PDF / spreadsheet understanding | MISSING | |

## Companion, memory, reminders

| Feature | Status | Notes |
| --- | --- | --- |
| Personality + honesty rules, capability registry | VERIFIED | |
| Memory list / edit / forget / private mode, secrets refused | VERIFIED | |
| Reminders, timers, alarms (survive restart, spoken, toast) | VERIFIED | |
| Notes by voice, daily summary, health check | VERIFIED | |
| Spoken startup report with Chennai weather | VERIFIED | |
| Recurring routines, quiet hours | MISSING | |

## Startup, safety, reliability

| Feature | Status | Notes |
| --- | --- | --- |
| Login auto-start, zero-click boot, single instance, JARVIS icon | VERIFIED | Real sign-out/sign-in not yet done |
| Backend watchdog (auto-restart) | VERIFIED (unit) | |
| Emergency STOP (tools, live voice, playback, wake word) | VERIFIED | |
| Tool risk levels, confirmation, path confinement, audit | VERIFIED | |
| API key in Windows Credential Manager | MISSING | Key is in `.env` (git-ignored) |
| Persistent multi-step tasks resumed after restart | VERIFIED | Unit tests + real UI run: resume, approval pause, approve, done 3/3 |
| Natural language -> saved plan -> tools -> approval | VERIFIED | Real Gemini: built a 3-step task, ran 2, paused install for approval, reported accurately |
| Tray icon | MISSING | Needs the `pystray` package (approval) |
| Task control panel (approve / reject / resume / cancel) | VERIFIED | Real Edge + backend end-to-end; backend re-checks eligibility |

## Integrations

| Feature | Status | Notes |
| --- | --- | --- |
| Gmail, Google Calendar | BLOCKED | Needs a Google Cloud OAuth client and your sign-in |
| Spotify control | BLOCKED | Needs Spotify app credentials |
| Telegram | BLOCKED | Needs a bot token |
| Coding agent | MISSING | |
| Smart home / IoT | MISSING | No devices or APIs configured |
