"""Assistant surface in a real browser: suggestions, status bar, approval card, automation settings.

Real: the page and its JavaScript. Faked: backend answers (tests/ui_harness.py). The status bar tests
check that only supplied data is shown and that missing data is labelled unavailable.
"""

from __future__ import annotations

import json

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


def task(**overrides):
    base = {
        "id": "abc123", "goal": "evening cleanup", "state": "approval_required", "active": False, "error": "",
        "started": "", "finished": "", "plan_approved": False,
        "approval": {"scope": "plan", "steps": [
            {"idx": 1, "summary": "instalar_programa(id_paquete=Gyan.FFmpeg)"},
            {"idx": 2, "summary": "mover_archivo(origen=a.txt, destino=b)"}]},
        "steps": [
            {"idx": 0, "tool": "diagnostico_sistema", "args": {}, "state": "completed", "attempts": 1, "error": ""},
            {"idx": 1, "tool": "instalar_programa", "args": {"id_paquete": "Gyan.FFmpeg"}, "state": "approval_required", "attempts": 0, "error": ""},
            {"idx": 2, "tool": "mover_archivo", "args": {"origen": "a.txt"}, "state": "pending", "attempts": 0, "error": ""},
        ],
    }
    base.update(overrides)
    return base


ROUTE = {
    "mode": "cloud_first", "local_only": False, "configured": True, "ready": True,
    "chain": [{"role": "primary", "provider": "gemini", "model": "gemini-2.5-flash"},
              {"role": "backup", "provider": "gemini", "model": "gemini-3.1-flash-lite"},
              {"role": "fallback", "provider": "groq", "model": "openai/gpt-oss-120b"},
              {"role": "fallback", "provider": "ollama", "model": "qwen2.5:3b"}],
    "last_answer": {"provider": "gemini", "model": "gemini-3.1-flash-lite", "role": "primary"},
}
PREFS = {"preferences": {"auto_low_risk": True, "ask_once_per_task": True, "always_confirm": ["browser"]},
         "categories": ["install", "file_changes", "delete", "browser", "desktop_control", "clipboard", "plans"],
         "active_approvals": [{"category": "install", "key": "x", "seconds_left": 300}]}


def requests(page):
    return page.evaluate("window.__chat.requests.map(r => r.message)")


# ── welcome and suggestions ──────────────────────────────────────────────────
def test_empty_state_welcomes_and_a_suggestion_runs_a_real_command(browser, base_url):
    page = open_page(browser, base_url)
    assert page.is_visible(".welcome-title")
    chips = page.locator(".suggestion-chip")
    assert chips.count() >= 5
    page.click(".suggestion-chip[data-command='open chrome']")
    page.wait_for_function("document.body.innerText.includes('Reply to: open chrome')", timeout=8000)
    assert requests(page) == ["open chrome"]
    assert not page.is_visible(".welcome-title")  # the welcome card steps aside once the conversation starts


# ── status bar ───────────────────────────────────────────────────────────────
def test_status_bar_shows_the_real_ai_route_and_who_answered(browser, base_url):
    page = open_page(browser, base_url, api={"/api/security/ai-route": ROUTE})
    page.wait_for_function("document.getElementById('sb-ai-text').textContent.includes('gemini-3.1-flash-lite')", timeout=8000)
    assert page.inner_text("#sb-ai-text") == "gemini · gemini-3.1-flash-lite"
    title = page.get_attribute("#sb-ai", "title")
    assert "backup: gemini gemini-3.1-flash-lite" in title and "fallback: ollama qwen2.5:3b" in title
    assert page.get_attribute("#sb-ai", "data-state") == "ok"
    assert page.inner_text("#sb-mode-text") == "cloud first"


def test_status_bar_never_invents_data_when_the_backend_is_unavailable(browser, base_url):
    page = open_page(browser, base_url, api={"/api/security/ai-route": lambda r: r.fulfill(status=500, body="down")})
    page.wait_for_function("document.getElementById('sb-ai-text').textContent === 'unavailable'", timeout=8000)
    assert page.get_attribute("#sb-ai", "data-state") == "unknown"
    assert "gemini" not in page.inner_text("#status-bar").lower()


def test_local_only_mode_is_visible(browser, base_url):
    route = {**ROUTE, "mode": "local_only", "local_only": True, "last_answer": {}}
    page = open_page(browser, base_url, api={"/api/security/ai-route": route})
    page.wait_for_function("document.getElementById('sb-mode-text').textContent.includes('local only')", timeout=8000)
    assert page.get_attribute("#sb-mode", "data-state") == "local"
    assert page.inner_text("#sb-ai-text") == "gemini · gemini-2.5-flash"  # configured primary, nothing answered yet


def test_task_chip_counts_only_open_tasks(browser, base_url):
    tasks = {"tasks": [task(), task(id="done1", state="completed", approval=None), task(id="x2", state="failed", approval=None)]}
    page = open_page(browser, base_url, api={"/api/security/tasks": tasks})
    page.wait_for_function("document.getElementById('sb-tasks-text').textContent === '1'", timeout=8000)
    assert page.get_attribute("#sb-tasks", "data-state") == "warn"  # one is waiting for approval


