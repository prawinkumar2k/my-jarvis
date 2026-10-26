"""Stop-speaking behaviour, run in Node against the real functions from main.js.

The functions are lifted out of main.js by name, so this exercises the shipped
code; browser audio, fetch and the Live client are stubs.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "frontend" / "static" / "js" / "main.js"
NODE = shutil.which("node")


def _function_source(source: str, signature: str) -> str:
    start = source.index(signature)
    depth, i = 0, source.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        i += 1
        if depth == 0:
            return source[start:i]


@pytest.mark.skipif(NODE is None, reason="node is required")
def test_stop_speaking_halts_playback_and_queued_sentences():
    src = MAIN.read_text(encoding="utf-8")
    functions = "\n".join(
        _function_source(src, sig)
        for sig in (
            "function interrumpirAudio()",
            "function liveVoiceIsPlaying()",
            "function renderStopSpeaking()",
            "function stopSpeaking()",
            "async function speakSentenceChain(",
        )
    )
    script = f"""
let isSpeaking = false, currentAudio = null, activeTtsController = null;
let activeSpeakToken = 0, ttsChainActive = false, ttsChainToken = 0, wakeWordCooldownUntil = 0;
const started = [], logs = [], bargeIns = [];
const button = {{ hidden: true }};
const document = {{ getElementById: (id) => (id === 'stop-speaking' ? button : null) }};
const window = {{}};
const addLogEntry = (m) => logs.push(m), t = (k) => k, prefetchTts = () => {{}};
const animateWaves = () => renderStopSpeaking(), setCurrentMode = () => {{}};
let liveVoiceClient = null;
const pending = [];
function speak(text, onFinished) {{
    isSpeaking = true; started.push(text); renderStopSpeaking();
    currentAudio = {{ src: '', pause() {{ this.paused = true; }} }};
    pending.push(() => {{ isSpeaking = false; currentAudio = null; onFinished(true); }});
}}
{functions}
const assert = (ok, msg) => {{ if (!ok) {{ console.error(msg, JSON.stringify({{started, button, logs}})); process.exit(1); }} }};

// 1. Stop during sentence 1: audio paused, sentences 2 and 3 never start.
speakSentenceChain(['one', 'two', 'three'], 0, () => started.push('DONE'));
assert(!button.hidden, 'button visible while speaking');
const audio = currentAudio;
stopSpeaking();
assert(audio.paused === true, 'audio paused');
pending.shift()();  // the stopped clip's late 'ended' event must not advance the queue
assert(JSON.stringify(started) === '["one"]', 'queue cancelled');
assert(button.hidden, 'button hidden after stop');

// 2. Stop in the gap between two sentences (nothing playing yet) still cancels the rest.
started.length = 0; pending.length = 0;
speakSentenceChain(['a', 'b'], 0, () => started.push('DONE'));
isSpeaking = false; currentAudio = null;   // sentence 'a' ended, 'b' not started yet
stopSpeaking();
pending.shift()();
assert(JSON.stringify(started) === '["a"]', 'gap stop cancels queue');

// 3. A new request after stopping plays normally.
started.length = 0; pending.length = 0;
speakSentenceChain(['new'], 0, () => started.push('DONE'));
pending.shift()();
assert(JSON.stringify(started) === '["new","DONE"]', 'new reply plays after stop');
assert(button.hidden, 'button hidden once the queue finishes on its own');

// 4. Gemini Live playback is interrupted too.
liveVoiceClient = {{ player: {{ isPlaying: true }}, handleLocalBargeIn() {{ bargeIns.push(1); this.player.isPlaying = false; }} }};
stopSpeaking();
assert(bargeIns.length === 1, 'live playback interrupted');
"""
    result = subprocess.run([NODE, "--input-type=module", "--eval", script], capture_output=True, text=True, cwd=ROOT, check=False)
    assert result.returncode == 0, result.stderr


def test_stop_controls_are_wired():
    src = MAIN.read_text(encoding="utf-8")
    html = (ROOT / "src" / "frontend" / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'id="stop-speaking"' in html
    assert "getElementById('stop-speaking')?.addEventListener('click', stopSpeaking)" in src
    assert "e.key === 'Escape'" in src and "stopSpeaking();" in src
    emergency = _function_source(src, "async function setEmergencyStop(")
    assert "interrumpirAudio();" in emergency and "stopLiveVoiceStream" in emergency
