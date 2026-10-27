"""Memory panel API: list/search, add, edit, forget, export, private mode (kept), guarded clear-all.

The memory store is a fake (as in test_companion_memory.py); the HTTP layer, the rules about secrets and
private mode, and the cognitive-graph cleanup call are the real code.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from core import privacy
from tools import memory as memory_tools

ORIGIN = {"Origin": "http://localhost:5002"}


@pytest.fixture
def store(monkeypatch, tmp_path):
    data: dict[str, str] = {"facts": "- Likes tea\n- Project: my-jarvis"}
    forgotten: list[str] = []

    class FakeManager:
        def get_profile_data(self, _pid):
            return {"facts": data["facts"]}

        def set_facts(self, _pid, value):
            data["facts"] = value

    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    monkeypatch.setattr(memory_tools, "memory_manager", FakeManager())
    monkeypatch.setattr(memory_tools, "guardar_memoria_perfiles", lambda: None)
    monkeypatch.setattr(memory_tools, "_forget_cognitive_copy", lambda _pid, fact: forgotten.append(fact))
    monkeypatch.setattr("modules.memory.service.unified_memory.save_cognitive_memory", lambda **_k: None, raising=False)
    monkeypatch.setattr(privacy, "_state_file", lambda: tmp_path / "private_mode.json")
    privacy.set_private_mode(False)
    yield data, forgotten
    privacy.set_private_mode(False)


def call(method, path, body=None):
    import jarvis_backend

    async def run():
        client = jarvis_backend.app.test_client()
        response = await getattr(client, method)(path, headers=ORIGIN, **({"json": body} if body is not None else {}))
        text = await response.get_data(as_text=True)
        return response.status_code, response.headers, (json.loads(text) if text and text.lstrip().startswith(("{", "[")) else text)

    return asyncio.run(run())


def test_list_and_search(store):
    status, _, body = call("get", "/api/security/memory")
    assert status == 200 and body["count"] == 2 and [f["text"] for f in body["facts"]] == ["Likes tea", "Project: my-jarvis"]
    _, _, found = call("get", "/api/security/memory?q=JARVIS")
    assert [f["n"] for f in found["facts"]] == [2] and found["count"] == 2


def test_add_edit_and_forget_with_graph_cleanup(store):
    data, forgotten = store
    status, _, body = call("post", "/api/security/memory", {"text": "Favourite editor: VS Code"})
    assert status == 200 and body["ok"] and body["count"] == 3
    status, _, body = call("post", "/api/security/memory/1/edit", {"text": "Likes green tea"})
    assert status == 200 and body["ok"] and "Likes green tea" in data["facts"] and "Likes tea" in forgotten
    status, _, body = call("post", "/api/security/memory/2/delete")
    assert status == 200 and body["ok"] and "my-jarvis" not in data["facts"] and "Project: my-jarvis" in forgotten


@pytest.mark.parametrize("secret", ["my password is hunter2", "card 4111 1111 1111 1111", "otp code 123456"])
def test_secrets_are_refused_and_nothing_is_stored(store, secret):
    data, _ = store
    before = data["facts"]
    status, _, body = call("post", "/api/security/memory", {"text": secret})
    assert status == 409 and body["ok"] is False and data["facts"] == before


def test_bad_input_and_unknown_numbers_change_nothing(store):
    data, _ = store
    before = data["facts"]
    assert call("post", "/api/security/memory", {"text": "   "})[0] == 400
    assert call("post", "/api/security/memory", {"text": "x" * 501})[0] == 400
    assert call("post", "/api/security/memory/9/delete")[0] == 409
    assert call("post", "/api/security/memory/1/edit", {})[0] == 400
    assert call("post", "/api/security/memory/1/explode")[0] == 400
    assert data["facts"] == before


def test_private_mode_blocks_new_memories_and_is_kept(store, tmp_path):
    data, _ = store
    assert call("post", "/api/security/memory/private", {"enabled": "yes"})[0] == 400
    status, _, body = call("post", "/api/security/memory/private", {"enabled": True})
    assert status == 200 and body["private_mode"] is True
    status, _, body = call("post", "/api/security/memory", {"text": "Likes jazz"})
    assert status == 409 and "Private mode" in body["message"] and "jazz" not in data["facts"]
    assert json.loads((tmp_path / "private_mode.json").read_text())["enabled"] is True  # survives a restart
    assert call("get", "/api/security/memory")[2]["private_mode"] is True


def test_export_is_a_download_with_only_memories(store):
    status, headers, body = call("get", "/api/security/memory/export")
    assert status == 200 and "attachment" in headers["Content-Disposition"]
    assert body["memories"] == ["Likes tea", "Project: my-jarvis"] and body["count"] == 2


def test_clear_all_needs_the_exact_confirmation_phrase(store):
    data, forgotten = store
    assert call("post", "/api/security/memory/clear", {})[0] == 400
    assert call("post", "/api/security/memory/clear", {"confirm": "yes"})[0] == 400
    assert "Likes tea" in data["facts"]
    status, _, body = call("post", "/api/security/memory/clear", {"confirm": "DELETE ALL"})
    assert status == 200 and body["removed"] == 2 and body["count"] == 0
    assert data["facts"] == "" and set(forgotten) == {"Likes tea", "Project: my-jarvis"}


def test_hostile_origin_is_refused(store):
    import jarvis_backend

    async def run():
        client = jarvis_backend.app.test_client()
        return (await client.get("/api/security/memory", headers={"Origin": "https://evil.example"})).status_code

    assert asyncio.run(run()) == 403