# ── approval card ────────────────────────────────────────────────────────────
def approval_page(browser, base_url, posts, tasks=None):
    def capture(route):
        posts.append(route.request.url.rsplit("/api/security/tasks/", 1)[-1])
        route.fulfill(status=202, content_type="application/json", body=json.dumps({"task": task()}))

    api = {"/api/security/tasks": {"tasks": tasks if tasks is not None else [task()]},
           "/api/security/tasks/abc123/approve": capture, "/api/security/tasks/abc123/reject": capture}
    page = open_page(browser, base_url, api=api)
    return page


def test_approval_card_lists_exactly_what_one_yes_covers(browser, base_url):
    page = approval_page(browser, base_url, [])
    page.wait_for_selector("#approval-card:not(.hidden)", timeout=8000)
    text = page.inner_text("#approval-card")
    assert "evening cleanup" in text and "2 step" in text
    assert "instalar_programa(id_paquete=Gyan.FFmpeg)" in text and "mover_archivo(origen=a.txt, destino=b)" in text
    assert "diagnostico_sistema" not in text  # the already-finished harmless step is not part of the question
    assert page.get_attribute("#approval-card", "role") == "alertdialog"
    assert "seri" in text  # tells the user they can answer by voice or chat


def test_approve_button_answers_once_even_if_clicked_repeatedly(browser, base_url):
    posts: list[str] = []
    page = approval_page(browser, base_url, posts)
    page.wait_for_selector("#approval-card:not(.hidden)", timeout=8000)
    # Three clicks in the same instant (a nervous double-click): only the first may be sent.
    page.evaluate("for (let i = 0; i < 3; i++) document.getElementById('approval-approve').click()")
    page.wait_for_timeout(800)
    assert posts == ["abc123/approve"]


def test_reject_button_rejects(browser, base_url):
    posts: list[str] = []
    page = approval_page(browser, base_url, posts)
    page.wait_for_selector("#approval-card:not(.hidden)", timeout=8000)
    page.click("#approval-reject")
    page.wait_for_timeout(500)
    assert posts == ["abc123/reject"]


def test_no_card_when_nothing_is_waiting_and_a_running_task_is_not_asked_twice(browser, base_url):
    page = approval_page(browser, base_url, [], tasks=[task(state="completed", approval=None), task(id="r1", active=True)])
    page.wait_for_timeout(1500)
    assert page.is_hidden("#approval-card")


def test_task_text_cannot_inject_html_into_the_card(browser, base_url):
    evil = "<img src=x onerror=window.__pwned=1>"
    page = approval_page(browser, base_url, [], tasks=[task(goal=evil)])
    page.wait_for_selector("#approval-card:not(.hidden)", timeout=8000)
    assert evil in page.inner_text("#approval-card")
    assert page.locator("#approval-card img").count() == 0
    assert page.evaluate("window.__pwned") is None


def test_a_single_step_approval_explains_it_is_separate(browser, base_url):
    single = task(approval={"scope": "step", "steps": [{"idx": 3, "summary": "controlar_pc(accion=apagar)"}]})
    page = approval_page(browser, base_url, [], tasks=[single])
    page.wait_for_selector("#approval-card:not(.hidden)", timeout=8000)
    assert "own confirmation" in page.inner_text("#approval-card")


# ── automation settings ──────────────────────────────────────────────────────
def test_automation_settings_show_saved_values_and_save_changes(browser, base_url):
    saved: list[dict] = []

    def prefs(route):
        if route.request.method == "POST":
            saved.append(json.loads(route.request.post_data))
            body = {**PREFS, "preferences": {**PREFS["preferences"], **saved[-1]}}
        else:
            body = PREFS
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page = open_page(browser, base_url, api={"/api/security/automation": prefs})
    page.wait_for_selector("#auto-always input", state="attached", timeout=8000)
    assert page.is_checked("#auto-low-risk") and page.is_checked("#auto-once")
    assert page.is_checked("#auto-always input[value='browser']")
    assert not page.is_checked("#auto-always input[value='install']")
    assert "install" in page.inner_text("#auto-approvals").lower()  # the remembered approval is listed

    page.evaluate("document.getElementById('auto-always').querySelector(\"input[value='install']\").click()")
    page.wait_for_timeout(600)
    assert saved and sorted(saved[-1]["always_confirm"]) == ["browser", "install"]
    page.evaluate("document.getElementById('auto-low-risk').click()")
    page.wait_for_timeout(600)
    assert saved[-1]["auto_low_risk"] is False


def test_forget_approvals_calls_the_backend(browser, base_url):
    calls: list[str] = []
    api = {"/api/security/automation": PREFS,
           "/api/security/automation/revoke": lambda r: (calls.append("revoke"), r.fulfill(status=200, content_type="application/json", body='{"revoked": 1}'))}
    page = open_page(browser, base_url, api=api)
    page.wait_for_selector("#auto-revoke", state="attached")
    page.evaluate("document.getElementById('auto-revoke').click()")
    page.wait_for_timeout(500)
    assert calls == ["revoke"]


