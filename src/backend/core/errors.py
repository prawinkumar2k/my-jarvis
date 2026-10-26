LLM_UNCONFIGURED_MESSAGE = "Configure GEMINI_API_KEY or GROQ_API_KEY to enable AI responses."
CHAT_UNAVAILABLE_MESSAGE = "The AI service is temporarily unavailable."


class LLMUnavailableError(RuntimeError):
    """Raised when a request needs an LLM but no provider is configured."""

    def __init__(self):
        super().__init__("No LLM provider is configured.")


LLM_FAILURE_MESSAGES = {
    "rate_limited": "The AI provider's free usage limit was reached. Wait about a minute, or add a free GROQ_API_KEY as an automatic backup.",
    "auth_failed": "The AI provider rejected the API key. Check or replace the key in the setup screen.",
    "timeout": "The AI provider took too long to answer. Please try again.",
    "network": "Could not reach the AI provider. Check the internet connection.",
}


def classify_llm_failure(exc: BaseException | None) -> str:
    """Map a provider exception to rate_limited / auth_failed / timeout / network / unavailable."""
    name = type(exc).__name__ if exc is not None else ""
    text = str(getattr(exc, "status_code", "") or "")
    if name == "RateLimitError" or text == "429":
        return "rate_limited"
    if name in {"AuthenticationError", "PermissionDeniedError"} or text in {"401", "403"}:
        return "auth_failed"
    if "Timeout" in name:
        return "timeout"
    if name in {"APIConnectionError", "ConnectError", "ConnectionError"}:
        return "network"
    return "unavailable"


class LLMServiceError(RuntimeError):
    """Raised when a configured LLM cannot complete a request.

    Raised inside an ``except`` block, so it records why the provider failed
    (``kind``) without exposing the raw provider message.
    """

    def __init__(self):
        import sys

        super().__init__("The LLM service is temporarily unavailable.")
        self.kind = classify_llm_failure(sys.exc_info()[1])

    @property
    def public_code(self) -> str:
        return "chat_unavailable" if self.kind == "unavailable" else f"llm_{self.kind}"

    @property
    def public_message(self) -> str:
        return LLM_FAILURE_MESSAGES.get(self.kind, CHAT_UNAVAILABLE_MESSAGE)
