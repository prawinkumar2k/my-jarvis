"""Memory panel in a real browser against a small fake memory API (no real memories are touched)."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
from tests.ui_harness import Site, launch_browser, open_page  # noqa: E402


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


class FakeMemory:
    """Same JSON shapes as /api/security/memory*; records every request."""

    def __init__(self, facts):
        self.facts, self.private_on, self.calls, self.days = list(facts), False, [], 0

    def view(self, query=""):
        shown = [{"n": i, "text": f} for i, f in enumerate(self.facts, 1) if query.lower() in f.lower()]
        return {"facts": shown, "count": len(self.facts), "private_mode": self.private_on,
                "retention_days": self.days, "retention_choices": [0, 30, 90, 365]}

    def reply(self, route, body, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    def collection(self, route):
        request = route.request
        if request.method == "POST":
            text = json.loads(request.post_data)["text"]
            self.calls.append(("add", text))
            if "password" in text:
                return self.reply(route, {**self.view(), "ok": False, "message": "Not saved: that looks like a password."}, 409)
            self.facts.append(text)
            return self.reply(route, {**self.view(), "ok": True, "message": "saved"})
        self.calls.append(("list", parse_qs(urlparse(request.url).query).get("q", [""])[0]))
        self.reply(route, self.view(parse_qs(urlparse(request.url).query).get("q", [""])[0]))

    def action(self, name):
        def handle(route):
            request = route.request
            number = int(request.url.split("/memory/")[1].split("/")[0])
            body = json.loads(request.post_data) if request.post_data else {}
            self.calls.append((name, number, body.get("text")))
            if name == "delete":
                self.facts.pop(number - 1)
            else:
                self.facts[number - 1] = body["text"]
            self.reply(route, {**self.view(), "ok": True, "message": "ok"})
        return handle

    def private(self_, route):  # noqa: N805
        self_.private_on = json.loads(route.request.post_data)["enabled"]
        self_.calls.append(("private", self_.private_on))
        self_.reply(route, {"private_mode": self_.private_on})

    def retention(self, route):
        self.days = json.loads(route.request.post_data)["days"]
        self.calls.append(("retention", self.days))
        self.reply(route, {"removed": 0, **self.view()})

    def clear(self, route):
        self.calls.append(("clear", json.loads(route.request.post_data)))
        removed, self.facts = len(self.facts), []
        self.reply(route, {"removed": removed, **self.view()})

    def export(self, route):
        self.calls.append(("export",))
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"memories": self.facts}))

    def api(self):
        return {
            "/api/security/memory": self.collection,
            "/api/security/memory/private": self.private,
            "/api/security/memory/clear": self.clear,
            "/api/security/memory/retention": self.retention,
            "/api/security/memory/export": self.export,
            **{f"/api/security/memory/{n}/{name}": self.action(name) for n in range(1, 6) for name in ("delete", "edit")},
        }


def panel(browser, base_url, facts=("Likes tea", "Project: my-jarvis")):
    fake = FakeMemory(facts)
    page = open_page(browser, base_url, api=fake.api())
    page.wait_for_function("document.getElementById('mem-count').textContent !== '0' || document.querySelector('#mem-list .control-empty')", timeout=20000)
    return page, fake


def js_click(page, selector):
    # The panel sits inside the (collapsed) diagnostics side panel; DOM clicks drive it directly.
    page.evaluate("s => document.querySelector(s).click()", selector)


def test_lists_memories_and_filters_on_the_backend(browser, base_url):
    page, fake = panel(browser, base_url)
    assert page.inner_text("#mem-count") == "2"
    assert page.locator("#mem-list .mem-text").all_inner_texts() == ["Likes tea", "Project: my-jarvis"]
    page.evaluate("const s = document.getElementById('mem-search'); s.value = 'jarvis'; s.dispatchEvent(new Event('input', {bubbles: true}))")
    page.wait_for_function("document.querySelectorAll('#mem-list .mem-text').length === 1")
    assert ("list", "jarvis") in fake.calls and page.inner_text("#mem-count") == "2"  # total stays, list is filtered


def test_add_saves_and_refuses_secrets_with_the_reason(browser, base_url):
    page, fake = panel(browser, base_url)
    page.evaluate("document.getElementById('mem-new').value = 'Favourite editor: VS Code'")
    js_click(page, "#mem-add")
    page.wait_for_function("document.querySelectorAll('#mem-list .mem-text').length === 3")
    assert page.input_value("#mem-new") == "" and ("add", "Favourite editor: VS Code") in fake.calls
    page.evaluate("document.getElementById('mem-new').value = 'my password is hunter2'")
    js_click(page, "#mem-add")
    page.wait_for_function("document.getElementById('mem-status').textContent.includes('password')")
    assert page.input_value("#mem-new") == "my password is hunter2"  # kept so the user can fix it
    assert page.locator("#mem-list .mem-text").count() == 3


def test_edit_and_forget_one_memory(browser, base_url):
    page, fake = panel(browser, base_url)
    page.evaluate("document.querySelector('#mem-list .mem-item .mem-btn').click()")  # Edit on the first row
    page.wait_for_selector("#mem-list input.mem-input", state="attached")
    page.evaluate("document.querySelector('#mem-list input.mem-input').value = 'Likes green tea'")
    page.evaluate("document.querySelectorAll('#mem-list .mem-item .mem-btn')[0].click()")  # Save
    page.wait_for_function("document.querySelector('#mem-list .mem-text').textContent === 'Likes green tea'")
    assert ("edit", 1, "Likes green tea") in fake.calls
    page.evaluate("document.querySelectorAll('#mem-list .mem-item')[1].querySelector('.mem-btn-danger').click()")
    page.wait_for_function("document.querySelectorAll('#mem-list .mem-text').length === 1")
    assert ("delete", 2, None) in fake.calls


def test_private_mode_toggle_reaches_the_backend(browser, base_url):
    page, fake = panel(browser, base_url)
    js_click(page, "#mem-private")
    page.wait_for_function("document.getElementById('mem-status').textContent.includes('ON')")
    assert ("private", True) in fake.calls and fake.private_on is True


def test_retention_choice_is_listed_and_saved(browser, base_url):
    page, fake = panel(browser, base_url)
    assert page.locator("#mem-retention option").count() == 4 and page.input_value("#mem-retention") == "0"
    page.evaluate("const s = document.getElementById('mem-retention'); s.value = '90'; s.dispatchEvent(new Event('change', {bubbles: true}))")
    page.wait_for_function("document.getElementById('mem-status').textContent.includes('Saved')")
    assert ("retention", 90) in fake.calls and page.input_value("#mem-retention") == "90"


def test_forget_all_needs_a_second_click_and_the_exact_phrase_is_sent(browser, base_url):
    page, fake = panel(browser, base_url)
    js_click(page, "#mem-clear")
    page.wait_for_timeout(300)
    assert not [c for c in fake.calls if c[0] == "clear"]  # one click only arms it
    assert "again" in page.inner_text("#mem-clear").lower()
    js_click(page, "#mem-clear")
    page.wait_for_function("document.querySelectorAll('#mem-list .mem-text').length === 0")
    assert ("clear", {"confirm": "DELETE ALL"}) in fake.calls and page.inner_text("#mem-count") == "0"


def test_export_downloads_the_file(browser, base_url):
    page, fake = panel(browser, base_url)
    with page.expect_download(timeout=15000) as download:
        js_click(page, "#mem-export")
    assert download.value.suggested_filename == "jarvis-memory.json"
    assert ("export",) in fake.calls


def test_memory_text_cannot_inject_html(browser, base_url):
    evil = "<img src=x onerror=window.__pwned=1>"
    page, _ = panel(browser, base_url, facts=(evil,))
    assert page.locator("#mem-list .mem-text").inner_text() == evil
    assert page.locator("#mem-list img").count() == 0 and page.evaluate("window.__pwned") is None