# ── layout ───────────────────────────────────────────────────────────────────
def test_conversation_is_the_main_area_and_nothing_overflows(browser, base_url):
    page = open_page(browser, base_url)
    box = page.locator("#conversation-panel").bounding_box()
    assert box["height"] >= 0.30 * 950 and box["width"] >= 700  # was ~30% of the height and 760 px max
    composer = page.locator("#command-form").bounding_box()
    assert composer["y"] + composer["height"] <= 950
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.evaluate("getComputedStyle(document.body, '::before').display") == "none"  # no CRT scanline overlay


def test_the_default_desktop_window_size_keeps_everything_reachable(browser, base_url):
    # The desktop app opens at 1366x768 (minimum 1024x768), with an approval waiting.
    for size in ({"width": 1366, "height": 768}, {"width": 1024, "height": 768}):
        page = open_page(browser, base_url, viewport=size, api={"/api/security/tasks": {"tasks": [task()]}})
        page.wait_for_selector("#approval-card:not(.hidden)", timeout=8000)
        for selector in ("#command-input", "#command-submit", "#approval-approve", "#approval-reject"):
            box = page.locator(selector).bounding_box()
            assert box and 0 <= box["x"] and box["x"] + box["width"] <= size["width"], (size, selector, box)
            assert 0 <= box["y"] and box["y"] + box["height"] <= size["height"], (size, selector, box)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.context.close()


def test_a_long_conversation_scrolls_inside_the_panel_and_keeps_the_composer_visible(browser, base_url):
    page = open_page(browser, base_url)
    for i in range(12):
        page.fill("#command-input", f"message number {i} " + "text " * 40)
        page.keyboard.press("Enter")
        page.wait_for_function(f"document.body.innerText.includes('Reply to: message number {i} ')", timeout=8000)
    page.wait_for_timeout(300)
    assert page.evaluate("(() => { const c = document.getElementById('conversation-segments'); return c.scrollHeight > c.clientHeight && "
                         "Math.abs(c.scrollTop + c.clientHeight - c.scrollHeight) < 4; })()")
    composer = page.locator("#command-form").bounding_box()
    assert composer["y"] + composer["height"] <= 950 and composer["y"] > 400


# ── voice starts by itself (setting voice_autostart, on by default) ─────────────────────────────
# Only the WebSocket and the permission query are stubbed: no microphone is touched.
SPY = """
window.__ws = []; window.__gum = 0;
window.WebSocket = function (url) { window.__ws.push(String(url)); throw new Error('stubbed'); };
const realGum = navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
if (navigator.mediaDevices) navigator.mediaDevices.getUserMedia = async () => { window.__gum += 1; throw new Error('stubbed'); };
"""
LIVE_STATUS = {"capabilities": {"live_voice": {"state": "available"}}}


def permission(state):
    return f"navigator.permissions.query = async () => ({{ state: '{state}' }});"


def voice_page(browser, base_url, *, perm="granted", prefs=None, route=None):
    api = {"/api/status": LIVE_STATUS,
           "/api/security/automation": {**PREFS, "preferences": {**PREFS["preferences"], **(prefs or {})}},
           "/api/security/ai-route": route or ROUTE}
    return open_page(browser, base_url, api=api, scripts=(SPY, permission(perm)))


def test_voice_opens_on_its_own_when_the_microphone_is_already_allowed(browser, base_url):
    page = voice_page(browser, base_url)
    page.wait_for_function("window.__ws.length > 0", timeout=60000)
    assert any("/api/voice/stream" in url for url in page.evaluate("window.__ws"))


def test_voice_never_triggers_a_microphone_prompt_by_itself(browser, base_url):
    page = voice_page(browser, base_url, perm="prompt")
    page.wait_for_function("document.getElementById('command-notice').textContent.length > 0", timeout=60000)
    assert "Activate voice" in page.inner_text("#command-notice")  # says what to do once
    page.wait_for_timeout(1500)
    assert page.evaluate("window.__ws.length") == 0 and page.evaluate("window.__gum") == 0


def test_voice_autostart_can_be_switched_off(browser, base_url):
    page = voice_page(browser, base_url, prefs={"voice_autostart": False})
    page.wait_for_timeout(4000)
    assert page.evaluate("window.__ws.length") == 0 and page.evaluate("window.__gum") == 0
    assert page.inner_text("#command-notice") == ""  # an opt-out is silent, not an error
    assert not page.is_checked("#auto-voice")


def test_local_only_mode_never_opens_the_cloud_voice_stream(browser, base_url):
    page = voice_page(browser, base_url, route={**ROUTE, "mode": "local_only", "local_only": True})
    page.wait_for_timeout(5000)
    assert page.evaluate("window.__ws.length") == 0  # no stream to Google; local listening only
