"""Provider-neutral LLM configuration resolution."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
_DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"  # production on Groq; qwen3.6-27b was retired
# Free-tier Gemini quotas are per model (gemini-2.5-flash: 20 requests/day in 2026-10), so a
# second Gemini model keeps Gemini answering before Groq. Verified to support tool calls.
_DEFAULT_GEMINI_BACKUP_MODEL = "gemini-3.1-flash-lite"


@dataclass(frozen=True)
class LLMProviderConfig:
    primary_provider: str
    primary_model: str
    primary_api_key: str = field(repr=False)
    fallback_provider: str = ""
    fallback_model: str = ""
    fallback_api_key: str = field(default="", repr=False)
    # Extra providers tried after the fallback (e.g. local Ollama in cloud_first mode).
    extra_fallbacks: tuple[tuple[str, str, str], ...] = field(default=(), repr=False)
    mode: str = "cloud_first"

    @property
    def configured(self) -> bool:
        return bool(self.primary_provider and (self.primary_api_key or self.primary_provider == "ollama"))


def _provider_model(
    source: Mapping[str, str],
    variable: str,
    *,
    provider: str,
    default: str,
) -> str:
    configured = str(source.get(variable) or default).strip() or default
    normalized = configured.lower()
    if provider == "groq" and normalized.startswith("gemini-"):
        return default
    if provider == "gemini" and normalized.startswith(
        ("groq/", "llama-", "meta-llama/", "openai/", "qwen/")
    ):
        return default
    return configured


def resolve_llm_provider_config(
    env: Mapping[str, str] | None = None,
) -> LLMProviderConfig:
    """Resolve the usable primary and fallback providers from one env view."""
    source = os.environ if env is None else env
    requested = str(source.get("JARVIS_LLM_PROVIDER") or "").strip().lower()
    if requested == "google":
        requested = "gemini"
    if requested not in {"", "gemini", "groq", "ollama"}:
        requested = ""
    mode = str(source.get("JARVIS_AI_MODE") or "cloud_first").strip().lower()
    if mode not in {"cloud_first", "local_first", "local_only", "manual"}:
        mode = "cloud_first"
    local_model = str(source.get("OLLAMA_MODEL") or "").strip()
    local = ("ollama", local_model, "ollama") if local_model else ("", "", "")

    gemini_key = str(source.get("GEMINI_API_KEY") or source.get("GOOGLE_API_KEY") or "").strip()
    groq_key = str(source.get("GROQ_API_KEY") or "").strip()
    gemini_model = _provider_model(
        source,
        "JARVIS_GEMINI_MODEL",
        provider="gemini",
        default=_DEFAULT_GEMINI_MODEL,
    )
    groq_model = _provider_model(
        source,
        "JARVIS_GROQ_MODEL",
        provider="groq",
        default=_DEFAULT_GROQ_MODEL,
    )

    if requested == "groq" and groq_key:
        primary = ("groq", groq_model, groq_key)
        fallback = ("gemini", gemini_model, gemini_key) if gemini_key else ("", "", "")
    elif requested == "gemini" and gemini_key:
        primary = ("gemini", gemini_model, gemini_key)
        fallback = ("groq", groq_model, groq_key) if groq_key else ("", "", "")
    elif gemini_key:
        primary = ("gemini", gemini_model, gemini_key)
        fallback = ("groq", groq_model, groq_key) if groq_key else ("", "", "")
    elif groq_key:
        primary = ("groq", groq_model, groq_key)
        fallback = ("", "", "")
    else:
        primary = ("", "", "")
        fallback = ("", "", "")

    extras: tuple[tuple[str, str, str], ...] = ()
    if local[0]:
        cloud = [entry for entry in (primary, fallback) if entry[0]]
        if mode == "local_only" or requested == "ollama" and not cloud:
            primary, fallback, extras = local, ("", "", ""), ()
        elif mode == "local_first" or requested == "ollama":
            chain = [local, *cloud]
            primary, fallback, extras = chain[0], chain[1] if len(chain) > 1 else ("", "", ""), tuple(chain[2:])
        elif primary[0]:
            if fallback[0]:
                extras = (local,)
            else:
                fallback = local
        else:  # no cloud keys at all: local model keeps JARVIS working
            primary = local
    elif mode == "local_only":
        primary, fallback = ("", "", ""), ("", "", "")
    if mode == "manual":
        # The user pinned exactly one provider (JARVIS_LLM_PROVIDER): no fallbacks, no hidden second model.
        # If that provider is not usable the result is "not configured", never a silent switch.
        choices = {
            "gemini": ("gemini", gemini_model, gemini_key) if gemini_key else ("", "", ""),
            "groq": ("groq", groq_model, groq_key) if groq_key else ("", "", ""),
            "ollama": local,
        }
        primary = choices.get(requested, ("", "", ""))
        fallback, extras = ("", "", ""), ()
    return LLMProviderConfig(
        primary_provider=primary[0],
        primary_model=primary[1],
        primary_api_key=primary[2],
        fallback_provider=fallback[0],
        fallback_model=fallback[1],
        fallback_api_key=fallback[2],
        extra_fallbacks=extras,
        mode=mode,
    )


def gemini_backup_model(config: LLMProviderConfig, env: Mapping[str, str] | None = None) -> str:
    """Second Gemini model tried when the primary Gemini model fails ('' = none).

    JARVIS_GEMINI_BACKUP_MODEL=none disables it.
    """
    if config.primary_provider != "gemini" or config.mode == "manual":
        return ""
    source = os.environ if env is None else env
    model = str(source.get("JARVIS_GEMINI_BACKUP_MODEL") or _DEFAULT_GEMINI_BACKUP_MODEL).strip()
    if model.lower() in {"none", "off", "false", "0"} or model == config.primary_model:
        return ""
    if not model.lower().startswith("gemini-"):
        return ""
    return model


def resolve_gemini_api_key(env: Mapping[str, str] | None = None) -> str:
    """Resolve Gemini API key independently of provider selection."""
    source = os.environ if env is None else env
    return str(source.get("GEMINI_API_KEY") or source.get("GOOGLE_API_KEY") or "").strip()


def resolve_groq_api_key(env: Mapping[str, str] | None = None) -> str:
    """Resolve Groq API key independently of provider selection."""
    source = os.environ if env is None else env
    return str(source.get("GROQ_API_KEY") or "").strip()


def provider_base_url(provider: str) -> str:
    if provider == "gemini":
        return "https://generativelanguage.googleapis.com/v1beta/openai/"
    if provider == "groq":
        return "https://api.groq.com/openai/v1"
    if provider == "ollama":
        base = str(os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
        return f"{base}/v1"
    raise ValueError("unsupported_llm_provider")
