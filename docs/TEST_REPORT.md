# Test Report

Environment: Windows 11 Pro, Python 3.12.10, project `venv`, branch
`feature/jarvis-ultimate`, 2026-10-26. No API keys, microphone or GPU used.

## Automated results

| Command | Result |
| --- | --- |
| `pytest -q` (untouched `main`, temp worktree) | 801 passed, 2 failed, 1 skipped, 95 errors (errors = pytest tmp dir creation in that location) |
| `pytest -q` (this branch, project folder) | **955 passed, 1 failed, 1 skipped** |
| `pytest tests\test_multilingual_tamil.py tests\test_file_tools.py tests\test_emergency_stop.py tests\test_windows_startup.py -q` | 58 passed |
| PowerShell parser on all `scripts\*.ps1` / `.psm1` | 0 errors |
| `ruff check src/backend` | All checks passed |
| `pyright` on every changed backend file (venv interpreter) | 0 errors |
| `python -m compileall -q start_app.py src\backend` | OK |
| `node --check` on `main.js`, `i18n.js`, `api.js`, `hud.js`, `live-voice.js`, `recognition-policy.js`, `voice-capabilities.js` | OK |
| `git diff --check` | No whitespace errors (CRLF notices only) |
| `setup.ps1` PowerShell parser | 0 parse errors |

Remaining failure, also failing on untouched `main`:
`tests/test_frontend_i18n.py::FrontendI18nTests::test_conversation_layout_is_not_clipped_by_center_stage`
(CSS expects `max-height: none`).

Tests changed, with reason:
- `test_installation_contract.py`: Git LFS is now optional; asserts the Piper download runs after core dependencies.
- `test_frontend_onboarding.py`: onboarding keys must appear at least in en and es; the partial Tamil table adds a third occurrence.
- `test_windows_release_packaging.py`: unchanged; README keeps the `v0.1.0-alpha.4` reference it requires.

## Recorded runs

- **Voice model recovery:** `python -m piper.download_voices en_GB-northern_english_male-medium es_MX-claude-high --download-dir models --force-redownload` downloaded both voices; SHA-256 equals the upstream LFS object IDs (`57a219ae…`, `3ef40a71…`).
- **Backend smoke (Quart test client, `JARVIS_TEST_MODE=1`):** `GET /api/status` 200; `GET /api/language` lists `ta` with `local_tts_native: false`; `POST /api/language {"language":"ta"}` 200 → `locale: ta-IN`; subsequent `GET` reports `current: ta`.

- **Login startup (real Windows, no admin):** enable/disable via shortcut and Task Scheduler; launch through the exact login command (`start-jarvis.ps1 -AutoStart`) → backend ready in 12 s, `startup.log` written; second launch refused by the script and by the `start_app.py` mutex; `stop-jarvis.ps1` stopped 4 processes; live `POST /api/security/startup` on/off OK, hostile origin → 403; live emergency stop on/off OK. Details: [STARTUP_CONFIGURATION.md](STARTUP_CONFIGURATION.md).
- **`install.ps1` health-check command:** `/api/status` → 200.

## Not run (needs hardware, credentials, or a person)

| Area | Why |
| --- | --- |
| Spoken Tamil / Thanglish / English recognition | No microphone in this session |
| Gemini Live Tamil speech output | No `GEMINI_API_KEY` used |
| Reply quality in Tamil/Thanglish | Needs a live LLM |
| Recycle Bin deletion | Would touch a real Windows shell; tests force the POSIX path |
| STOP button and Tamil labels in the desktop window | No visual session |
| Playwright browser tools | Optional dependency not installed |
| Real sign-out/sign-in auto-start | Requires signing out of your session |
| Full fresh `scripts\install.ps1` run | Would reinstall the existing venv |
| GitHub push | Rejected 403: stored credential is a different GitHub account |

## Manual acceptance checklist

1. `python start_app.py` → window opens, header shows language selector with **TA** and a red **STOP** button.
2. Type `Desktop la enna files irukku nu paaru` → JARVIS lists Desktop files (admin) and replies in Thanglish.
3. Type `உன் பெயர் என்ன?` → reply in Tamil script.
4. Type `What can you do?` in the same chat → reply switches to English.
5. Type `read src/backend/tools/files.py summary` → the path is kept verbatim.
6. Select **TA**, activate voice, say a Tamil sentence → transcript appears; with Gemini Live the spoken reply is Tamil. Record result.
7. With `JARVIS_FILE_TOOLS_ENABLED=true`: "create folder Test on Desktop" → folder exists; "delete Test" → confirmation required → after confirming, folder is in the Recycle Bin.
8. Ask to read `C:\Windows\win.ini` or `.env` → refused.
9. While JARVIS is speaking press `Ctrl+Shift+X` → audio stops, log shows emergency stop, any command reports "Emergency stop is active". Press again → actions work.
10. "Open sound settings" → Windows Settings › Sound opens.
