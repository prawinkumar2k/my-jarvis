r"""Measure offline speech-to-text accuracy on real recordings.

Usage:
    venv\Scripts\python.exe scripts\evaluate_stt.py <folder> [--model small]

<folder>/manifest.csv columns: file,language,kind,reference
    language: whisper code (ta, en)   kind: tamil | thanglish | english | mixed
    reference: what the speaker actually said, typed by a person.

Only real recordings with honest human transcripts give meaningful numbers.
Runs fully offline (HF_HUB_OFFLINE=1); the model must already be downloaded.
Writes <folder>/stt_report.json and prints a summary per kind.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--model", default=os.getenv("JARVIS_WHISPER_MODEL", "small"))
    args = parser.parse_args()

    from voice.stt_eval import cer, wer
    from voice.transcription import LazyWhisperTranscriber

    manifest = args.folder / "manifest.csv"
    rows = list(csv.DictReader(manifest.open(encoding="utf-8-sig")))
    if not rows:
        print("manifest.csv has no rows")
        return 2
    stt = LazyWhisperTranscriber(enabled=True, model_name=args.model, device="cpu", compute_type="int8", runtime_dir=args.folder)
    results = []
    for row in rows:
        audio = (args.folder / row["file"]).read_bytes()
        started = time.perf_counter()
        heard = stt.transcribe(audio, row["language"])
        results.append({
            **row,
            "heard": heard,
            "seconds": round(time.perf_counter() - started, 2),
            "wer": round(wer(row["reference"], heard), 3),
            "cer": round(cer(row["reference"], heard), 3),
        })
        print(f"[{row['kind']}] {row['file']}: WER {results[-1]['wer']:.2f} CER {results[-1]['cer']:.2f}")
    summary = {}
    for kind in sorted({r["kind"] for r in results}):
        group = [r for r in results if r["kind"] == kind]
        summary[kind] = {
            "samples": len(group),
            "mean_wer": round(sum(r["wer"] for r in group) / len(group), 3),
            "mean_cer": round(sum(r["cer"] for r in group) / len(group), 3),
            "mean_seconds": round(sum(r["seconds"] for r in group) / len(group), 2),
        }
    report = {"model": args.model, "device": "cpu/int8", "summary": summary, "results": results}
    (args.folder / "stt_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
