"""Windows login auto-start status and toggling.

The PowerShell scripts in scripts/ are the single implementation; this module
only reads their visible artifacts (Startup-folder shortcut, logon task) and
runs them with argument arrays. Nothing here needs administrator rights.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT_DIR / "scripts"
SHORTCUT_NAME = "JARVIS.lnk"
TASK_NAME = "JARVIS Assistant (user logon)"
SCRIPT_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class StartupStatus:
    supported: bool
    enabled: bool
    shortcut: bool
    scheduled_task: bool
    shortcut_path: str

    def to_dict(self) -> dict:
        return asdict(self)


def startup_folder() -> Path:
    appdata = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _task_exists() -> bool:
    try:
        result = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", TASK_NAME],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def get_startup_status() -> StartupStatus:
    if sys.platform != "win32":
        return StartupStatus(False, False, False, False, "")
    shortcut_path = startup_folder() / SHORTCUT_NAME
    shortcut = shortcut_path.is_file()
    task = _task_exists()
    return StartupStatus(True, shortcut or task, shortcut, task, str(shortcut_path))


def _run_script(name: str, *args: str) -> tuple[bool, str]:
    script = SCRIPTS_DIR / name
    if not script.is_file():
        return False, f"{name} is missing."
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *args,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=SCRIPT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "The startup script timed out."
    except OSError:
        return False, "PowerShell is not available."
    output = (result.stdout or result.stderr or "").strip().splitlines()
    return result.returncode == 0, (output[-1] if output else "")[:300]


def set_startup_enabled(enabled: bool, method: str = "Shortcut") -> tuple[bool, str, StartupStatus]:
    if sys.platform != "win32":
        return False, "Login auto-start is only available on Windows.", get_startup_status()
    if enabled:
        if method not in {"Shortcut", "TaskScheduler"}:
            return False, "Unknown startup method.", get_startup_status()
        ok, message = _run_script("enable-startup.ps1", "-Method", method)
    else:
        ok, message = _run_script("disable-startup.ps1")
    return ok, message, get_startup_status()
