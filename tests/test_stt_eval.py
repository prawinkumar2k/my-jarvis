"""Scoring math for the speech-to-text evaluation harness (no audio involved)."""

from voice.stt_eval import cer, normalize, wer


def test_wer_counts_word_edits_and_ignores_case_and_punctuation():
    assert wer("Chrome open pannu", "chrome open pannu!") == 0.0
    assert wer("chrome open pannu", "chrome open pannu da") == 1 / 3  # one insertion
    assert wer("adutha song podu", "adutha son") == 2 / 3  # substitution + deletion


def test_tamil_vowel_signs_survive_normalisation():
    assert normalize("வணக்கம், ஜார்விஸ்!") == "வணக்கம் ஜார்விஸ்"


def test_tamil_cer_counts_letters_with_their_vowel_signs():
    assert cer("வணக்கம்", "வணக்கம்") == 0.0
    # ண -> ன is one wrong letter out of five (வ ண க் க ம்)
    assert cer("வணக்கம்", "வனக்கம்") == 1 / 5
    # A wrong vowel sign changes one letter, not the whole word
    assert cer("பாட்டு", "பட்டு") == 1 / 3  # பா ட் டு: three letters


def test_empty_hypothesis_is_full_error():
    assert wer("open chrome", "") == 1.0
    assert cer("abc", "") == 1.0
