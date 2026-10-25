from __future__ import annotations

import pytest
from utils import jarvis_i18n
from utils.language_detection import (
    build_live_language_directive,
    build_response_language_directive,
    detect_input_language,
    resolve_response_language,
)
from voice.live_context import LiveContextPolicy, build_live_context


@pytest.fixture(autouse=True)
def _auto_response_language(monkeypatch):
    monkeypatch.delenv("JARVIS_RESPONSE_LANGUAGE", raising=False)
    previous = jarvis_i18n.get_current_language()
    yield
    jarvis_i18n.set_current_language(previous)


# --- Detection: four distinct input styles --------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "வணக்கம், இன்று வானிலை எப்படி இருக்கிறது?",
        "என் Desktop-ல் உள்ள files-ஐ காட்டு",
    ],
)
def test_tamil_script_is_detected_as_tamil(text):
    assert detect_input_language(text).code == "ta"


@pytest.mark.parametrize(
    "text",
    [
        "Desktop la enna files irukku nu paaru",
        "Spotify open pannu da",
        "konjam volume kammi pannunga",
        "ennoda repoku mathala",
        "inniku weather eppadi irukku",
    ],
)
def test_thanglish_is_detected_separately_from_tamil_script(text):
    assert detect_input_language(text).code == "thanglish"


@pytest.mark.parametrize(
    "text",
    [
        "Open the file and close the window",
        "What is the weather today in Chennai?",
        "Run pytest on the backend and show me the failures",
        "Set the volume to 40 percent",
    ],
)
def test_plain_english_is_not_mistaken_for_thanglish(text):
    assert detect_input_language(text).code == "en"


def test_spanish_still_detected():
    assert detect_input_language("pon música de Queen por favor").code == "es"


def test_paths_and_code_do_not_skew_detection():
    text = "please read `src/backend/enna/pannu.py` and C:\\illa\\venum\\notes.txt"
    assert detect_input_language(text).code == "en"


def test_empty_input_is_undetermined():
    assert detect_input_language("   ").code == "und"


# --- Response policy -------------------------------------------------------


def test_reply_mirrors_input_style_in_auto_mode():
    assert resolve_response_language("Spotify open pannu", "en") == "thanglish"
    # Tamil-script input is answered in Thanglish (English letters) by default.
    assert resolve_response_language("பாடல் போடு", "en") == "thanglish"
    assert resolve_response_language("பாடல் போடு", "en", preference="ta") == "ta"
    assert resolve_response_language("open spotify", "ta") == "en"


def test_fixed_preference_overrides_detection(monkeypatch):
    monkeypatch.setenv("JARVIS_RESPONSE_LANGUAGE", "ta")
    assert resolve_response_language("open spotify", "en") == "ta"


def test_invalid_preference_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv("JARVIS_RESPONSE_LANGUAGE", "klingon")
    assert resolve_response_language("Spotify open pannu", "en") == "thanglish"


def test_directives_protect_technical_identifiers():
    for text in ("Spotify open pannu", "பாடல் போடு", "open spotify"):
        directive = build_response_language_directive(text, "en")
        assert directive.startswith("LANGUAGE POLICY:")
        assert "Never translate code, commands, file names, paths" in directive


def test_thanglish_directive_asks_for_latin_script_not_tamil_script():
    directive = build_response_language_directive("file open pannu", "en")
    assert "Thanglish" in directive
    assert "not in Tamil script" in directive


# --- Configuration and integration ----------------------------------------


def test_tamil_is_a_selectable_language_with_whisper_and_locale():
    cfg = jarvis_i18n.LANGUAGE_CONFIG["ta"]
    assert cfg["whisper_lang"] == "ta"
    assert cfg["locale"] == "ta-IN"
    assert "ta" in jarvis_i18n.BACKEND_TRANSLATIONS


def test_tamil_mode_does_not_claim_a_native_local_tts_voice(monkeypatch):
    monkeypatch.delenv("JARVIS_TTS_MODEL_TA", raising=False)
    assert jarvis_i18n.has_native_tts("ta") is False
    assert jarvis_i18n.has_native_tts("en") is True
    monkeypatch.setenv("JARVIS_TTS_MODEL_TA", "ta_IN-custom.onnx")
    assert jarvis_i18n.has_native_tts("ta") is True


def test_tamil_translations_keep_every_english_key():
    assert set(jarvis_i18n.BACKEND_TRANSLATIONS["en"]) <= set(jarvis_i18n.BACKEND_TRANSLATIONS["ta"])


def test_tamil_mode_uses_english_fallback_messages_not_spanish():
    from core.brain import router
    from modules.spotify import messages

    jarvis_i18n.set_current_language("ta")
    assert messages.is_english() is True
    assert messages.text("Playing", "Reproduciendo") == "Playing"
    assert router._lang_is_english() is True
    assert router._language_is_english("ta") is True
    assert router._language_is_english("es") is False


def test_live_voice_tamil_directive_mirrors_spoken_language():
    directive = build_live_language_directive("ta")
    assert "Tamil" in directive
    assert "Mirror" in directive
    context = build_live_context(
        base_instruction="JARVIS",
        language="ta",
        profile_name="Administrator",
        profile_facts="",
        history=(),
        allowed_tool_names=(),
        policy=LiveContextPolicy(),
    )
    assert "Tamil" in context


def test_system_prompt_replaces_english_lock_with_policy(monkeypatch):
    from core.brain import prompts

    content = prompts._apply_language_policy(
        "Base prompt. You MUST reply in English. More rules.", "Desktop la files kaatu", "en"
    )
    assert "You MUST reply in English." not in content
    assert content.rstrip().splitlines()[-1].startswith("LANGUAGE POLICY:")
    assert "Thanglish" in content
