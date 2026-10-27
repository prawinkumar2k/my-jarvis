"""Message composer behaviour in a real browser (Edge/Chrome via Playwright).

Real: the page, its JavaScript, keyboard events, fetch and SSE parsing, the
send/stop state machine. Faked: the backend (see tests/ui_harness.py), so these
tests prove the front-end contract, not the AI. Skipped when no browser exists.
"""

from __future__ import annotations

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


def requests(page):
    return page.evaluate("window.__chat.requests.map(r => r.message)")


def send(page, text, how="enter"):
    page.click("#command-input")
    page.fill("#command-input", text)
    page.keyboard.press("Enter") if how == "enter" else page.click("#command-submit")


def wait_idle(page):
    page.wait_for_function("document.getElementById('command-status').dataset.state !== 'processing'", timeout=8000)


def test_enter_sends_exactly_once_and_shows_the_reply(browser, base_url):
    page = open_page(browser, base_url)
    send(page, "hello jarvis")
    page.wait_for_function("document.body.innerText.includes('Reply to: hello jarvis')", timeout=8000)
    assert requests(page) == ["hello jarvis"]
    assert page.input_value("#command-input") == ""
    assert page.evaluate("document.activeElement.id") == "command-input"  # keyboard stays usable


def test_send_button_behaves_like_enter(browser, base_url):
    page = open_page(browser, base_url)
    send(page, "via button", how="click")
    page.wait_for_function("document.body.innerText.includes('Reply to: via button')", timeout=8000)
    assert requests(page) == ["via button"]


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_empty_messages_are_not_sent(browser, base_url, text):
    page = open_page(browser, base_url)
    page.click("#command-input")
    page.evaluate("t => { const i = document.getElementById('command-input'); i.value = t; }", text)
    page.keyboard.press("Enter")
    page.click("#command-submit")
    page.wait_for_timeout(400)
    assert requests(page) == []


def test_shift_enter_adds_a_newline_and_does_not_send(browser, base_url):
    page = open_page(browser, base_url)
    page.click("#command-input")
    page.keyboard.type("line one")
    page.keyboard.press("Shift+Enter")
    page.keyboard.type("line two")
    page.wait_for_timeout(300)
    assert requests(page) == []
    assert page.input_value("#command-input") == "line one\nline two"
    page.keyboard.press("Enter")
    page.wait_for_function("window.__chat.requests.length === 1", timeout=5000)
    assert requests(page) == ["line one\nline two"]


def test_enter_while_composing_text_does_not_send(browser, base_url):
    page = open_page(browser, base_url)
    page.fill("#command-input", "vanakkam")
    page.evaluate(
        "document.getElementById('command-input').dispatchEvent("
        "new KeyboardEvent('keydown', {key: 'Enter', isComposing: true, keyCode: 229, bubbles: true, cancelable: true}))"
    )
    page.wait_for_timeout(400)
    assert requests(page) == []  # Tamil/CJK keyboards press Enter to accept a word, not to send


def test_rapid_repeated_enter_sends_one_request(browser, base_url):
    page = open_page(browser, base_url, chat_mode="manual")
    page.click("#command-input")
    page.fill("#command-input", "only once")
    for _ in range(4):
        page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    assert requests(page) == ["only once"]


def test_enter_while_busy_is_never_silent_and_keeps_the_new_text(browser, base_url):
    page = open_page(browser, base_url, chat_mode="manual")
    send(page, "first")
    page.wait_for_function("window.__chat.requests.length === 1")
    page.click("#command-input")
    page.fill("#command-input", "second")
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    assert requests(page) == ["first"]
    assert page.input_value("#command-input") == "second"  # not lost, not sent
    notice = page.inner_text("#command-notice").strip()
    assert notice, "the UI must say why nothing was sent"
    assert page.get_attribute("#command-submit", "data-mode") == "stop"
    page.evaluate("window.__chat.finish(0, 'done first')")
    page.wait_for_function("document.body.innerText.includes('done first')", timeout=5000)
    page.keyboard.press("Enter")  # now idle: the kept text sends
    page.wait_for_function("window.__chat.requests.length === 2", timeout=5000)
    assert requests(page) == ["first", "second"]


def test_progress_is_visible_while_a_request_runs(browser, base_url):
    page = open_page(browser, base_url, chat_mode="manual")
    send(page, "slow job")
    page.wait_for_function("document.getElementById('command-status').dataset.state === 'processing'")
    assert page.get_attribute("#command-input", "aria-busy") == "true"
    page.wait_for_function("/\\d+\\s?s/.test(document.getElementById('command-status').textContent)", timeout=6000)


