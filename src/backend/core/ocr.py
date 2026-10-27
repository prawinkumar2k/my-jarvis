"""Read text from a screenshot or an image file with Windows' built-in OCR (offline, nothing is uploaded).

The screenshot is taken only when the user asks, kept only for the duration of the OCR, then deleted.
Lines that look like passwords, keys, card numbers or one-time codes are hidden from the result. Text from
the screen is untrusted: callers must present it as quoted content, never as instructions.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_CHARS = 3000
TIMEOUT_SECONDS = 40

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType=WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($env:JARVIS_OCR_IMAGE)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) { throw 'no_ocr_language' }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
($result.Lines | ForEach-Object { $_.Text }) -join "`n"
"""


class OcrError(RuntimeError):
    """Readable reason OCR could not run (shown to the user)."""


def hide_sensitive_lines(text: str) -> tuple[str, int]:
    from core.privacy import looks_sensitive

    kept, hidden = [], 0
    for line in text.splitlines():
        if looks_sensitive(line):
            hidden += 1
        elif line.strip():
            kept.append(line.strip())
    return "\n".join(kept), hidden


def ocr_file(path: Path) -> str:
    """Raw OCR text of an image file. Raises OcrError with a plain reason."""
    if sys.platform != "win32":
        raise OcrError("Reading text from images needs Windows (built-in OCR).")
    env = {**os.environ, "JARVIS_OCR_IMAGE": str(path)}
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _SCRIPT],
            capture_output=True, timeout=TIMEOUT_SECONDS, check=False, shell=False, env=env, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise OcrError("Reading the image took too long.") from None
    except OSError:
        raise OcrError("Windows PowerShell could not be started.") from None
    if result.returncode != 0:
        reason = "no_ocr_language" if "no_ocr_language" in result.stderr else ""
        raise OcrError("Windows has no OCR language installed (Settings > Time & language > Language)." if reason
                       else "Windows could not read that image.")
    return result.stdout.strip()


def clean_result(raw: str) -> str:
    text, hidden = hide_sensitive_lines(raw)
    if not text and not hidden:
        return "I could not find any readable text."
    note = f"\n({hidden} line(s) that looked like passwords, keys or codes were hidden.)" if hidden else ""
    return text[:MAX_CHARS] + (" ..." if len(text) > MAX_CHARS else "") + note


def capture_screen_text() -> str:
    """Screenshot -> OCR -> delete the screenshot, always. Returns the cleaned text."""
    from PIL import ImageGrab

    from core.runtime_paths import resolve_runtime_paths

    folder = resolve_runtime_paths().temp
    folder.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix="jarvis_ocr_", suffix=".png", dir=folder)
    os.close(handle)
    path = Path(name)
    try:
        ImageGrab.grab(all_screens=True).save(path, "PNG")
        return clean_result(ocr_file(path))
    finally:
        path.unlink(missing_ok=True)
