# Feature Matrix

Status meanings: **verified** = implemented and covered by automated tests or a
recorded run in this environment; **implemented** = code exists but needs
manual/hardware verification; **partial** = works with stated gaps;
**existing** = upstream feature, unchanged, covered by upstream tests;
**not started** / **blocked** = absent.

## Language and voice

| Feature | Files | Status | Test method | Notes |
| --- | --- | --- | --- | --- |
| Written Tamil (script) understanding + Tamil replies | `utils/language_detection.py`, `core/brain/prompts.py` | verified (detection + prompt policy) | `tests/test_multilingual_tamil.py` | Reply quality depends on Gemini/Groq model. Not measured. |
| Written Thanglish understanding + Thanglish replies | same | verified (detection + policy) | same | Lexicon-based detector, ~150 markers; English sentences with "open/close" are not misdetected. |
| Mid-conversation language switching | same | verified | same | Auto mode re-detects every message. |
| Technical terms/paths/code kept intact | same | verified (policy + detector ignores paths/code) | same | Enforcement is via prompt instruction to the LLM. |
| Configurable reply language | `JARVIS_RESPONSE_LANGUAGE` | verified | same | `auto`, `en`, `ta`, `thanglish`, `es`. |
| Tamil as UI/session language | `utils/jarvis_i18n.py`, `api/language_routes.py`, `index.html`, `i18n.js`, `main.js` | verified (API) / implemented (UI) | test + Quart smoke run | UI labels partially translated, rest fall back to English. |
| Tamil fixed messages no longer Spanish | 8 modules | verified | `test_tamil_mode_uses_english_fallback_messages_not_spanish` | Fixed messages use English in Tamil mode. |
| Spoken Tamil recognition (local) | faster-whisper `language="ta"` | implemented | manual | Whisper supports Tamil; accuracy on `medium` not measured here. |
| Spoken Tamil recognition (browser) | `ta-IN` SpeechRecognition | implemented | manual | Depends on WebView2/Chrome online speech service. |
| Spoken Tamil via Gemini Live | `voice/live_context.py` directive | implemented | manual | Needs `GEMINI_API_KEY` + microphone. Not verified here. |
| Spoken Thanglish recognition | — | not verified | manual | STT will produce Tamil script or English words; no Thanglish-specific model. |
| Natural spoken Tamil output (local Piper) | — | **blocked** | — | No Tamil Piper voice bundled; `/api/language` reports `local_tts_native: false`. Use Gemini Live, or set `JARVIS_TTS_MODEL_TA` to a Tamil-capable model you obtain and license-check. |
| Full-duplex voice, barge-in, reconnection | `voice/live_*` | existing | upstream tests | Unchanged. |
| Wake word | `main.js` (browser recognition regex) | partial (existing) | upstream tests | Not a local engine. No openWakeWord/Porcupine integration. |
| Push-to-talk / voice button | `main.js` | existing | upstream tests | |
| Voice profiles | `voice/identifier.py` | existing (off by default) | upstream tests | Never sufficient for authorization of sensitive actions alone. |

## Desktop control and files

| Feature | Files | Status | Test method | Notes |
| --- | --- | --- | --- | --- |
| List folder / search files in allowed roots | `tools/files.py` | verified | `tests/test_file_tools.py` | Max 200 entries / 50 results / 8 s search budget. |
| Create folder, copy (opt-in) | same | verified | same | Never overwrites. |
| Move, rename (opt-in, confirmation) | same | verified | same | Never overwrites; policy `critical`. |
| Delete (opt-in, confirmation) | same | verified (POSIX path) / implemented (Recycle Bin) | same | Windows: Recycle Bin via `SHFileOperationW`. Recycle Bin path not exercised by tests. |
| Organize folder with preview | same | verified | same | Preview tool changes nothing; apply needs confirmation. |
| Path traversal / credential protection | same | verified | same | `.env`, keys, `.ssh`, `.git` hidden and refused. |
| System info (CPU, RAM, disk, battery, uptime) | same | verified | same | Battery reported as unavailable on desktops. |
| Open Windows Settings pages | same | implemented | unknown page rejection tested | 19 allowlisted `ms-settings:` URIs. |
| Apps, volume, power, processes, windows | `tools/system.py`, `tools/desktop_control.py` | existing | upstream tests | |
| Browser automation (Playwright) | `tools/browser.py` | existing (optional dep) | upstream tests | |
| Clipboard tools | — | not started | — | |
| Duplicate finder, monitor layout, virtual desktops | — | not started | — | |
| winget package search/install | — | not started | — | |

## Agent, safety, platform

| Feature | Files | Status | Test method | Notes |
| --- | --- | --- | --- | --- |
| Emergency stop (backend) | `core/security/emergency_stop.py`, `execution.py`, `security_manager.py` | verified | `tests/test_emergency_stop.py` | Both tool gates refuse; blocked requests are not replayed. |
| Emergency stop (HTTP + live voice) | `api/security_routes.py`, `voice/live_session.py` | verified | same | Critical route; hostile origin rejected. Closes all live sessions. |
| Emergency stop (UI button, Ctrl+Shift+X) | `main.js`, `index.html`, `style.css` | implemented | `node --check` | Needs visual check in the app. |
| Planner, exactly-once execution, confirmation | `core/command_pipeline/` | existing | upstream tests | |
| Parallel DAG execution, persistent checkpoints, resume | — | not started | — | |
| Coding agent workflow | — | not started | — | Terminal tool is opt-in only. |
| Calendar / email / meeting notes | — | blocked | — | Needs official OAuth integrations; none implemented. |
| Docker / database diagnostics | — | not started | — | |
| Offline-mode detection | partial (existing provider fallback) | existing | upstream tests | |
| Setup from ZIP (voice models) | `setup.ps1` | verified | contract test + real download, SHA-256 matched upstream | |
| Upstream repo links removed | README, AGENTS, SECURITY, CODE_OF_CONDUCT, LICENSE | verified | grep | MIT notice kept, fork maintainer added. |
