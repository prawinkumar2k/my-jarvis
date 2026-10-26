"""Gemini backup model and streaming fallback. Fake clients only (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from core.brain import brain_state, processor
from core.brain.llm_engine import ChainedFallbackChat
from core.errors import LLMServiceError
from core.llm_providers import gemini_backup_model, resolve_llm_provider_config


class RateLimitError(Exception):
    status_code = 429


class FakeClient:
    def __init__(self, name, chunks=None, fail_at=None):
        self.name, self.chunks, self.fail_at, self.calls = name, chunks or [], fail_at, 0

    def stream(self, _messages):
        self.calls += 1
        for i, text in enumerate(self.chunks):
            if self.fail_at == i:
                raise RateLimitError("quota")
            yield SimpleNamespace(content=text)
        if self.fail_at == len(self.chunks):
            raise RateLimitError("quota")


def test_backup_model_only_for_gemini_and_can_be_disabled():
    env = {"GEMINI_API_KEY": "k", "GROQ_API_KEY": "g"}
    config = resolve_llm_provider_config(env)
    assert gemini_backup_model(config, env) == "gemini-3.1-flash-lite"
    assert gemini_backup_model(config, {**env, "JARVIS_GEMINI_BACKUP_MODEL": "none"}) == ""
    assert gemini_backup_model(config, {**env, "JARVIS_GEMINI_BACKUP_MODEL": "gemini-2.5-flash"}) == ""  # same as primary
    assert gemini_backup_model(config, {**env, "JARVIS_GEMINI_BACKUP_MODEL": "llama-3"}) == ""  # not a Gemini model
    groq_first = resolve_llm_provider_config({"GROQ_API_KEY": "g"})
    assert gemini_backup_model(groq_first, {"GROQ_API_KEY": "g"}) == ""
    assert config.fallback_provider == "groq"  # Groq stays the cross-provider fallback


def test_chain_streams_from_next_client_only_if_nothing_was_sent():
    quota = FakeClient("gemini", fail_at=0)
    backup = FakeClient("lite", ["Hel", "lo"])
    assert [c.content for c in ChainedFallbackChat([quota, backup]).stream([])] == ["Hel", "lo"]

    mid = FakeClient("gemini", ["Half"], fail_at=1)
    other = FakeClient("lite", ["Other"])
    seen = []
    with pytest.raises(RateLimitError):
        for chunk in ChainedFallbackChat([mid, other]).stream([]):
            seen.append(chunk.content)
    assert seen == ["Half"] and other.calls == 0  # never stitch two models into one reply


def test_processor_stream_uses_groq_when_gemini_quota_is_gone(monkeypatch):
    monkeypatch.setattr(brain_state, "llm", FakeClient("gemini", fail_at=0))
    monkeypatch.setattr(brain_state, "llm_fallback", FakeClient("groq", ["From ", "Groq"]))
    assert "".join(c.content for c in processor._stream_with_fallback([])) == "From Groq"


def test_processor_stream_reports_the_real_failure_kind(monkeypatch):
    monkeypatch.setattr(brain_state, "llm", FakeClient("gemini", fail_at=0))
    monkeypatch.setattr(brain_state, "llm_fallback", FakeClient("groq", fail_at=0))
    with pytest.raises(LLMServiceError) as info:
        list(processor._stream_with_fallback([]))
    assert info.value.public_code == "llm_rate_limited"


def test_chain_records_which_model_actually_answered():
    class Invoker:
        def __init__(self, name, fail):
            self.model_name, self.fail = name, fail

        def invoke(self, _messages):
            if self.fail:
                raise RateLimitError("quota")
            return "ok"

    chain = ChainedFallbackChat([Invoker("gemini-2.5-flash", True), Invoker("gemini-3.1-flash-lite", False)])
    assert chain.invoke([]) == "ok"
    assert chain.model_name == "gemini-2.5-flash" and chain.last_model == "gemini-3.1-flash-lite"
