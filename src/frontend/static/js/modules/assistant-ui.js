/**
 * Assistant surface: status bar, suggested commands, approval card, automation settings.
 *
 * Everything shown comes from the backend (/api/security/ai-route, /automation, task
 * state) or is labelled unavailable. API text is rendered with textContent only.
 */

const POLL_MS = 15000;
const CATEGORIES = ['install', 'file_changes', 'delete', 'browser', 'desktop_control', 'clipboard', 'plans'];

export function describeAiRoute(route, t = (k) => k) {
    if (!route || typeof route !== 'object') {
        return { text: t('sb_unavailable'), state: 'unknown', title: '' };
    }
    const chain = Array.isArray(route.chain) ? route.chain : [];
    const last = route.last_answer && route.last_answer.model ? route.last_answer : null;
    const first = chain[0];
    let text;
    if (!route.configured) text = t('sb_ai_not_configured');
    else if (last) text = `${last.provider || '?'} · ${last.model}`;
    else if (first) text = `${first.provider} · ${first.model}`;
    else text = t('sb_unavailable');
    const state = !route.configured ? 'warn' : route.ready ? 'ok' : 'warn';
    const order = chain.map((entry) => `${entry.role}: ${entry.provider} ${entry.model}`).join(' → ');
    const answered = last ? `${t('sb_last_answer')}: ${last.provider} ${last.model}` : '';
    return { text, state, title: [order, answered].filter(Boolean).join('\n') };
}

export function describeMode(route, t = (k) => k) {
    const mode = route?.mode;
    if (!['cloud_first', 'local_first', 'local_only'].includes(mode)) return { text: t('sb_unavailable'), local: false };
    return { text: t(`sb_mode_${mode}`), local: mode === 'local_only' };
}

export function approvalCardView(task, t = (k) => k) {
    if (!task || task.state !== 'approval_required' || !task.approval) return null;
    const steps = Array.isArray(task.approval.steps) ? task.approval.steps : [];
    return {
        taskId: task.id,
        goal: String(task.goal || ''),
        intro: task.approval.scope === 'plan'
            ? t('approval_plan_intro').replace('{n}', String(steps.length))
            : t('approval_step_intro'),
        steps: steps.map((step) => String(step.summary || '')),
    };
}

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
}

