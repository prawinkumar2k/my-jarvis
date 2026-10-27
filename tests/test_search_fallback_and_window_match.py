"""Keyless web search via Gemini grounding (mocked HTTP) and spoken window-name matching."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest
from tools import search
from tools.desktop_control import _find_window

GROUNDED = {
    "candidates": [{
        "content": {"parts": [{"text": "It is 32 C in Chennai."}]},
        "groundingMetadata": {"groundingChunks": [{"web": {"title": "weather.com"}}, {"web": {"title": "weather.com"}}]},
    }]
}


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def gemini_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_AI_MODE", raising=False)
    monkeypatch.delenv("JARVIS_GEMINI_MODEL", raising=False)
    monkeypatch.setattr(search, "_buscar_en_tavily", lambda _q: "")
    monkeypatch.setattr("core.jarvis_config.BRAVE_API_KEY", "", raising=False)


def test_search_uses_gemini_grounding_when_no_search_key(monkeypatch, gemini_env):
    calls = []

    def urlopen(request, timeout):
        calls.append((request.full_url, request.headers.get("X-goog-api-key"), json.loads(request.data)["tools"]))
        return Response(json.dumps(GROUNDED).encode())

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    result = search._buscar_en_internet_impl("chennai weather")
    assert result == "It is 32 C in Chennai.\nSources: weather.com"
    assert "gemini-2.5-flash:generateContent" in calls[0][0]
    assert calls[0][1] == "test-key" and calls[0][2] == [{"google_search": {}}]
    assert "test-key" not in calls[0][0]  # key in a header, never in the URL


def test_quota_on_main_model_falls_back_to_backup_model(monkeypatch, gemini_env):
    urls = []

    def urlopen(request, timeout):
        urls.append(request.full_url)
        if "2.5-flash" in request.full_url:
            raise urllib.error.HTTPError(request.full_url, 429, "quota", {}, None)
        return Response(json.dumps(GROUNDED).encode())

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    assert search._buscar_en_internet_impl("q").startswith("It is 32 C")
    assert "gemini-3.1-flash-lite" in urls[1]


def test_local_only_mode_never_sends_the_query(monkeypatch, gemini_env):
    monkeypatch.setenv("JARVIS_AI_MODE", "local_only")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("must not call the cloud"))
    assert "local-only" in search._buscar_en_internet_impl("q")


def test_honest_message_when_nothing_works(monkeypatch, gemini_env):
    def urlopen(request, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    assert search._buscar_en_internet_impl("q").startswith("I could not search the web")


WINDOWS = [{"handle": 1, "title": "JARVIS-master - Antigravity IDE", "pid": 1},
           {"handle": 2, "title": "Untitled - Notepad", "pid": 2}]


@pytest.mark.parametrize(("spoken", "handle"), [("Anti Gravity", 1), ("antigravity", 1), ("note pad", 2), ("2", 2)])
def test_spoken_window_names_match(spoken, handle):
    assert _find_window(spoken, WINDOWS)["handle"] == handle


def test_too_short_or_unknown_names_do_not_match():
    assert _find_window("x y", WINDOWS) is None
    assert _find_window("Photoshop", WINDOWS) is None
