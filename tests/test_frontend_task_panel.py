"""Task control panel logic, run in Node against the real module (DOM is a tiny stub)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "frontend" / "static" / "js" / "modules" / "task-panel.js"
NODE = shutil.which("node")


def _run(body: str) -> None:
    script = f"import * as panel from {json.dumps(MODULE.resolve().as_uri())};\n{body}\n"
    result = subprocess.run([NODE, "--input-type=module", "--eval", script], capture_output=True, text=True, cwd=ROOT, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(NODE is None, reason="node is required")
def test_actions_match_backend_eligibility():
    _run("""
const assert = (ok, msg) => { if (!ok) { console.error(msg); process.exit(1); } };
const step = (state, extra = {}) => ({ idx: 0, tool: 'x', state, attempts: 1, args: {}, ...extra });
const acts = (task) => panel.allowedActions(task).join(',');
assert(acts({ state: 'approval_required', steps: [step('approval_required')] }) === 'approve,reject,cancel', 'approval');
assert(acts({ state: 'interrupted', steps: [step('pending')] }) === 'resume,cancel', 'interrupted');
assert(acts({ state: 'running', active: true, steps: [step('running')] }) === 'cancel', 'running: no resume');
assert(acts({ state: 'pending', active: true, steps: [] }) === 'cancel', 'active: no second run');
for (const s of ['completed', 'failed', 'cancelled']) assert(acts({ state: s, steps: [] }) === '', s);
""")


@pytest.mark.skipif(NODE is None, reason="node is required")
def test_progress_retries_and_stale_running_tasks():
    _run("""
const assert = (ok, msg) => { if (!ok) { console.error(msg); process.exit(1); } };
const info = panel.describeTask({ state: 'running', active: false, steps: [
  { idx: 0, state: 'completed', attempts: 3 }, { idx: 1, state: 'failed', attempts: 1 }, { idx: 2, state: 'pending', attempts: 0 } ] });
assert(info.done === 1 && info.failed === 1 && info.total === 3, 'counts');
assert(info.retries === 2, 'retries = extra attempts');
assert(info.activeStep === 3, 'active step is the first unfinished one');
assert(info.stale === true, 'running in DB but not in this process = stale after restart');
""")


@pytest.mark.skipif(NODE is None, reason="node is required")
def test_task_text_is_rendered_as_text_not_html():
    _run("""
const assert = (ok, msg) => { if (!ok) { console.error(msg); process.exit(1); } };
const nodes = [];
const make = (tag) => { const n = { tag, children: [], className: '', textContent: '', set innerHTML(v) { throw new Error('innerHTML used'); },
  appendChild(c) { this.children.push(c); return c; }, replaceChildren() { this.children = []; }, addEventListener(e, f) { this.on = f; } }; nodes.push(n); return n; };
globalThis.document = { createElement: make };
const box = make('div');
const evil = '<img src=x onerror=alert(1)>';
const clicks = [];
panel.renderTasks(box, [{ id: 't1', goal: evil, state: 'approval_required', error: evil,
  steps: [{ idx: 0, tool: 'eliminar_archivo', state: 'approval_required', attempts: 0, args: { ruta: evil } }] }],
  { onAction: (id, a) => clicks.push(id + ':' + a), busy: new Set() });
assert(nodes.some((n) => n.textContent === evil), 'goal shown verbatim as text');
const buttons = nodes.filter((n) => n.tag === 'button');
assert(buttons.map((b) => b.textContent).join(',') === 'task_action_approve,task_action_reject,task_action_cancel', 'buttons');
buttons[0].on(); assert(clicks[0] === 't1:approve', 'click wires action');
const busyBox = make('div'); nodes.length = 0;
panel.renderTasks(busyBox, [{ id: 't1', goal: 'g', state: 'approval_required', steps: [] }], { busy: new Set(['t1']) });
assert(nodes.filter((n) => n.tag === 'button').every((b) => b.disabled), 'buttons disabled while a request is in flight');
""")
