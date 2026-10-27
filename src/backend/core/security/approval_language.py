"""Understanding short replies to "may I do this?" in English, Tanglish, Tamil and Spanish.

Fail closed. A reply approves only when the *whole* message is an affirmation
("ok", "go ahead", "seri pannu"). Anything that adds content ("yes and open
Chrome"), contains a negation ("yes but don't"), or is long, is `unclear` and
is handled as an ordinary new message, never as permission. Approval is also
bound to one pending request by the caller (it expires, and any unclear reply
discards it), so an old "okay" cannot authorise a later, different action.
"""

from __future__ import annotations

import unicodedata

# A reply must contain at least one STRONG word, or be exactly one of PHRASES.
STRONG_APPROVE = frozenset({
    # English
    "yes", "yeah", "yep", "yup", "ok", "okay", "okey", "okk", "sure", "proceed", "continue", "confirm",
    "confirmed", "approve", "approved", "fine", "alright",
    # Tanglish
    "seri", "sari", "sare", "saringa", "serri", "aama", "aam", "ama", "aamam", "pannu", "pannunga", "panni",
    "panniru", "pannidu", "pannuda", "vidu", "podu", "poduga", "seiyunga",
    # Tamil script
    "சரி", "ஆமா", "ஆம்", "பண்ணு", "பண்ணுங்க", "செய்",
    # Spanish
    "si", "sí", "claro", "adelante", "hazlo", "procede", "proceder", "dale", "confirmo", "autorizo",
    "ejecuta", "ejecutar", "supuesto", "afirmativo", "correcto", "autorizado", "confirmar", "autorizar",
})
# Allowed next to a strong word ("ok go ahead", "yes do it") but never enough alone.
WEAK_APPROVE = frozenset({"go", "ahead", "do", "it", "that", "thats", "is", "all", "right", "good", "on", "haa", "ha", "de", "acuerdo", "por"})
PHRASES = frozenset({
    "go ahead", "do it", "go on", "carry on", "lets go", "let us go", "sounds good", "thats fine", "thats good",
    "all right", "go for it", "de acuerdo",
})

REJECT_WORDS = frozenset({
    "no", "nope", "nah", "never", "cancel", "cancelled", "canceled", "stop", "abort", "reject", "rejected",
    "dont", "not", "wait", "hold", "nevermind", "undo", "wrong", "wont",
    "vendaam", "vendam", "venam", "vena", "vendaa", "illa", "illai", "nillu", "niruthu", "nirutthu",
    "வேண்டாம்", "வேணாம்", "இல்ல", "இல்லை", "நிறுத்து",
    "cancela", "cancelar", "aborta", "abortar", "detener", "deten", "rechazar", "negativo", "para",
})

FILLERS = frozenset({
    "please", "pls", "plz", "da", "dei", "bro", "ji", "pa", "sir", "boss", "jarvis", "thanks", "thank", "you",
    "now", "then", "just", "and", "ah", "ahh", "hmm", "um", "so", "ya", "ma", "madam",
})

MAX_WORDS = 8


def _words(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", str(text or "")).casefold().replace("'", "").replace("’", "")
    # Drop punctuation and symbols only; Tamil vowel signs are combining marks and must stay.
    text = "".join(" " if unicodedata.category(ch)[0] in "PS" else ch for ch in text)
    return text.split()


def interpret_reply(text: str) -> str:
    """Return "approve", "reject" or "unclear"."""
    words = _words(text)
    if not words or len(words) > MAX_WORDS:
        return "unclear"
    if any(word in REJECT_WORDS for word in words):
        return "reject"
    content = [word for word in words if word not in FILLERS]
    if not content:
        return "unclear"
    if " ".join(content) in PHRASES:
        return "approve"
    if all(word in STRONG_APPROVE or word in WEAK_APPROVE for word in content) and any(
        word in STRONG_APPROVE for word in content
    ):
        return "approve"
    return "unclear"
