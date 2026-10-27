"""Benchmark a local Ollama model on JARVIS-style requests (fully offline).

Usage:
    venv\\Scripts\\python.exe scripts\\benchmark_local_model.py [model] [--runs 2]

Measures, with identical prompts for every model:
- first-token latency and total latency (streaming plain replies),
- tool-call accuracy: right tool + right key argument,
- invalid tool calls: unknown tool or arguments that are not valid JSON,
- VRAM in use while the model is loaded (nvidia-smi, when present).
Results are printed and written to scratch-free JSON next to nothing: stdout only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import time
import urllib.request

BASE = "http://127.0.0.1:11434"

TOOLS = [
    {"name": "abrir_aplicacion", "description": "Open an installed application by name.",
     "parameters": {"type": "object", "properties": {"nombre_app": {"type": "string"}}, "required": ["nombre_app"]}},
    {"name": "ajustar_volumen", "description": "Set the system volume to a level 0-100, or up/down/mute.",
     "parameters": {"type": "object", "properties": {"nivel": {"type": "string"}}, "required": ["nivel"]}},
    {"name": "poner_temporizador", "description": "Start a timer, e.g. duracion '5 minutes'.",
     "parameters": {"type": "object", "properties": {"duracion": {"type": "string"}}, "required": ["duracion"]}},
    {"name": "guardar_nota", "description": "Save a short note for the user.",
     "parameters": {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"]}},
    {"name": "informacion_sistema", "description": "Report CPU, memory, disk and battery.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "buscar_en_internet", "description": "Search the web for current information.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
]
NAMES = {t["name"] for t in TOOLS}

# (prompt, expected tool, key argument, substring the argument must contain)
TOOL_CASES = [
    ("Open Chrome", "abrir_aplicacion", "nombre_app", "chrome"),
    ("chrome open pannu", "abrir_aplicacion", "nombre_app", "chrome"),
    ("Set the volume to 40", "ajustar_volumen", "nivel", "40"),
    ("volume 30 ku vai", "ajustar_volumen", "nivel", "30"),
    ("Start a 10 minute timer", "poner_temporizador", "duracion", "10"),
    ("5 nimisham timer vai", "poner_temporizador", "duracion", "5"),
    ("Note this down: buy milk tomorrow", "guardar_nota", "texto", "milk"),
    ("How much battery and CPU am I using right now?", "informacion_sistema", None, None),
    ("system condition enna?", "informacion_sistema", None, None),
    ("Who won the cricket match yesterday?", "buscar_en_internet", "query", "cricket"),
]
CHAT_CASES = ["Say hello in one short sentence.", "Explain what RAM is in one sentence."]
SYSTEM = "You are JARVIS, a Windows assistant. Use a tool when the request needs an action or live data."


def _post(path: str, body: dict, timeout: float = 300):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 - local Ollama only


def _vram_mb() -> float | None:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    out = subprocess.run([smi, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, check=False).stdout.strip()
    try:
        return float(out.splitlines()[0])
    except (ValueError, IndexError):
        return None


def chat_latency(model: str, prompt: str) -> tuple[float, float]:
    start = time.perf_counter()
    first = None
    with _post("/api/chat", {"model": model, "stream": True, "messages": [{"role": "user", "content": prompt}]}) as r:
        for line in r:
            data = json.loads(line)
            if first is None and data.get("message", {}).get("content"):
                first = time.perf_counter() - start
            if data.get("done"):
                break
    return first or 0.0, time.perf_counter() - start


def tool_case(model: str, prompt: str) -> tuple[float, list]:
    body = {"model": model, "stream": False, "tools": [{"type": "function", "function": t} for t in TOOLS],
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
    start = time.perf_counter()
    with _post("/api/chat", body) as r:
        data = json.load(r)
    return time.perf_counter() - start, data.get("message", {}).get("tool_calls") or []


def judge(calls: list, tool: str, arg: str | None, must: str | None) -> tuple[bool, bool]:
    """(correct, invalid)."""
    if not calls:
        return False, False
    fn = calls[0].get("function", {})
    name, args = fn.get("name"), fn.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return False, True
    if name not in NAMES or not isinstance(args, dict):
        return False, True
    if name != tool:
        return False, False
    if arg is None:
        return True, False
    return must.lower() in str(args.get(arg, "")).lower(), False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", nargs="?", default="qwen2.5:3b")
    parser.add_argument("--runs", type=int, default=2)
    a = parser.parse_args()

    vram_before = _vram_mb()
    load_start = time.perf_counter()
    chat_latency(a.model, "Hi")  # load the model (cold start)
    cold = time.perf_counter() - load_start
    vram_loaded = _vram_mb()

    firsts, totals = [], []
    for _ in range(a.runs):
        for prompt in CHAT_CASES:
            f, t = chat_latency(a.model, prompt)
            firsts.append(f)
            totals.append(t)

    correct = invalid = 0
    tool_times, misses = [], []
    for _ in range(a.runs):
        for prompt, tool, arg, must in TOOL_CASES:
            seconds, calls = tool_case(a.model, prompt)
            ok, bad = judge(calls, tool, arg, must)
            correct += ok
            invalid += bad
            tool_times.append(seconds)
            if not ok:
                got = calls[0]["function"].get("name") if calls else "no tool"
                misses.append(f"{prompt!r} -> {got}")
    n = len(TOOL_CASES) * a.runs
    report = {
        "model": a.model,
        "runs": a.runs,
        "cold_load_s": round(cold, 1),
        "first_token_s_median": round(statistics.median(firsts), 2),
        "reply_total_s_median": round(statistics.median(totals), 2),
        "tool_call_s_median": round(statistics.median(tool_times), 2),
        "tool_accuracy": f"{correct}/{n}",
        "invalid_tool_calls": f"{invalid}/{n}",
        "vram_mb_before": vram_before,
        "vram_mb_loaded": vram_loaded,
        "misses": sorted(set(misses)),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
