from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from core import startup_manager

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REQUIRED_SCRIPTS = (
    "install.ps1",
    "enable-startup.ps1",
    "disable-startup.ps1",
    "uninstall-startup.ps1",
    "start-jarvis.ps1",
    "stop-jarvis.ps1",
    "status-jarvis.ps1",
    "JarvisCommon.psm1",
)


def test_all_startup_scripts_exist():
    for name in REQUIRED_SCRIPTS:
        assert (SCRIPTS / name).is_file(), name


def test_scripts_never_require_admin_or_hide_persistence():
    text = "\n".join((SCRIPTS / name).read_text(encoding="utf-8") for name in REQUIRED_SCRIPTS)
    assert "RunLevel Highest" not in text
    assert "New-Service" not in text
    assert "CurrentVersion\\Run" not in text  # no hidden registry Run keys
    assert "-Verb RunAs" not in text
    assert "RunLevel Limited" in text


def test_disable_removes_only_jarvis_artifacts():
    text = (SCRIPTS / "disable-startup.ps1").read_text(encoding="utf-8")
    assert "Get-JarvisStartupShortcutPath" in text
    assert "Unregister-ScheduledTask -TaskName (Get-JarvisTaskName)" in text
    assert "Remove-Item -LiteralPath $shortcut" in text
    common = (SCRIPTS / "JarvisCommon.psm1").read_text(encoding="utf-8")
    assert '$script:ShortcutName = "JARVIS.lnk"' in common
    assert f'$script:TaskName = "{startup_manager.TASK_NAME}"' in common


def test_stop_script_only_targets_this_checkout():
    common = (SCRIPTS / "JarvisCommon.psm1").read_text(encoding="utf-8")
    assert "start_app.py" in common and "jarvis_backend.py" in common
    assert "$lower.Contains($root)" in common


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell parser check runs on Windows")
def test_powershell_scripts_parse():
    files = ",".join(f"'{(SCRIPTS / name)}'" for name in REQUIRED_SCRIPTS)
    command = (
        f"$bad=0; foreach($f in @({files})){{$t=$null;$e=$null;"
        "[void][System.Management.Automation.Language.Parser]::ParseFile($f,[ref]$t,[ref]$e);"
        "$bad+=$e.Count}; $bad"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.stdout.strip().splitlines()[-1] == "0"


def test_status_reports_shortcut(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(startup_manager.sys, "platform", "win32")
    monkeypatch.setattr(startup_manager, "startup_folder", lambda: tmp_path)
    monkeypatch.setattr(startup_manager, "_task_exists", lambda: False)
    assert startup_manager.get_startup_status().enabled is False
    (tmp_path / "JARVIS.lnk").write_bytes(b"lnk")
    status = startup_manager.get_startup_status()
    assert status.enabled is True and status.shortcut is True and status.scheduled_task is False


def test_toggle_runs_scripts_with_argument_arrays(monkeypatch, tmp_path: Path):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert kwargs.get("timeout") == startup_manager.SCRIPT_TIMEOUT_SECONDS
        assert "shell" not in kwargs
        return subprocess.CompletedProcess(command, 0, stdout="Login startup enabled\n", stderr="")

    monkeypatch.setattr(startup_manager.sys, "platform", "win32")
    monkeypatch.setattr(startup_manager.subprocess, "run", fake_run)
    monkeypatch.setattr(startup_manager, "startup_folder", lambda: tmp_path)
    monkeypatch.setattr(startup_manager, "_task_exists", lambda: False)

    ok, message, _ = startup_manager.set_startup_enabled(True, "TaskScheduler")
    assert ok is True and message == "Login startup enabled"
    assert calls[-1][-3:] == [str(SCRIPTS / "enable-startup.ps1"), "-Method", "TaskScheduler"]

    startup_manager.set_startup_enabled(False)
    assert calls[-1][-1] == str(SCRIPTS / "disable-startup.ps1")


def test_toggle_rejects_unknown_method(monkeypatch):
    monkeypatch.setattr(startup_manager.sys, "platform", "win32")
    monkeypatch.setattr(startup_manager, "_task_exists", lambda: False)
    ok, message, _ = startup_manager.set_startup_enabled(True, "Registry; calc.exe")
    assert ok is False and "Unknown" in message


def test_not_supported_off_windows(monkeypatch):
    monkeypatch.setattr(startup_manager.sys, "platform", "linux")
    assert startup_manager.get_startup_status().supported is False
    ok, _, _ = startup_manager.set_startup_enabled(True)
    assert ok is False


@pytest.mark.skipif(sys.platform != "win32", reason="Named mutex is Windows-only")
def test_second_desktop_instance_is_refused():
    probe = (
        "import importlib.util,os;os.environ['JARVIS_SKIP_VENV_REEXEC']='1';"
        f"s=importlib.util.spec_from_file_location('sa',r'{ROOT / 'start_app.py'}');"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        "m._INSTANCE_MUTEX_NAME=r'Local\\JARVIS-Test-Instance';"
        "first=m.acquire_single_instance();import subprocess,sys;"
        "inner=\"import ctypes;k=ctypes.WinDLL('kernel32',use_last_error=True);k.CreateMutexW.restype=ctypes.c_void_p;"
        "h=k.CreateMutexW(None,False,r'Local\\\\JARVIS-Test-Instance');print(ctypes.get_last_error())\";"
        "r=subprocess.run([sys.executable,'-c',inner],capture_output=True,text=True);"
        "print(first, r.stdout.strip())"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=60, check=False)
    assert result.stdout.strip() == "True 183", result.stderr[-400:]