export function initAssistantUi({ t, submitCommand, taskAction, fetchImpl = (...a) => fetch(...a) }) {
    const $ = (id) => document.getElementById(id);
    const bar = { ai: $('sb-ai'), aiText: $('sb-ai-text'), mode: $('sb-mode'), modeText: $('sb-mode-text'),
        mic: $('sb-mic'), micText: $('sb-mic-text'), tasks: $('sb-tasks'), tasksText: $('sb-tasks-text') };
    let route = null;

    // ── status bar ────────────────────────────────────────────────
    function renderBar() {
        if (!bar.ai) return;
        const ai = describeAiRoute(route, t);
        bar.aiText.textContent = ai.text;
        bar.ai.dataset.state = ai.state;
        bar.ai.title = ai.title;
        const mode = describeMode(route, t);
        bar.modeText.textContent = mode.text;
        bar.mode.dataset.state = mode.local ? 'local' : 'cloud';
    }

    async function refreshRoute() {
        try {
            const res = await fetchImpl('/api/security/ai-route', { cache: 'no-store' });
            route = res.ok ? await res.json() : null;
        } catch (_) {
            route = null;
        }
        renderBar();
    }

    function setMic(data) {
        if (!bar.mic) return;
        const state = data?.listener_state || 'stopped';
        const name = data?.in_use || '';
        bar.micText.textContent = name ? `${name} · ${t(`sb_mic_${state}`)}` : t(`sb_mic_${state}`);
        bar.mic.dataset.state = state === 'listening' ? 'ok' : state === 'failed' || state === 'reconnecting' ? 'warn' : 'off';
        bar.mic.title = data?.error || '';
    }

    function setTasks(tasks) {
        const list = Array.isArray(tasks) ? tasks : [];
        const open = list.filter((task) => !['completed', 'failed', 'cancelled'].includes(task.state));
        if (bar.tasksText) bar.tasksText.textContent = String(open.length);
        if (bar.tasks) bar.tasks.dataset.state = open.some((task) => task.state === 'approval_required') ? 'warn' : open.length ? 'ok' : 'off';
        renderApprovals(list);
    }

    // ── approval card ─────────────────────────────────────────────
    const card = { root: $('approval-card'), body: $('approval-body'), approve: $('approval-approve'), reject: $('approval-reject') };
    let cardTask = null;
    let cardBusy = false;

    function renderApprovals(tasks) {
        if (!card.root) return;
        const waiting = tasks.filter((task) => task.state === 'approval_required' && !task.active && task.approval);
        if (waiting.length === 0) {
            cardTask = null;
            card.root.classList.add('hidden');
            return;
        }
        // Several waiting: show the newest; the rest stay in the Tasks panel and are not guessed at.
        const view = approvalCardView(waiting[0], t);
        cardTask = view.taskId;
        card.body.replaceChildren(
            el('div', 'approval-goal', view.goal),
            el('div', 'approval-intro', view.intro),
            ...view.steps.map((summary) => el('div', 'approval-step', summary)),
            ...(waiting.length > 1 ? [el('div', 'approval-more', t('approval_more').replace('{n}', String(waiting.length - 1)))] : []),
            el('div', 'approval-hint', t('approval_voice_hint')),
        );
        card.root.classList.remove('hidden');
    }

    async function answer(action) {
        if (!cardTask || cardBusy) return;  // repeated clicks cannot answer twice
        cardBusy = true;
        card.approve.disabled = card.reject.disabled = true;
        try {
            await taskAction(cardTask, action);
        } finally {
            cardBusy = false;
            card.approve.disabled = card.reject.disabled = false;
        }
    }
    card.approve?.addEventListener('click', () => answer('approve'));
    card.reject?.addEventListener('click', () => answer('reject'));

    // ── suggestions ───────────────────────────────────────────────
    document.addEventListener('click', (event) => {
        const chip = event.target.closest?.('.suggestion-chip');
        if (chip?.dataset.command) submitCommand(chip.dataset.command);
    });

    // ── automation settings ───────────────────────────────────────
    const auto = { voice: $('auto-voice'), low: $('auto-low-risk'), once: $('auto-once'), box: $('auto-always'), active: $('auto-approvals'), revoke: $('auto-revoke'),
        status: $('auto-status') };

    function renderAutomation(data) {
        if (!auto.low || !data?.preferences) return;
        if (auto.voice) auto.voice.checked = data.preferences.voice_autostart !== false;
        auto.low.checked = data.preferences.auto_low_risk;
        auto.once.checked = data.preferences.ask_once_per_task;
        auto.box.replaceChildren(...CATEGORIES.map((name) => {
            const label = el('label', 'auto-check');
            const input = document.createElement('input');
            input.type = 'checkbox';
            input.value = name;
            input.checked = data.preferences.always_confirm.includes(name);
            label.append(input, el('span', '', t(`cat_${name}`)));
            return label;
        }));
        const active = Array.isArray(data.active_approvals) ? data.active_approvals : [];
        auto.active.textContent = active.length
            ? active.map((item) => `${t(`cat_${item.category}`)} · ${Math.ceil(item.seconds_left / 60)} min`).join(', ')
            : t('auto_none_active');
    }

    async function loadAutomation() {
        try {
            const res = await fetchImpl('/api/security/automation', { cache: 'no-store' });
            if (res.ok) renderAutomation(await res.json());
        } catch (_) { /* backend restarting */ }
    }

    async function saveAutomation() {
        const body = {
            voice_autostart: auto.voice ? auto.voice.checked : true,
            auto_low_risk: auto.low.checked,
            ask_once_per_task: auto.once.checked,
            always_confirm: [...auto.box.querySelectorAll('input:checked')].map((input) => input.value),
        };
        try {
            const res = await fetchImpl('/api/security/automation', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            const data = await res.json().catch(() => ({}));
            if (auto.status) auto.status.textContent = res.ok ? t('auto_saved') : (data.error || `HTTP ${res.status}`);
            if (res.ok) renderAutomation(data);
        } catch (err) {
            if (auto.status) auto.status.textContent = err.message;
        }
    }
    [auto.voice, auto.low, auto.once].forEach((input) => input?.addEventListener('change', saveAutomation));
    auto.box?.addEventListener('change', saveAutomation);
    auto.revoke?.addEventListener('click', async () => {
        try { await fetchImpl('/api/security/automation/revoke', { method: 'POST' }); } catch (_) { /* ignore */ }
        loadAutomation();
    });

    // Refresh the "answered by" chip after every command, and slowly in the background.
    window.addEventListener('jarvis:command-outcome', () => setTimeout(refreshRoute, 800));
    refreshRoute();
    loadAutomation();
    setInterval(() => { if (!document.hidden) { refreshRoute(); loadAutomation(); } }, POLL_MS);

    return { setMic, setTasks, refreshRoute };
}
