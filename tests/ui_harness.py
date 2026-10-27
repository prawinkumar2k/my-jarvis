"""Standalone harness for browser tests of the real JARVIS page.

The page is rendered from the real template and served with the real static
files on a free port. The backend is NOT started: every /api request is
answered by Playwright (default: an empty JSON object) and /api/chat* by a
controllable fake installed in the page, so tests exercise the real front-end
code (keyboard handlers, fetch, SSE parsing, state machine) without touching
a running JARVIS or any AI provider.
"""

from __future__ import annotations

import http.server
import json
import mimetypes
import re
import threading
from pathlib import Path

import jinja2
from playwright import sync_api

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src" / "frontend" / "templates"
STATIC = ROOT / "src" / "frontend" / "static"
MEDIA = ROOT / "media"

# Replaces window.fetch for /api/chat and /api/chat/stream only. Modes:
#   auto   answer immediately            manual  hold until finish()/fail() is called
#   fail   HTTP 500 immediately
CHAT_FAKE = r"""
(() => {
  const realFetch = window.fetch.bind(window);
  const state = window.__chat = { mode: 'auto', requests: [], pending: [], aborted: 0, reply: (m) => 'Reply to: ' + m };
  const isChat = (url) => /\/api\/chat(\/stream)?$/.test(new URL(url, location.href).pathname);
  const build = (entry, text) => {
    if (entry.stream) {
      const done = { type: 'done', response: text, text, should_listen: false, outcome: state.outcome || 'succeeded', receipts: state.receipts || [] };
      const body = 'data: ' + JSON.stringify({ type: 'status', text: 'thinking' }) + '\n\n' + 'data: ' + JSON.stringify(done) + '\n\n';
      return new Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' } });
    }
    return new Response(JSON.stringify({ ok: true, response: text, outcome: 'succeeded' }), { status: 200, headers: { 'content-type': 'application/json' } });
  };
  state.finish = (index, text) => { const e = state.pending[index]; if (e && !e.done) { e.done = true; e.resolve(build(e, text ?? state.reply(e.message))); } };
  state.fail = (index) => { const e = state.pending[index]; if (e && !e.done) { e.done = true; e.resolve(new Response('boom', { status: 500 })); } };
  window.fetch = (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    if (!isChat(url)) return realFetch(input, init);
    const message = JSON.parse(init.body || '{}').message;
    const entry = { message, stream: /stream$/.test(new URL(url, location.href).pathname), done: false };
    state.requests.push({ path: new URL(url, location.href).pathname, message });
    return new Promise((resolve, reject) => {
      entry.resolve = resolve;
      const signal = init.signal;
      if (signal) {
        const abort = () => { if (!entry.done) { entry.done = true; state.aborted += 1; reject(signal.reason || new DOMException('Aborted', 'AbortError')); } };
        if (signal.aborted) abort(); else signal.addEventListener('abort', abort, { once: true });
      }
      state.pending.push(entry);
      const index = state.pending.length - 1;
      if (state.mode === 'auto') state.finish(index);
      else if (state.mode === 'fail') state.fail(index);
    });
  };
})();
"""


def _render_index() -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATES)), autoescape=True)
    env.globals["url_for"] = lambda endpoint, **kw: f"/{endpoint}/{kw['filename']}"
    return env.get_template("index.html").render()


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):  # keep test output clean
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - http.server API
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self._send(200, _render_index().encode("utf-8"), "text/html; charset=utf-8")
        for prefix, base in (("/static/", STATIC), ("/media/", MEDIA)):
            if path.startswith(prefix):
                target = (base / path[len(prefix):]).resolve()
                if base.resolve() in target.parents and target.is_file():
                    kind = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                    return self._send(200, target.read_bytes(), kind)
        return self._send(404, b"{}", "application/json")


class Site:
    """Context manager: serves the page and returns its base URL."""

    def __enter__(self) -> str:
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __exit__(self, *_exc) -> None:
        self.server.shutdown()
        self.server.server_close()


def open_page(browser, base_url: str, *, chat_mode: str = "auto", api: dict | None = None, viewport: dict | None = None,
              scripts: tuple[str, ...] = ()):
    """New page with API mocks installed and the boot splash dismissed.

    api maps an API path suffix (e.g. "/api/security/tasks") to the JSON body to return, or to a
    callable taking the Playwright route. More specific entries win over the empty-object default.
    """
    # The page enforces script-src self; Playwright polls with eval, so bypass CSP for the test driver only.
    context = browser.new_context(viewport=viewport or {"width": 1500, "height": 950}, bypass_csp=True)
    page = context.new_page()
    page.add_init_script(CHAT_FAKE)
    # The boot animation advances by Math.random(); a constant makes it finish quickly and predictably.
    page.add_init_script("Math.random = () => 0.9999;")
    for script in scripts:
        page.add_init_script(script)
    page.add_init_script(f"window.__chat.mode = {json.dumps(chat_mode)};")
    # Google Fonts and other external hosts are blocked: tests must not depend on (or wait for) the internet.
    page.route(lambda url: not url.startswith(base_url), lambda route: route.abort())
    page.route(re.compile(r".*/api/.*"), lambda route: route.fulfill(status=200, content_type="application/json", body="{}"))
    page.route(re.compile(r".*/api/tts.*"), lambda route: route.fulfill(status=503, body="tts off"))
    # A normal session: an AI key is configured, so the first-run panel is not in the way.
    configured = json.dumps({"capabilities": {"llm": {"state": "available"}}, "items": {"language": {"configured": True}}})
    page.route(re.compile(r".*/api/setup/status.*"),
               lambda route: route.fulfill(status=200, content_type="application/json", body=configured))
    def json_handler(payload):
        text = json.dumps(payload)

        def handle(route):  # one parameter: Playwright passes (route, request) to two-parameter handlers
            route.fulfill(status=200, content_type="application/json", body=text)

        return handle

    for suffix, body in (api or {}).items():
        page.route(re.compile(r".*" + re.escape(suffix) + r"(\?.*)?$"), body if callable(body) else json_handler(body))
    page.goto(base_url + "/", wait_until="domcontentloaded")
    page.wait_for_selector("#command-input", state="attached")
    page.wait_for_timeout(1500)
    # "Click screen to initialise" splash. On a slow load the click can land before the page's script has
    # attached its handler, so click again until the app is up (the app ignores repeat clicks once booting).
    for _ in range(45):
        page.mouse.click(700, 450)
        try:
            page.wait_for_function("document.getElementById('loader').classList.contains('hidden')", timeout=2000)
            break
        except sync_api.TimeoutError:
            continue
    else:
        raise AssertionError("the page did not finish booting")
    page.wait_for_timeout(300)
    return page


def launch_browser(playwright):
    """Installed Edge or Chrome (no download). Returns None when neither starts."""
    for channel in ("msedge", "chrome"):
        try:
            return playwright.chromium.launch(channel=channel, headless=True)
        except Exception:
            continue
    return None
