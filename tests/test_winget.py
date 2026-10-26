"""winget integration with a fake winget process (no real package is searched or installed here)."""

from __future__ import annotations

import subprocess
import threading

import pytest
from tools import winget

SEARCH_OUTPUT = (
    "Name                 Id                     Version  Match         Source\n"
    "-----------------------------------------------------------------------------\n"
    "VLC media player     VideoLAN.VLC           3.0.24   Moniker: vlc  winget\n"
    "Jellyfin VLC Bridge  CrySer66.JellyfinVlc…  1.18.0   Tag: vlc      winget\n"
)
SHOW_VLC = (
    "Found VLC media player [VideoLAN.VLC]\n"
    "Version: 3.0.24\n"
    "Publisher: VideoLAN\n"
    "License: GPL-2.0\n"
    "Installer:\n"
    "  Installer Type: nullsoft\n"
)


class Proc:
    def __init__(self, stdout="", code=0):
        self.stdout, self.returncode = stdout, code


@pytest.fixture
def fake(monkeypatch):
    calls, state = [], {"installed": False}

    def run(args, timeout):
        calls.append(args)
        if args[0] == "search":
            return Proc(SEARCH_OUTPUT)
        if args[0] == "show":
            return Proc(SHOW_VLC) if args[2] == "VideoLAN.VLC" else Proc("No package found matching input criteria.", 1)
        if args[0] == "list":
            if state["installed"]:
                return Proc("VLC media player VideoLAN.VLC 3.0.24")
            return Proc("No installed package found matching input criteria.", 1)
        raise AssertionError(args)

    monkeypatch.setattr(winget, "_run", run)
    monkeypatch.setattr(winget, "winget_path", lambda: "winget.exe")
    return calls, state


def test_search_parses_table_layout_and_drops_truncated_ids(fake):
    calls, _ = fake
    results = winget.search("vlc")
    assert results == [{"name": "VLC media player", "id": "VideoLAN.VLC", "version": "3.0.24", "source": "winget"}]
    assert calls[0][:3] == ["search", "--query", "vlc"] and "--source" in calls[0]


@pytest.mark.parametrize("query", ["", "--help", "x" * 81, "vlc\nrm"])
def test_search_rejects_option_like_or_control_text(fake, query):
    with pytest.raises(winget.WingetError):
        winget.search(query)


@pytest.mark.parametrize("bad", ["", "VideoLAN.VLC --override x", "a;b", "../x", "-x"])
def test_invalid_ids_never_reach_winget(fake, bad):
    calls, _ = fake
    assert "Package check failed" in winget.describe_for_confirmation({"id_paquete": bad})
    assert calls == []


def test_confirmation_shows_exact_identity(fake):
    text = winget.describe_for_confirmation({"id_paquete": "VideoLAN.VLC"})
    assert "VideoLAN.VLC" in text and "publisher VideoLAN" in text and "source winget" in text and "GPL-2.0" in text


def test_install_runs_user_scope_and_verifies(fake, monkeypatch):
    _, state = fake
    launched = []

    class Popen:
        def __init__(self, args, **kwargs):
            launched.append((args, kwargs))
            self.returncode = None

        def communicate(self, timeout):
            state["installed"], self.returncode = True, 0
            return "Successfully installed", None

        def poll(self):
            return self.returncode

    monkeypatch.setattr(subprocess, "Popen", Popen)
    result = winget.install("VideoLAN.VLC")
    args, kwargs = launched[0]
    assert args[1:5] == ["install", "--id", "VideoLAN.VLC", "--exact"]
    assert args[args.index("--scope") + 1] == "user" and args[args.index("--source") + 1] == "winget"
    assert kwargs["shell"] is False
    assert "exit code 0" in result and "Verified" in result


def test_already_installed_is_not_reinstalled(fake, monkeypatch):
    _, state = fake
    state["installed"] = True
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("must not install"))
    assert "already installed" in winget.install("VideoLAN.VLC")


def test_machine_scope_only_package_is_reported_not_elevated(fake, monkeypatch):
    class Popen:
        returncode = None

        def __init__(self, *a, **k):
            pass

        def communicate(self, timeout):
            self.returncode = 0x8A150010
            return "No applicable installer found; see logs for more details.", None

    monkeypatch.setattr(subprocess, "Popen", Popen)
    result = winget.install("VideoLAN.VLC")
    assert "administrator" in result and "did not do" in result


def test_unknown_package_is_refused(fake):
    assert "No package with the exact id" in winget.install("Fake.Package")


def test_second_install_while_one_runs_is_refused_and_cancel_works(fake, monkeypatch):
    started, release = threading.Event(), threading.Event()

    class Popen:
        returncode = None

        def __init__(self, *a, **k):
            pass

        def communicate(self, timeout):
            started.set()
            release.wait(5)
            self.returncode = 1
            return "", None

        def poll(self):
            return self.returncode

        def terminate(self):
            release.set()

    monkeypatch.setattr(subprocess, "Popen", Popen)
    results = []
    worker = threading.Thread(target=lambda: results.append(winget.install("VideoLAN.VLC")))
    worker.start()
    assert started.wait(5)
    assert "already running" in winget.install("VideoLAN.VLC")
    assert "Stopping the install" in winget.cancel_install()
    worker.join(5)
    assert "cancelled" in results[0]
    assert winget.cancel_install() == "No install is running."


def test_install_needs_confirmation_and_preview_names_the_package(fake):
    from core.security.confirmation_preview import preview
    from core.security.tool_policy import get_tool_policy

    assert get_tool_policy("instalar_programa").requires_confirmation
    assert get_tool_policy("leer_portapapeles").requires_confirmation
    assert not get_tool_policy("buscar_programa").requires_confirmation
    assert "VideoLAN.VLC" in preview("instalar_programa", {"id_paquete": "VideoLAN.VLC"})
    assert "cloud" in preview("leer_portapapeles", {})


def test_confirmation_message_in_the_tool_pipeline_names_the_package(fake):
    from core.brain.tool_manager import _blocked_error
    from core.command_pipeline.execution import ToolConfirmationRequiredError

    error = _blocked_error("La herramienta requiere confirmacion explicita.", "instalar_programa", {"id_paquete": "VideoLAN.VLC"})
    assert isinstance(error, ToolConfirmationRequiredError)
    message = error.user_message("en")
    assert "VideoLAN.VLC" in message and "publisher VideoLAN" in message
