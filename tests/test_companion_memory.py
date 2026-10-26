from __future__ import annotations

import pytest
from core import capability_catalog, privacy
from core.brain import prompts
from tools import memory as memory_tools


@pytest.fixture
def facts(monkeypatch):
    store: dict[str, str] = {"facts": ""}

    class FakeManager:
        def get_profile_data(self, _pid):
            return {"facts": store["facts"]}

        def set_facts(self, _pid, value):
            store["facts"] = value

    forgotten: list[str] = []
    monkeypatch.setattr(memory_tools, "memory_manager", FakeManager())
    monkeypatch.setattr(memory_tools, "guardar_memoria_perfiles", lambda: None)
    monkeypatch.setattr(memory_tools, "_forget_cognitive_copy", lambda _pid, fact: forgotten.append(fact))
    privacy.set_private_mode(False)
    yield store, forgotten
    privacy.set_private_mode(False)


def test_save_list_edit_forget_cycle(facts, monkeypatch):
    store, forgotten = facts
    monkeypatch.setattr("modules.memory.service.unified_memory.save_cognitive_memory", lambda **_k: None, raising=False)
    assert "guardado" in memory_tools.guardar_dato_memoria.invoke({"dato": "Favourite editor: VS Code"})
    assert "guardado" in memory_tools.guardar_dato_memoria.invoke({"dato": "Project: my-jarvis"})
    listing = memory_tools.ver_memorias.invoke({})
    assert "1. Favourite editor: VS Code" in listing and "2. Project: my-jarvis" in listing

    result = memory_tools.editar_memoria.invoke({"numero_o_texto": "1", "nuevo_texto": "Favourite editor: Neovim"})
    assert "Neovim" in result
    assert "Favourite editor: VS Code" in forgotten
    assert "Neovim" in store["facts"] and "VS Code" not in store["facts"]

    assert "Forgotten" in memory_tools.olvidar_memoria.invoke({"numero_o_texto": "jarvis"})
    assert "my-jarvis" not in store["facts"]
    assert "Project: my-jarvis" in forgotten
    assert "No saved memories" not in memory_tools.ver_memorias.invoke({})


def test_ambiguous_or_missing_reference_changes_nothing(facts):
    store, _ = facts
    store["facts"] = "- Likes tea\n- Likes coffee"
    assert "exactly one" in memory_tools.olvidar_memoria.invoke({"numero_o_texto": "likes"})
    assert "exactly one" in memory_tools.olvidar_memoria.invoke({"numero_o_texto": "9"})
    assert store["facts"] == "- Likes tea\n- Likes coffee"


@pytest.mark.parametrize(
    "secret",
    [
        "my password is hunter2",
        "gemini key AIzaSyA1234567890abcdefghijklmnopqrstu",
        "card 4111 1111 1111 1111",
        "OTP code 482913",
        "-----BEGIN RSA PRIVATE KEY-----",
    ],
)
def test_secrets_are_never_saved(facts, secret):
    store, _ = facts
    assert "Not saved" in memory_tools.guardar_dato_memoria.invoke({"dato": secret})
    assert store["facts"] == ""
    assert memory_tools.extraer_datos_criticos(secret, "") == ""


def test_normal_facts_are_not_flagged():
    assert privacy.looks_sensitive("My favourite language is Python") is False
    assert privacy.looks_sensitive("Project Alpha is 60% done") is False


def test_private_mode_blocks_all_memory_writes(facts):
    store, _ = facts
    store["facts"] = "- Name: Prawin"
    memory_tools.modo_privado.invoke({"activar": True})
    assert "Private mode" in memory_tools.guardar_dato_memoria.invoke({"dato": "Likes biryani"})
    assert "Private mode" in memory_tools.editar_memoria.invoke({"numero_o_texto": "1", "nuevo_texto": "x"})
    assert memory_tools.extraer_datos_criticos("siempre llamame administrador", store["facts"]) == "- Name: Prawin"
    assert "Private mode is ON" in memory_tools.ver_memorias.invoke({})
    memory_tools.modo_privado.invoke({"activar": False})
    assert privacy.is_private_mode() is False


def test_capability_registry_uses_five_states_and_live_config(monkeypatch):
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "JARVIS_FILE_TOOLS_ENABLED", "JARVIS_SYSTEM_TOOLS_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    snap = {item["key"]: item for item in capability_catalog.capability_snapshot()}
    assert {item["state"] for item in snap.values()} <= set(capability_catalog.STATE_LABELS)
    assert snap["conversation"]["state"] == capability_catalog.NEEDS_CONFIG
    assert snap["file_write"]["state"] == capability_catalog.NEEDS_CONFIG
    import importlib.util

    engine = importlib.util.find_spec("openwakeword") is not None and importlib.util.find_spec("sounddevice") is not None
    expected = capability_catalog.UNTESTED if engine else capability_catalog.NEEDS_CONFIG
    assert snap["wake_word_offline"]["state"] == expected
    assert snap["wifi_bluetooth_toggle"]["state"] == capability_catalog.NOT_IMPLEMENTED
    assert snap["window_layouts"]["state"] == capability_catalog.VERIFIED
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("JARVIS_FILE_TOOLS_ENABLED", "true")
    snap = {item["key"]: item for item in capability_catalog.capability_snapshot()}
    assert snap["conversation"]["state"] == capability_catalog.UNTESTED
    assert snap["file_write"]["state"] == capability_catalog.VERIFIED


def test_system_prompt_contains_companion_rules_and_capabilities():
    content = prompts._apply_language_policy("Base. You MUST reply in English.", "Vanakkam da, eppadi irukka?", "ta")
    assert "COMPANION STYLE" in content
    assert "Never claim human feelings" in content
    assert "CAPABILITIES (live registry" in content
    assert "Not implemented:" in content
    assert content.rstrip().splitlines()[-1].startswith("LANGUAGE POLICY:")
    assert "Thanglish" in content.splitlines()[-1]
