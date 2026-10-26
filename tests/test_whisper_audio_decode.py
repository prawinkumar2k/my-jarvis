"""Whisper input decoding: arrays are built without PyAV or FFmpeg for PCM WAV."""

from __future__ import annotations

import io
import wave

import numpy as np
import pytest
from utils import audio_conversion
from utils.audio_conversion import AudioConversionError, decode_for_whisper


def _wav(samples: np.ndarray, rate: int, channels: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((samples * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def test_stereo_44k_wav_becomes_16k_mono_float32(monkeypatch):
    monkeypatch.setattr(audio_conversion, "convert_to_wav", lambda *a, **k: pytest.fail("FFmpeg not needed"))
    tone = np.sin(np.linspace(0, 2 * np.pi * 440, 44100)) * 0.5
    stereo = np.repeat(tone, 2)  # identical left/right channels, 1 second
    audio = decode_for_whisper(_wav(stereo, 44100, 2))
    assert audio.dtype == np.float32
    assert abs(audio.size - 16000) <= 1
    assert 0.45 < float(np.abs(audio).max()) <= 0.51


def test_16k_mono_wav_is_passed_through_unchanged():
    samples = np.linspace(-0.5, 0.5, 1600)
    audio = decode_for_whisper(_wav(samples, 16000, 1))
    assert audio.size == 1600
    assert np.allclose(audio, samples, atol=1e-4)


def test_non_wav_audio_goes_through_ffmpeg(monkeypatch):
    calls = []

    def fake_convert(data, **_kwargs):
        calls.append(data[:4])
        return _wav(np.zeros(160), 16000, 1)

    monkeypatch.setattr(audio_conversion, "convert_to_wav", fake_convert)
    assert decode_for_whisper(b"\x1a\x45\xdf\xa3webm-bytes").size == 160
    assert calls == [b"\x1a\x45\xdf\xa3"]


def test_empty_or_undecodable_audio_raises_controlled_error(monkeypatch):
    def broken(*_a, **_k):
        raise AudioConversionError("Audio conversion failed.")

    monkeypatch.setattr(audio_conversion, "convert_to_wav", broken)
    with pytest.raises(AudioConversionError):
        decode_for_whisper(b"")
    with pytest.raises(AudioConversionError):
        decode_for_whisper(b"not audio at all")
