# Installation on Windows

## Prerequisites

| Requirement | Install |
| --- | --- |
| Windows 10/11 | — |
| Python 3.11 or 3.12 (3.13+ is rejected) | `winget install Python.Python.3.12` |
| FFmpeg (required by setup) | `winget install Gyan.FFmpeg` |
| WebView2 Runtime (desktop shell) | Preinstalled on Windows 11 |
| Internet on first setup | Downloads Python packages and, for ZIP installs, ~126 MB of Piper voices |
| Gemini or Groq API key | <https://aistudio.google.com/apikey> or <https://console.groq.com/keys> |

Git LFS is **not** required. If the voice models are missing or are LFS pointer
files and the folder has no git remote, setup downloads the same voices from
the official Piper voice repository.

## Install

One step (setup + `.env` + health check + optional login startup):

```powershell
.\scripts\install.ps1            # login auto-start and "Hey Jarvis" are on by default
```

Or step by step:

```powershell
cd C:\path\to\JARVIS
.\setup.ps1              # core
.\setup.ps1 -Dev         # + pytest, ruff, pyright
.\setup.ps1 -Dev -Full   # + RAG, Playwright, voice biometrics, Telegram, pycaw
```

If PowerShell blocks the script: `powershell -ExecutionPolicy Bypass -File .\setup.ps1`
(or double-click `Install-JARVIS.bat`).

## Configure

```powershell
Copy-Item .env.example .env
notepad .env
```

Set at least `GEMINI_API_KEY` or `GROQ_API_KEY`. Never put keys in source files.
See [CONFIGURATION.md](CONFIGURATION.md) for Tamil, file tools and safety settings.

## Login startup

See [STARTUP_CONFIGURATION.md](STARTUP_CONFIGURATION.md): `.\scripts\enable-startup.ps1`, `.\scripts\disable-startup.ps1`, or the AUTO-START button.

## Run and stop

`.\scripts\start-jarvis.ps1`, `.\scripts\stop-jarvis.ps1`, `.\scripts\status-jarvis.ps1`, or:

```powershell
python start_app.py                      # desktop window (re-runs inside venv)
python src\backend\jarvis_backend.py     # backend only → http://localhost:5002
```

Stop: close the window, or press `Ctrl+C` in the terminal. To halt actions
without closing, press **STOP** in the header or `Ctrl+Shift+X`.

## Verify

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Expected on this branch: `955 passed, 1 skipped, 1 failed` — the failure is the
pre-existing CSS assertion listed in [TEST_REPORT.md](TEST_REPORT.md).

## Uninstall

```powershell
.\scripts\uninstall-startup.ps1      # stops JARVIS, removes startup entries
Remove-Item -Recurse .\venv          # optional: remove the Python environment
```

Your data (`%LOCALAPPDATA%\Jarvis`) and `.env` are kept until you delete them.

## Playwright browser automation (optional)

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-optional.txt
.\venv\Scripts\python.exe -m playwright install chromium
```
