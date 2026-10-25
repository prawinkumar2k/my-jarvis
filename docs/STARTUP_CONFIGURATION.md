# Windows Login Startup

JARVIS can start automatically **after you sign in to Windows**. It cannot run
before Windows boots or before sign-in, and it never installs a service,
registry Run key, or anything hidden. No administrator rights are needed.

## Enable / disable

```powershell
.\scripts\enable-startup.ps1                          # Startup-folder shortcut (default)
.\scripts\enable-startup.ps1 -Method TaskScheduler    # per-user logon task, 20 s delay
.\scripts\disable-startup.ps1                         # removes both; app stays installed
.\scripts\uninstall-startup.ps1                       # stop JARVIS + disable; keeps data and .env
```

Or use the **AUTO-START** button in the JARVIS header (shortcut method).

| Method | What is created | Where to see it |
| --- | --- | --- |
| Shortcut | `JARVIS.lnk` | `shell:startup` folder; Task Manager › Startup apps |
| TaskScheduler | Task `JARVIS Assistant (user logon)`, trigger "At log on" for you only, `RunLevel Limited` | Task Scheduler Library |

Both run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "<project>\scripts\start-jarvis.ps1" -AutoStart`

## Run, stop, status

```powershell
.\scripts\start-jarvis.ps1     # starts the desktop app, waits until /api/status answers
.\scripts\stop-jarvis.ps1      # closes the window, then ends leftover JARVIS processes
.\scripts\status-jarvis.ps1    # running, backend ready, startup enabled, log folder (-Json available)
```

## Behavior

- **Single instance:** `start_app.py` holds the per-user mutex `Local\JARVIS-Desktop-Assistant`; `start-jarvis.ps1` also checks for running JARVIS processes. A second launch exits with "already running".
- **Readiness:** the script waits up to 120 s for `http://127.0.0.1:5002/api/status`.
- **Logs:** `%LOCALAPPDATA%\Jarvis\logs\startup.log` (script steps, app and backend console output).
- **Stop scope:** only `python(w).exe` processes whose command line points at this project's `start_app.py` or `jarvis_backend.py`.
- **Microphone:** stays off at startup until you activate voice in the UI.

## Verification on this machine (2026-10-26)

| Check | Result |
| --- | --- |
| Enable/disable shortcut and logon task, no admin | PASS |
| Launch through the exact login command, backend ready | PASS (12 s) |
| Second launch via script and via `start_app.py` refused | PASS |
| `stop-jarvis.ps1` stops all 4 processes | PASS |
| AUTO-START API toggle from the running app | PASS |
| Real sign-out / sign-in cycle | **NOT VERIFIED** — needs you to sign out and back in |

Manual test: run `.\scripts\enable-startup.ps1`, sign out, sign in, wait ~20 s,
then run `.\scripts\status-jarvis.ps1` (expect `running True`, `backend_ready True`).
Disable, sign out/in again, and confirm `running False`.
