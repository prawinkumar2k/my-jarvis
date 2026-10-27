"""Routines panel in a real browser against a fake routines API."""

from __future__ import annotations

import json

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
from tests.ui_harness import Site, launch_browser, open_page  # noqa: E402

TOOLS = ["resumen_del_dia", "estado_jarvis", "diagnostico_sistema"]


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as playwright:
        instance = launch_browser(playwright)
        if instance is None:
            pytest.skip("Edge or Chrome is required for browser tests")
        yield instance
        instance.close()


@pytest.fixture(scope="module")
def base_url():
    with Site() as url:
        yield url


def routine(**kw):
    base = {"id": "r1", "name": "Morning summary", "time": "08:00", "repeat": "daily", "tool": "resumen_del_dia",
            "enabled": True, "args": {}, "next_run": "2026-10-28T08:00:00", "last_run": ""}
    base.update(kw)
    return base


class Fake:
    def __init__(self, routines=(), results=()):
        self.routines, self.results, self.calls = list(routines), list(results), []

    def view(self):
        return {"routines": self.routines, "results": self.results, "tools": TOOLS}

    def send(self, route, body, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    def collection(self, route):
        request = route.request
        if request.method == "POST":
            body = json.loads(request.post_data)
            self.calls.append(("add", body))
            if body["tool"] == "instalar_programa":
                return self.send(route, {"error": "'instalar_programa' needs your approval each time, so it cannot run on its own."}, 400)
            self.routines.append(routine(id="r2", name=body["name"], time=body["time"], repeat=body["repeat"], tool=body["tool"]))
            return self.send(route, {**self.view(), "routine": self.routines[-1]}, 201)
        self.send(route, self.view())

    def action(self, name):
        def handle(route):
            self.calls.append((name,))
            if name == "delete":
                self.routines.clear()
            else:
                self.results.append({"id": "r1", "name": "Morning summary", "tool": "resumen_del_dia", "ok": True,
                                     "text": "It is 8 AM. Battery 80 percent.", "at": "2026-10-27T14:00:00", "missed": False})
            self.send(route, self.view())
        return handle

    def api(self):
        return {"/api/security/routines": self.collection, "/api/security/routines/r1/delete": self.action("delete"),
                "/api/security/routines/r1/run": self.action("run")}


def open_panel(browser, base_url, fake):
    page = open_page(browser, base_url, api=fake.api())
    page.wait_for_function("document.getElementById('rt-tool').options.length > 0", timeout=20000)
    return page


def click(page, selector):
    page.evaluate("s => document.querySelector(s).click()", selector)


def test_shows_routines_with_next_run_and_the_default_form_is_a_daily_summary(browser, base_url):
    page = open_panel(browser, base_url, Fake([routine()]))
    text = page.inner_text("#rt-list")
    assert "Morning summary" in text and "resumen_del_dia" in text and "2026-10-28 08:00" in text
    assert page.inner_text("#rt-count") == "1"
    assert page.input_value("#rt-name") == "Daily summary" and page.input_value("#rt-time") == "08:00"
    assert page.locator("#rt-tool option").all_inner_texts() == TOOLS


def test_one_click_adds_the_daily_summary(browser, base_url):
    fake = Fake()
    page = open_panel(browser, base_url, fake)
    assert "No routines yet" in page.inner_text("#rt-list")
    click(page, "#rt-add")
    page.wait_for_function("document.querySelectorAll('#rt-list .mem-item').length === 1")
    assert fake.calls == [("add", {"name": "Daily summary", "time": "08:00", "repeat": "daily", "tool": "resumen_del_dia"})]


def test_run_now_shows_the_latest_result_and_delete_removes(browser, base_url):
    fake = Fake([routine()])
    page = open_panel(browser, base_url, fake)
    page.evaluate("document.querySelector('#rt-list .mem-btn').click()")  # Run now
    page.wait_for_function("document.querySelectorAll('#rt-last li').length === 1")
    assert "Battery 80 percent" in page.inner_text("#rt-last") and ("run",) in fake.calls
    page.evaluate("document.querySelector('#rt-list .mem-btn-danger').click()")
    page.wait_for_function("document.querySelectorAll('#rt-list .mem-item').length === 0")
    assert ("delete",) in fake.calls


def test_the_reason_is_shown_when_the_backend_refuses(browser, base_url):
    fake = Fake()
    page = open_panel(browser, base_url, fake)
    page.evaluate("const s = document.getElementById('rt-tool'); const o = document.createElement('option'); o.value = 'instalar_programa'; o.text = 'x'; s.add(o); s.value = 'instalar_programa'")
    click(page, "#rt-add")
    page.wait_for_function("document.getElementById('rt-status').textContent.includes('needs your approval')")
    assert page.locator("#rt-list .mem-item").count() == 0


def test_routine_names_cannot_inject_html(browser, base_url):
    evil = "<img src=x onerror=window.__pwned=1>"
    page = open_panel(browser, base_url, Fake([routine(name=evil)]))
    assert evil in page.inner_text("#rt-list")
    assert page.locator("#rt-list img").count() == 0 and page.evaluate("window.__pwned") is None


def test_setup_check_lists_statuses_and_fixes_and_runs_one_check_at_a_time(browser, base_url):
    calls = []
    report = {"checks": [
        {"id": "ai", "label": "AI provider", "status": "ok", "detail": "cloud first: gemini -> groq", "fix": ""},
        {"id": "ffmpeg", "label": "FFmpeg", "status": "missing", "detail": "Not found.", "fix": "winget install Gyan.FFmpeg"},
        {"id": "x", "label": "<img src=x onerror=window.__pwned=1>", "status": "warn", "detail": "<b>d</b>", "fix": ""}],
        "summary": {"ok": 1, "warn": 1, "missing": 1}, "ready": False}

    def handler(route):
        calls.append(1)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(report))

    page = open_page(browser, base_url, api={"/api/security/setup-check": handler})
    page.evaluate("for (let i = 0; i < 3; i++) document.getElementById('sc-run').click()")  # a nervous triple click
    page.wait_for_function("document.querySelectorAll('#sc-list .sc-item').length === 3")
    text = page.inner_text("#sc-list")
    assert "Missing · FFmpeg" in text and "Fix: winget install Gyan.FFmpeg" in text
    assert page.inner_text("#sc-summary") == "1 working, 1 to look at, 1 missing"
    assert len(calls) == 1
    assert page.locator("#sc-list img, #sc-list b").count() == 0 and page.evaluate("window.__pwned") is None