def test_stop_cancels_the_request_and_allows_a_new_one(browser, base_url):
    page = open_page(browser, base_url, chat_mode="manual")
    send(page, "long task")
    page.wait_for_function("window.__chat.requests.length === 1")
    page.click("#command-submit")  # the Send button is STOP while busy
    page.wait_for_function("window.__chat.aborted === 1", timeout=5000)
    wait_idle(page)
    assert page.input_value("#command-input") == "long task"  # text preserved for editing/retry
    assert page.get_attribute("#command-submit", "data-mode") != "stop"
    assert requests(page) == ["long task"]  # cancelling must not resend through the fallback path
    page.evaluate("window.__chat.mode = 'auto'")
    page.keyboard.press("Enter")
    page.wait_for_function("document.body.innerText.includes('Reply to: long task')", timeout=8000)


def test_escape_also_cancels(browser, base_url):
    page = open_page(browser, base_url, chat_mode="manual")
    send(page, "cancel me")
    page.wait_for_function("window.__chat.requests.length === 1")
    page.keyboard.press("Escape")
    page.wait_for_function("window.__chat.aborted === 1", timeout=5000)


def test_failure_keeps_text_offers_retry_and_never_double_sends(browser, base_url):
    page = open_page(browser, base_url, chat_mode="fail")
    send(page, "will break")
    wait_idle(page)
    page.wait_for_function("document.getElementById('command-status').dataset.state === 'error'", timeout=8000)
    assert page.input_value("#command-input") == "will break"
    assert page.is_visible("#command-retry-text")
    # One failed stream may fall back to the classic endpoint only if the stream never started; either way
    # a single user action must not create more than one request per endpoint.
    paths = page.evaluate("window.__chat.requests.map(r => r.path)")
    assert paths.count("/api/chat/stream") == 1 and paths.count("/api/chat") <= 1
    page.evaluate("window.__chat.mode = 'auto'; window.__chat.requests.length = 0; window.__chat.pending.length = 0")
    page.click("#command-retry-text")
    page.wait_for_function("document.body.innerText.includes('Reply to: will break')", timeout=8000)
    assert requests(page) == ["will break"]
    assert not page.is_visible("#command-retry-text")


def test_a_request_for_approval_is_a_question_not_an_error(browser, base_url):
    page = open_page(browser, base_url)
    # The real pipeline reports outcome "failed" plus a confirmation receipt when a tool needs a yes.
    page.evaluate("""window.__chat.outcome = 'failed';
        window.__chat.receipts = [{ tool_name: 'instalar_programa', status: 'blocked', diagnostic_code: 'tool_confirmation_required' }];
        window.__chat.reply = () => 'Install VLC [VideoLAN.VLC]? One yes covers the rest of this task.'""")
    send(page, "install vlc")
    page.wait_for_function("document.body.innerText.includes('Install VLC')", timeout=8000)
    wait_idle(page)
    assert page.get_attribute("#command-status", "data-state") == "confirmation"
    assert not page.is_visible("#command-failed")          # no red banner
    assert not page.is_visible("#command-retry-text")      # nothing to retry
    assert page.input_value("#command-input") == ""        # the request is not put back in the box
    assert "seri" in page.inner_text("#command-notice")    # tells the user how to answer
    assert requests(page) == ["install vlc"]
    page.keyboard.type("seri")                             # the answer is an ordinary message
    page.keyboard.press("Enter")
    page.wait_for_function("window.__chat.requests.length === 2", timeout=5000)
    assert requests(page) == ["install vlc", "seri"]


def test_composer_is_focused_after_start_and_typing_anywhere_reaches_it(browser, base_url):
    page = open_page(browser, base_url)
    assert page.evaluate("document.activeElement.id") == "command-input"
    page.evaluate("document.activeElement.blur()")
    page.keyboard.type("abc")
    assert page.input_value("#command-input").endswith("abc")


def test_composer_stays_on_screen_with_a_long_message(browser, base_url):
    page = open_page(browser, base_url)
    page.click("#command-input")
    page.fill("#command-input", "word " * 120)
    box = page.locator("#command-submit").bounding_box()
    assert box and 0 <= box["y"] and box["y"] + box["height"] <= 950
    assert box["x"] + box["width"] <= 1500
