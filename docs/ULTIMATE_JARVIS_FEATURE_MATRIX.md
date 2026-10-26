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
| Backup AI when Gemini is rate-limited | VERIFIED | Groq `openai/gpt-oss-120b`; real fallback observed (`llm_fallback_succeeded`) |
| Local AI (Ollama `qwen2.5:3b`, Q4_K_M, 1.93 GB) | VERIFIED | Real inference: cold load 150 s once, then 0.2–3.5 s; 100% on the T500 GPU; tool calling works; Thanglish quality poor |
| AI mode `cloud_first` / `local_first` / `local_only` | VERIFIED (unit) | Default cloud_first: Gemini → Groq → Ollama |
| Offline everyday commands (no AI call) | VERIFIED (unit) | apps, media, brightness, screenshot, timers, alarms, notes, summary, self check, layouts |
| Streaming text while typing | PARTIAL | Tool replies arrive whole; plain chat streams |

## Voice

| Feature | Status | Notes |
| --- | --- | --- |
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
| Volume, mute/unmute (exact via pycaw) | VERIFIED | |
| Media keys for any player | UNVERIFIED | Not pressed during tests to avoid pausing your music |
| Brightness | VERIFIED | Read and set on the built-in screen |
| Screenshot | VERIFIED | Saved to Pictures\JARVIS Screenshots |
| Screen analysis (vision) | UNVERIFIED | Enabled; uses Gemini |
| Clipboard read/write, secrets withheld | VERIFIED | |
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
| Persistent multi-step tasks resumed after restart | MISSING | Exactly-once pipeline exists; no task checkpoints |

## Integrations

| Feature | Status | Notes |
| --- | --- | --- |
| Gmail, Google Calendar | BLOCKED | Needs a Google Cloud OAuth client and your sign-in |
| Spotify control | BLOCKED | Needs Spotify app credentials |
| Telegram | BLOCKED | Needs a bot token |
| Coding agent | MISSING | |
| Smart home / IoT | MISSING | No devices or APIs configured |
