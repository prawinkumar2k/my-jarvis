"""Provider routing for every JARVIS_AI_MODE. Pure configuration logic; no network."""

from __future__ import annotations

from core.llm_providers import gemini_backup_model, resolve_llm_provider_config

KEYS = {"GEMINI_API_KEY": "g-key", "GROQ_API_KEY": "q-key", "OLLAMA_MODEL": "qwen2.5:3b"}


def chain(env):
    config = resolve_llm_provider_config(env)
    entries = [config.primary_provider, config.fallback_provider, *(e[0] for e in config.extra_fallbacks)]
    if gemini_backup_model(config, env):
        entries.insert(1, "gemini(backup)")
    return [e for e in entries if e], config


def test_cloud_first_prefers_gemini_then_backup_then_groq_then_local():
    order, config = chain({**KEYS, "JARVIS_AI_MODE": "cloud_first", "JARVIS_LLM_PROVIDER": "gemini"})
    assert order == ["gemini", "gemini(backup)", "groq", "ollama"] and config.mode == "cloud_first"


def test_local_first_starts_with_the_local_model():
    order, _ = chain({**KEYS, "JARVIS_AI_MODE": "local_first"})
    assert order[0] == "ollama" and "gemini" in order  # cloud only as the explicit fallback


def test_local_only_never_contains_a_cloud_provider_even_with_keys():
    order, config = chain({**KEYS, "JARVIS_AI_MODE": "local_only"})
    assert order == ["ollama"] and config.mode == "local_only"
    nothing, config = chain({"GEMINI_API_KEY": "g-key", "JARVIS_AI_MODE": "local_only"})  # no local model installed
    assert nothing == [] and not config.configured


def test_manual_uses_exactly_the_chosen_provider_and_nothing_else():
    for chosen in ("gemini", "groq", "ollama"):
        order, config = chain({**KEYS, "JARVIS_AI_MODE": "manual", "JARVIS_LLM_PROVIDER": chosen})
        assert order == [chosen] and config.fallback_provider == "" and config.extra_fallbacks == ()


def test_manual_never_switches_silently_when_the_chosen_provider_is_unusable():
    env = {"GROQ_API_KEY": "q-key", "OLLAMA_MODEL": "qwen2.5:3b", "JARVIS_AI_MODE": "manual", "JARVIS_LLM_PROVIDER": "gemini"}
    order, config = chain(env)
    assert order == [] and not config.configured  # honest "not configured", not a quiet switch to Groq


def test_manual_without_a_choice_is_not_configured():
    assert chain({**KEYS, "JARVIS_AI_MODE": "manual"})[0] == []


def test_unknown_mode_falls_back_to_cloud_first():
    assert resolve_llm_provider_config({**KEYS, "JARVIS_AI_MODE": "turbo"}).mode == "cloud_first"
