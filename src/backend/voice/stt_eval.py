"""Speech-to-text accuracy metrics for the language evaluation set.

WER suits English and romanised Thanglish (space-separated words). Tamil
script is agglutinative, so one wrong suffix makes a whole "word" wrong; CER
(character error rate, Unicode-normalised, spaces ignored) is reported too and
is the primary figure for Tamil.
"""

from __future__ import annotations

import unicodedata


def _edits(ref: list, hyp: list) -> int:
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return row[-1]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text or "")).casefold()
    # Drop punctuation and symbols only: Tamil vowel signs are combining marks,
    # which a regex \w class would strip.
    text = "".join(" " if unicodedata.category(ch)[0] in "PS" else ch for ch in text)
    return " ".join(text.split())


def _graphemes(text: str) -> list[str]:
    """Base characters with their combining marks (Tamil vowel signs, virama)."""
    out: list[str] = []
    for ch in normalize(text).replace(" ", ""):
        if out and unicodedata.category(ch).startswith("M"):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def wer(reference: str, hypothesis: str) -> float:
    ref = normalize(reference).split()
    return _edits(ref, normalize(hypothesis).split()) / max(1, len(ref))


def cer(reference: str, hypothesis: str) -> float:
    ref = _graphemes(reference)
    return _edits(ref, _graphemes(hypothesis)) / max(1, len(ref))
