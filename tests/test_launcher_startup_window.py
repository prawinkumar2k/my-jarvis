"""Launcher start-up: window first, real UI when the core is ready, no hidden backend on failure.
Fake webview and fake backend process (nothing is launched)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from core import desktop_session


class _Exit(Exception):
    pass


class LoadedEvent:
    def __init__(self, fires):
        self.fires, self.waits = list(fires), 0

    def wait(self, _timeout):
        self.waits += 1
        return self.fires.pop(0) if self.fires else False

    def clear(self):
        pass


class FakeWindow:
    def __init__(self, loads=(True,)):
        self.events = SimpleNamespace(closed=None, loaded=LoadedEvent(loads))
        self.loaded = []
        self.shown = 0

    def show(self):
        self.shown += 1

    def load_url(self, url):
        self.loaded.append(("url", url))

    def load_html(self, html):
        self.loaded.append(("html", html))


class Closed:
    def __init__(self):
        self.handler = None

    def __iadd__(self, handler):
        self.handler = handler
        return self


class FakeProc:
    def __init__(self, exit_code=None):
        self.pid, self.returncode, self._exit = 4321, None, exit_code

    def poll(self):
        if self._exit is not None:
            self.returncode = self._exit
        return self.returncode


def _run(monkeypatch, tmp_path, *, ready_after, proc, loads=(True,), opened=None):
    import start_app

    window = FakeWindow(loads)
    monkeypatch.setattr("webbrowser.open", (opened if opened is not None else []).append)
    window.events.closed = Closed()
    created = {}
    clock = {"t": 0.0}
    session = desktop_session.DesktopSession(
        origin="http://localhost:5002", webview_storage_dir=str(tmp_path), session_file=str(tmp_path / "s.json"),
        persist_permissions=False, cleanup_dir=None)
    monkeypatch.setattr(desktop_session, "load_desktop_session", lambda **_k: session)
    checks = {"n": 0}

    def running(_url):
        checks["n"] += 1
        return ready_after is not None and checks["n"] > ready_after

    monkeypatch.setattr(start_app, "is_backend_running", running)
    monkeypatch.setattr(start_app.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(start_app.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(start_app.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    monkeypatch.setattr(start_app, "start_backend_watchdog", lambda *a, **k: None)
    monkeypatch.setenv("JARVIS_BACKEND_START_TIMEOUT", "60")
    stopped = []
    monkeypatch.setattr(start_app, "stop_process_tree", stopped.append)

    def create(title, url, **kwargs):
        created.update(url=url, html=kwargs.get("html"))
        return window

    def start(func=None, **_kwargs):
        func()
        window.events.closed.handler()

    monkeypatch.setattr(start_app.webview, "create_window", create)
    monkeypatch.setattr(start_app.webview, "start", start)
    monkeypatch.setattr(start_app.os, "_exit", lambda _c: (_ for _ in ()).throw(_Exit()))
    with pytest.raises(_Exit):
        start_app.start_app()
    _run.window = window
    return created, window.loaded, stopped


def test_window_opens_with_starting_page_then_loads_the_ui(monkeypatch, tmp_path):
    created, loaded, _ = _run(monkeypatch, tmp_path, ready_after=5, proc=FakeProc())
    assert created["url"] is None and "STARTING J.A.R.V.I.S." in created["html"]
    assert loaded == [("url", "http://localhost:5002")]


def test_slow_core_is_stopped_completely_and_the_window_says_so(monkeypatch, tmp_path):
    proc = FakeProc()
    _, loaded, stopped = _run(monkeypatch, tmp_path, ready_after=None, proc=proc)
    assert loaded[0][0] == "html" and "did not start within 1 minutes" in loaded[0][1]
    assert proc in stopped  # whole process tree, so no invisible backend keeps running


def test_core_that_crashes_is_reported(monkeypatch, tmp_path):
    _, loaded, _ = _run(monkeypatch, tmp_path, ready_after=None, proc=FakeProc(exit_code=3))
    assert loaded[0][0] == "html" and "code 3" in loaded[0][1]


def test_start_timeout_default_and_bounds(monkeypatch):
    import start_app

    monkeypatch.delenv("JARVIS_BACKEND_START_TIMEOUT", raising=False)
    assert start_app.backend_start_timeout() == 300
    monkeypatch.setenv("JARVIS_BACKEND_START_TIMEOUT", "5")
    assert start_app.backend_start_timeout() == 30
    monkeypatch.setenv("JARVIS_BACKEND_START_TIMEOUT", "junk")
    assert start_app.backend_start_timeout() == 300


def test_blank_window_is_retried_then_opened_in_the_browser(monkeypatch, tmp_path):
    opened = []
    # WebView2 never finishes loading: retry once, then use the normal browser.
    _, loaded, _ = _run(monkeypatch, tmp_path, ready_after=0, proc=None, loads=(False, False), opened=opened)
    assert loaded == [("url", "http://localhost:5002")]  # one reload attempt
    assert _run.window.shown >= 1
    assert opened == ["http://localhost:5002"]


def test_retry_that_works_does_not_open_a_browser(monkeypatch, tmp_path):
    opened = []
    _run(monkeypatch, tmp_path, ready_after=0, proc=None, loads=(False, True), opened=opened)
    assert opened == []
