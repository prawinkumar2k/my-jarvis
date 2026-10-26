from __future__ import annotations

import pytest
from core.brain.llm_engine import ChainedFallbackChat
from core.llm_providers import provider_base_url, resolve_llm_provider_config

KEYS = {"GEMINI_API_KEY": "g", "GROQ_API_KEY": "q"}


def _order(cfg):
    return [cfg.primary_provider, cfg.fallback_provider, *(e[0] for e in cfg.extra_fallbacks)]


def test_cloud_first_adds_local_ollama_last():
    cfg = resolve_llm_provider_config({**KEYS, "OLLAMA_MODEL": "qwen2.5:3b"})
    assert _order(cfg) == ["gemini", "groq", "ollama"]
    assert cfg.mode == "cloud_first"


def test_local_first_tries_ollama_before_cloud():
    cfg = resolve_llm_provider_config({**KEYS, "OLLAMA_MODEL": "qwen2.5:3b", "JARVIS_AI_MODE": "local_first"})
    assert _order(cfg) == ["ollama", "gemini", "groq"]


def test_local_only_never_uses_cloud_even_with_keys():
    cfg = resolve_llm_provider_config({**KEYS, "OLLAMA_MODEL": "qwen2.5:3b", "JARVIS_AI_MODE": "local_only"})
    assert _order(cfg) == ["ollama", ""]
    assert cfg.configured


def test_no_cloud_keys_uses_local_model_alone():
    cfg = resolve_llm_provider_config({"OLLAMA_MODEL": "qwen2.5:3b"})
    assert cfg.primary_provider == "ollama" and cfg.configured


def test_without_ollama_behavior_is_unchanged():
    cfg = resolve_llm_provider_config(KEYS)
    assert _order(cfg) == ["gemini", "groq"]
    assert resolve_llm_provider_config({"JARVIS_AI_MODE": "local_only", **KEYS}).configured is False


def test_ollama_base_url(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    assert provider_base_url("ollama") == "http://127.0.0.1:11434/v1"


class _Client:
    def __init__(self, name, fail=False):
        self.name, self.fail, self.calls = name, fail, 0

    def invoke(self, _messages):
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.name} down")
        return self.name

    def bind_tools(self, _tools, **_kw):
        return self


def test_chain_tries_each_provider_once_in_order():
    groq, ollama = _Client("groq", fail=True), _Client("ollama")
    assert ChainedFallbackChat([groq, ollama]).bind_tools([]).invoke([]) == "ollama"
    assert (groq.calls, ollama.calls) == (1, 1)


def test_chain_raises_last_error_when_all_fail():
    a, b = _Client("a", fail=True), _Client("b", fail=True)
    with pytest.raises(RuntimeError, match="b down"):
        ChainedFallbackChat([a, b]).invoke([])
    assert (a.calls, b.calls) == (1, 1)
