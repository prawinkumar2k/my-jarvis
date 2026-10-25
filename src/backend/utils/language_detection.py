"""
Per-message language detection and response-language policy.

Distinguishes four input styles so replies can mirror the user:
- "ta"        Tamil written in Tamil script (U+0B80-U+0BFF).
- "thanglish" Tamil written with Latin characters ("file open pannu").
- "es"        Spanish.
- "en"        English (default for Latin text without other signals).

Detection is deterministic and offline. It only steers the reply language;
code, file paths, commands and identifiers are never translated.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

_TAMIL_CHAR = re.compile(r"[஀-௿]")
_LATIN_WORD = re.compile(r"[a-zA-Z]+")
_INLINE_CODE = re.compile(r"`[^`]*`|```.*?```", re.DOTALL)
_PATH_OR_URL = re.compile(r"(?:[a-zA-Z]:\\|https?://|www\.)\S*|\S+[/\\]\S+|\S+\.[a-zA-Z0-9]{1,5}\b")

# Common Tamil words as typed in Latin script. Kept specific enough that
# ordinary English words do not collide (no "a", "en", "va", "po", "ok").
THANGLISH_MARKERS = frozenset(
    {
        "aachu", "aacha", "adhu", "adhula", "adu", "aana", "anga", "andha", "appo", "appadi",
        "avan", "aval", "ayyo", "chinna", "da", "di", "edhu", "edhuku", "eduthu", "edu",
        "ella", "ellam", "ellame", "enaku", "enakku", "enga", "engae", "enna", "ennaku",
        "ennoda", "eppadi", "eppo", "epdi", "evlo", "evvalavu", "illa", "illai", "illaya",
        "inga", "inge", "indha", "inniku", "innaiku", "ippo", "ippadi", "irukka", "irukku",
        "irundhu", "iruku", "kaattu", "kaatu", "kekkala", "kelu", "konjam", "kudu",
        "kodu", "laam", "macha", "machan", "maathu", "mathu", "mathala", "mudichu", "mudiyuma",
        "mudiyum", "naan", "naa", "nalla", "nallairukku", "nandri", "nee", "neenga", "nenga",
        "nu", "oru", "paaru", "paru", "pannu", "pannunga", "pannala", "panni", "panna",
        "pannanum", "pannuvom", "pannalaam", "parunga", "podu", "podunga", "poi", "ponga",
        "poganum", "romba", "sari", "seri", "sollu", "sollunga", "sonna", "solla", "summa",
        "thaan", "thaane", "thambi", "theriyum", "theriyuma", "theriyala", "thiranthu",
        "thirandhu", "thira", "unga", "ungaluku", "unakku", "unaku", "vaa", "vaanga",
        "vanakkam", "vandhu", "varum", "vechu", "vela", "velai", "vendam", "vendaam",
        "vendum", "venum", "venumna", "yaaru", "yen", "yenna", "kitta", "kooda", "mela",
        "keela", "pakkam", "paathu", "pathu", "close", "open",
    }
)
# "open"/"close" appear in English too; they only count alongside a real marker.
_WEAK_MARKERS = frozenset({"close", "open", "da", "di", "nu", "naa", "oru", "edu", "kudu", "kodu", "poi"})

_SPANISH_MARKERS = frozenset(
    {
        "el", "la", "los", "las", "que", "por", "para", "como", "esta", "estoy", "hola",
        "pon", "abre", "dime", "cual", "qué", "cómo", "música", "gracias", "favor", "quiero",
        "puedes", "una", "uno", "del", "muy", "también", "ahora",
    }
)

SUPPORTED_RESPONSE_PREFERENCES = ("auto", "en", "ta", "thanglish", "es")


@dataclass(frozen=True)
class LanguageDetection:
    code: str  # "ta" | "thanglish" | "es" | "en" | "und"
    confidence: float
    tamil_chars: int = 0
    thanglish_hits: int = 0


def _strip_technical(text: str) -> str:
    """Remove code spans, paths and URLs so they do not skew detection."""
    text = _INLINE_CODE.sub(" ", text)
    return _PATH_OR_URL.sub(" ", text)


def detect_input_language(text: str) -> LanguageDetection:
    """Classify a user message. Pure function; safe on empty input."""
    raw = str(text or "")
    if not raw.strip():
        return LanguageDetection("und", 0.0)

    cleaned = _strip_technical(raw)
    tamil_chars = len(_TAMIL_CHAR.findall(cleaned))
    letters = sum(1 for ch in cleaned if ch.isalpha())
    if tamil_chars and letters and tamil_chars / letters >= 0.3:
        return LanguageDetection("ta", min(1.0, 0.6 + tamil_chars / letters / 2), tamil_chars=tamil_chars)

    words = [w.lower() for w in _LATIN_WORD.findall(cleaned)]
    if not words:
        return LanguageDetection("ta" if tamil_chars else "und", 0.5 if tamil_chars else 0.0, tamil_chars)

    strong = sum(1 for w in words if w in THANGLISH_MARKERS and w not in _WEAK_MARKERS)
    weak = sum(1 for w in words if w in _WEAK_MARKERS)
    hits = strong + (weak if strong else 0)
    ratio = hits / len(words)
    if strong >= 2 or (strong >= 1 and ratio >= 0.2):
        return LanguageDetection("thanglish", min(1.0, 0.5 + ratio), tamil_chars, hits)

    spanish = sum(1 for w in words if w in _SPANISH_MARKERS) + len(re.findall(r"[ñáéíóú¿¡]", cleaned.lower()))
    if spanish >= 2 and spanish / len(words) >= 0.2:
        return LanguageDetection("es", min(1.0, 0.5 + spanish / len(words)), tamil_chars, hits)

    return LanguageDetection("en", 0.6, tamil_chars, hits)


def get_response_preference() -> str:
    """Configured reply language: auto (mirror the user) or a fixed choice."""
    value = str(os.getenv("JARVIS_RESPONSE_LANGUAGE") or "auto").strip().lower()
    return value if value in SUPPORTED_RESPONSE_PREFERENCES else "auto"


_TECH_RULE = (
    "Never translate code, commands, file names, paths, URLs, product names or "
    "technical identifiers; keep them exactly as written."
)

_DIRECTIVES = {
    "ta": (
        "Reply in Tamil using Tamil script (தமிழ்). Common English technical terms may stay in English. "
        + _TECH_RULE
    ),
    "thanglish": (
        "The user writes Tamil in Latin letters (Thanglish). Reply in natural, casual Thanglish "
        "(Tamil words in Latin script, mixed with English technical terms as Tamil speakers do), "
        "not in Tamil script and not in formal English. " + _TECH_RULE
    ),
    "en": "Reply in English. " + _TECH_RULE,
    "es": "Responde en español. " + _TECH_RULE,
}


def resolve_response_language(user_text: str, active_language: str, preference: str | None = None) -> str:
    """Pick the reply language for one turn.

    A fixed preference wins. In auto mode the message's own language wins when
    it is detected with a clear signal; otherwise the active UI language is used.
    """
    pref = (preference or get_response_preference()).lower()
    if pref != "auto":
        return pref
    detected = detect_input_language(user_text)
    if detected.code in {"ta", "thanglish", "es"}:
        return detected.code
    active = str(active_language or "en").strip().lower()
    if detected.code == "en":
        # English input in Tamil mode is common (code-switching); mirror it.
        return "en"
    return active if active in _DIRECTIVES else "en"


def build_response_language_directive(user_text: str, active_language: str, preference: str | None = None) -> str:
    """Return a single prompt line telling the model which language to use."""
    target = resolve_response_language(user_text, active_language, preference)
    return "LANGUAGE POLICY: " + _DIRECTIVES.get(target, _DIRECTIVES["en"])


def build_live_language_directive(active_language: str, preference: str | None = None) -> str:
    """Directive for real-time voice, where the next utterance is not known yet."""
    pref = (preference or get_response_preference()).lower()
    if pref != "auto":
        return "LANGUAGE POLICY: " + _DIRECTIVES.get(pref, _DIRECTIVES["en"])
    lang = str(active_language or "en").strip().lower()
    if lang.startswith("ta"):
        return (
            "LANGUAGE POLICY: The user speaks Tamil, English, or a mix of both. Mirror the language "
            "of each utterance: answer Tamil speech in spoken Tamil and English speech in English; "
            "when the user mixes them, mix them the same way. " + _TECH_RULE
        )
    if lang.startswith("es"):
        return "RESPONDE INEQUÍVOCAMENTE EN ESPAÑOL."
    return "RESPOND UNMISTAKABLY IN ENGLISH."
