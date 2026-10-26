"""Browser launch fallback, local URLs, short errors, and emergency-stop hooks (no real browser)."""

from __future__ import annotations

import pytest
from core.security import emergency_stop
from tools import browser, winget


class FakeChromium:
    def __init__(self, available):
        self.available, self.tried = available, []

    def launch(self, **options):
        channel = options.get("channel", "")
        self.tried.append(channel)
        if channel not in self.available:
            raise RuntimeError("Executable doesn't exist")
        return f"browser:{channel or 'chromium'}"


class FakePW:
    def __init__(self, available):
        self.chromium = FakeChromium(available)


def test_installed_edge_is_used_when_bundled_chromium_is_missing(monkeypatch):
    monkeypatch.delenv("JARVIS_BROWSER_CHANNEL", raising=False)
    pw = FakePW({"msedge"})
    assert browser._launch_browser(pw) == ("browser:msedge", "msedge")
    assert pw.chromium.tried == ["", "msedge"]


def test_no_browser_gives_one_clear_error(monkeypatch):
    monkeypatch.delenv("JARVIS_BROWSER_CHANNEL", raising=False)
    with pytest.raises(RuntimeError, match="No browser could be started"):
        browser._launch_browser(FakePW(set()))


def test_channel_can_be_pinned(monkeypatch):
    monkeypatch.setenv("JARVIS_BROWSER_CHANNEL", "chrome")
    pw = FakePW({"chrome", "msedge"})
    assert browser._launch_browser(pw)[1] == "chrome" and pw.chromium.tried == ["chrome"]


@pytest.mark.parametrize("url", ["http://127.0.0.1:8765/index.html", "http://localhost:3000/app", "http://[::1]:8080/"])
def test_local_pages_open_instead_of_becoming_a_web_search(url):
    assert browser._normalizar_destino_web(url) == url


def test_public_and_unclear_destinations_keep_existing_behaviour():
    assert browser._normalizar_destino_web("example.org") == "https://example.org"
    assert browser._normalizar_destino_web("weather in chennai").startswith("https://www.google.com/search?q=")


def test_missing_element_error_is_short_and_plain():
    error = RuntimeError("Locator.click: Timeout 8000ms exceeded.\nCall log:\n  - waiting for locator('#x')")
    assert browser._short_browser_error("click", "#x", error) == "Could not click: nothing matching '#x' was found on the page."


def test_emergency_stop_runs_browser_and_winget_hooks(monkeypatch):
    calls = []
    monkeypatch.setattr(winget, "cancel_install", lambda: calls.append("winget") or "")
    monkeypatch.setattr(browser, "_close_browser_for_emergency_stop", lambda: calls.append("browser"))
    emergency_stop.register_cancel_hook("winget_install", winget.cancel_install)
    emergency_stop.register_cancel_hook("browser_automation", browser._close_browser_for_emergency_stop)
    try:
        emergency_stop.engage("test")
        assert {"winget", "browser"} <= set(calls)
    finally:
        emergency_stop.release()
