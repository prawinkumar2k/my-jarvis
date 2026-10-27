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
| Local AI (Ollama `qwen2.5:3b`, Q4_K_M, 1.93 GB; `qwen3.5:4b` opt-in, 20/20 tools but 5x slower per call) | VERIFIED | Real inference: cold load 150 s once, then 0.2–3.5 s; 100% on the T500 GPU; tool calling works; Thanglish quality poor |
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
| Clipboard read/write/clear, secrets withheld | VERIFIED (unit) | Reading asks once (text may reach the cloud AI); no question in local-only mode |
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
| Browser click/type: one approval per session; submit/buy/send/sign-in always asks | VERIFIED (unit) | Page text is untrusted; Chromium download not needed (installed Edge works) |
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
| Repeating reminders (daily / weekdays / weekly), quiet hours | VERIFIED (unit) | Fixed-clock tests incl. a week of downtime = one missed fire; alarms and timers ignore quiet hours |
| Scheduled routines / daily summaries on a schedule | VERIFIED (unit + browser, mocked backend) | Only tools that never need approval can be scheduled; missed runs fire once; results kept, panel + voice tools |
| Memory panel (list / edit / forget / export / private mode / clear all / auto-forget after 30-90-365 days) | VERIFIED (unit + browser, mocked backend) | Clear all needs the typed phrase; old memories are dated from first sight |

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
| Ask before a screenshot goes to the cloud AI | VERIFIED (unit) | Setting, off by default; always asks when on |
| Tray icon (Open / Quit) | VERIFIED (unit) / UNVERIFIED on screen | `pystray` installed (small, listed in requirements-optional.txt); closing the window still quits; `JARVIS_TRAY_ENABLED=false` turns it off |
| First-run setup check (AI keys, mic, FFmpeg, speech, startup) with exact fixes | VERIFIED (unit + browser, mocked backend) | Read-only; never shows key values |
| Read text on screen / in an image (offline Windows OCR) | VERIFIED (real OCR on a generated image) | Screenshot deleted after use; password/key/card/code lines hidden; text treated as untrusted quote |
| Launcher: window at once, waits up to 300 s, recovers a blank WebView2 | VERIFIED (unit) + reproduced | Blank hidden window reproduced under pythonw; now retried, then opened in the default browser |
| Voice no longer cut by short noise / speaker echo | VERIFIED (unit) | Time-based barge-in; real-room behaviour needs your confirmation |
| Web search without Tavily/Brave keys | VERIFIED | Real: Chennai weather with sources via Gemini Google Search grounding; blocked in local_only |
| Task control panel (approve / reject / resume / cancel) | VERIFIED | Real Edge + backend end-to-end; backend re-checks eligibility |
| Risk-tiered approvals (auto / once per task / always ask), user settings | VERIFIED (unit) | 87 tests; policy applies to chat, voice, browser and the task engine through one guard |
| Plan approved once, dangerous steps still ask; edited plans need re-approval | VERIFIED (unit) | Bound to a plan hash; emergency STOP withdraws approvals |
| "ok / seri / sari / pannu" approves, "yes but don't" does not | VERIFIED (unit) | Whole-message match; unrelated message drops the pending question |
| Approval card above the composer (shows what one yes covers) | VERIFIED (browser, mocked backend) | Double-click sends once; task text cannot inject HTML |
| Message composer: Enter / Shift+Enter / Send / STOP / Retry / IME | VERIFIED (browser, mocked backend) | Real Edge; the fake backend proves the front-end contract, not the AI |
| Local-only mode blocks Gemini voice, Gemini TTS, Groq STT, screenshot upload, search grounding | VERIFIED (unit) | Proves JARVIS makes no attempt; cannot see other software |
| Voice listens from launch (no button), never prompts for the mic itself, can be turned off | VERIFIED (browser, stubbed mic) / UNVERIFIED on your PC | Needs the mic already allowed in WebView; the real hardware path is not yet confirmed |
| Manual AI mode (one provider, no silent fallback) | VERIFIED (unit) | `JARVIS_AI_MODE=manual` + `JARVIS_LLM_PROVIDER` |
| Assistant UI: status bar (AI route, who answered), welcome + suggestions | VERIFIED (browser, mocked backend) | Real data only; "unavailable" when missing |

## Integrations

| Feature | Status | Notes |
| --- | --- | --- |
| Gmail, Google Calendar | BLOCKED | Needs a Google Cloud OAuth client and your sign-in |
| Spotify control | BLOCKED | Needs Spotify app credentials |
| Telegram | BLOCKED | Needs a bot token |
| Coding agent | MISSING | |
| Smart home / IoT | MISSING | No devices or APIs configured |
