"""Shared FFmpeg-based audio conversion helpers.

The public errors intentionally omit command output and filesystem paths because
these helpers are used by HTTP- and messaging-facing code.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

FFMPEG_TIMEOUT_SECONDS = 30
_CONVERSION_ERROR = "Audio conversion failed."


class AudioConversionError(RuntimeError):
    """Raised when audio cannot be converted into the requested format."""


def _input_suffix(audio_bytes: bytes) -> str:
    magic = audio_bytes[:4]
    if magic == b"\x1a\x45\xdf\xa3":
        return ".webm"
    if magic == b"OggS":
        return ".ogg"
    if magic == b"RIFF":
        return ".wav"
    if magic[:3] == b"ID3" or magic[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
        return ".mp3"
    return ".bin"


def _resolve_runtime_dir(runtime_dir: str | os.PathLike[str] | None) -> Path:
    configured = runtime_dir or os.getenv("JARVIS_RUNTIME_DIR") or tempfile.gettempdir()
    path = Path(configured)
    path.mkdir(parents=True, exist_ok=True)
    return path


def ffmpeg_executable() -> str | None:
    """Locate FFmpeg on PATH, or in winget's per-user folders (PATH changes
    made by winget only reach processes started after the install)."""
    import shutil

    found = shutil.which("ffmpeg")
    if found:
        return found
    local = os.getenv("LOCALAPPDATA")
    if not local:
        return None
    winget = Path(local) / "Microsoft" / "WinGet"
    candidates = [winget / "Links" / "ffmpeg.exe"]
    candidates += sorted(winget.glob("Packages/*FFmpeg*/*/bin/ffmpeg.exe"), reverse=True)
    return next((str(c) for c in candidates if c.is_file()), None)


def _ffmpeg_commands(
    input_path: Path,
    output_path: Path,
    output_args: list[str],
) -> list[list[str]]:
    prefix = [
        ffmpeg_executable() or "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
    ]
    normal = [*prefix, "-i", str(input_path), *output_args, str(output_path)]
    matroska = [
        *prefix,
        "-f",
        "matroska",
        "-i",
        str(input_path),
        *output_args,
        str(output_path),
    ]
    tolerant = [
        *prefix,
        "-err_detect",
        "ignore_err",
        "-fflags",
        "+genpts+discardcorrupt",
        "-i",
        str(input_path),
        *output_args,
        str(output_path),
    ]
    return [normal, matroska, tolerant]


def _convert(
    audio_bytes: bytes,
    *,
    runtime_dir: str | os.PathLike[str] | None,
    output_suffix: str,
    output_args: list[str],
    expected_magic: bytes,
) -> bytes:
    if not isinstance(audio_bytes, (bytes, bytearray)) or not audio_bytes:
        raise AudioConversionError(_CONVERSION_ERROR)

    try:
        root = _resolve_runtime_dir(runtime_dir)
        with tempfile.TemporaryDirectory(prefix="jarvis_audio_", dir=root) as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / f"input{_input_suffix(bytes(audio_bytes))}"
            output_path = temp_path / f"output{output_suffix}"
            input_path.write_bytes(bytes(audio_bytes))

            for command in _ffmpeg_commands(input_path, output_path, output_args):
                output_path.unlink(missing_ok=True)
                result = subprocess.run(
                    command,
                    capture_output=True,
                    timeout=FFMPEG_TIMEOUT_SECONDS,
                    check=False,
                    shell=False,
                )
                if result.returncode != 0 or not output_path.is_file():
                    continue
                converted = output_path.read_bytes()
                if converted and converted.startswith(expected_magic):
                    return converted
    except (OSError, subprocess.SubprocessError):
        raise AudioConversionError(_CONVERSION_ERROR) from None

    raise AudioConversionError(_CONVERSION_ERROR)


def convert_to_wav(
    audio_bytes: bytes,
    *,
    runtime_dir: str | os.PathLike[str] | None = None,
) -> bytes:
    """Convert audio bytes to 16 kHz, mono, signed 16-bit PCM WAV."""
    return _convert(
        audio_bytes,
        runtime_dir=runtime_dir,
        output_suffix=".wav",
        output_args=[
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "wav",
        ],
        expected_magic=b"RIFF",
    )


def convert_to_ogg_opus(
    audio_bytes: bytes,
    *,
    runtime_dir: str | os.PathLike[str] | None = None,
) -> bytes:
    """Convert audio bytes to an OGG container encoded with libopus."""
    return _convert(
        audio_bytes,
        runtime_dir=runtime_dir,
        output_suffix=".ogg",
        output_args=[
            "-acodec",
            "libopus",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-f",
            "ogg",
        ],
        expected_magic=b"OggS",
    )


def _pcm_wav_to_array(data: bytes):
    import io
    import wave

    import numpy as np

    with wave.open(io.BytesIO(data), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    scale = {1: None, 2: ("<i2", 32768.0), 4: ("<i4", 2147483648.0)}
    if width not in scale:
        raise wave.Error("unsupported sample width")
    if width == 1:
        samples = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        dtype, divisor = scale[width]
        samples = np.frombuffer(frames, dtype=dtype).astype(np.float32) / divisor
    if channels > 1:
        samples = samples[: samples.size - samples.size % channels].reshape(-1, channels).mean(axis=1)
    if rate != 16000 and samples.size:
        target = round(samples.size * 16000 / rate)
        samples = np.interp(np.linspace(0, samples.size - 1, target), np.arange(samples.size), samples)
    return samples.astype(np.float32)


def decode_for_whisper(
    audio_bytes: bytes,
    *,
    runtime_dir: str | os.PathLike[str] | None = None,
):
    """Decode audio into the 16 kHz mono float32 array faster-whisper accepts.

    Passing an array bypasses faster-whisper's PyAV decoder, which breaks on
    some PyAV releases. PCM WAV is decoded with the standard library; any
    other format (or WAV the standard library cannot read) goes through FFmpeg.
    """
    import wave

    data = bytes(audio_bytes or b"")
    if not data:
        raise AudioConversionError(_CONVERSION_ERROR)
    if data.startswith(b"RIFF"):
        try:
            return _pcm_wav_to_array(data)
        except (wave.Error, EOFError, ValueError):
            pass
    try:
        return _pcm_wav_to_array(convert_to_wav(data, runtime_dir=runtime_dir))
    except (wave.Error, EOFError, ValueError):
        raise AudioConversionError(_CONVERSION_ERROR) from None
