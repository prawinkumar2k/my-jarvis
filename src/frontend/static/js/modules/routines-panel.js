/**
 * Routines panel: scheduled routines (daily summary ...), their next run and latest results.
 * Talks only to /api/security/routines*. Backend text is rendered with textContent only.
 */

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
}

export function describeRoutine(routine, t = (k) => k) {
    const when = String(routine.next_run || '').replace('T', ' ').slice(0, 16);
    const state = routine.enabled ? `${t('rt_next')} ${when}` : t('rt_off');
    return { title: routine.name, detail: `${routine.tool} · ${t(`rt_repeat_${routine.repeat}`)} ${routine.time}`, state };
}

export function initRoutinesPanel({ t, fetchImpl = (...a) => fetch(...a) }) {
    const $ = (id) => document.getElementById(id);
    const ui = { list: $('rt-list'), name: $('rt-name'), time: $('rt-time'), repeat: $('rt-repeat'), tool: $('rt-tool'), add: $('rt-add'),
        last: $('rt-last'), status: $('rt-status'), count: $('rt-count') };
    if (!ui.list) return null;
    const say = (message) => { if (ui.status) ui.status.textContent = message || ''; };

    async function call(path, options) {
        const res = await fetchImpl(path, { cache: 'no-store', ...options });
        return { ok: res.ok, status: res.status, data: await res.json().catch(() => ({})) };
    }

    function render(data) {
        const routines = Array.isArray(data?.routines) ? data.routines : [];
        const results = Array.isArray(data?.results) ? data.results : [];
        if (ui.count) ui.count.textContent = String(routines.filter((r) => r.enabled).length);
        if (Array.isArray(data?.tools) && ui.tool && ui.tool.options.length === 0) {
            ui.tool.replaceChildren(...data.tools.map((name) => { const o = el('option', '', name); o.value = name; return o; }));
        }
        ui.list.replaceChildren(...(routines.length ? routines.map((r) => item(r)) : [el('li', 'control-empty', t('rt_empty'))]));
        const latest = results.slice(-3).reverse();
        ui.last.replaceChildren(...latest.map((r) => {
            const line = el('li', r.ok ? 'rt-ok' : 'rt-fail');
            line.textContent = `${r.at.slice(5, 16).replace('T', ' ')} · ${r.name}${r.missed ? ` (${t('rt_missed')})` : ''}: ${String(r.text).slice(0, 140)}`;
            return line;
        }));
    }

    function item(routine) {
        const view = describeRoutine(routine, t);
        const li = el('li', 'mem-item');
        const info = el('span', 'mem-text');
        info.append(el('b', '', view.title), el('br'), el('small', '', `${view.detail} · ${view.state}`));
        const run = el('button', 'mem-btn', t('rt_run'));
        const del = el('button', 'mem-btn mem-btn-danger', t('rt_delete'));
        run.type = del.type = 'button';
        run.addEventListener('click', async () => {
            const r = await call(`/api/security/routines/${routine.id}/run`, { method: 'POST' });
            say(r.ok ? t('rt_ran') : r.data.error || `HTTP ${r.status}`);
            if (r.ok) render(r.data);
        });
        del.addEventListener('click', async () => {
            const r = await call(`/api/security/routines/${routine.id}/delete`, { method: 'POST' });
            say(r.ok ? t('rt_deleted') : r.data.error || `HTTP ${r.status}`);
            if (r.ok) render(r.data);
        });
        li.append(info, run, del);
        return li;
    }

    async function refresh() {
        try {
            const r = await call('/api/security/routines');
            if (r.ok) render(r.data); else say(t('sb_unavailable'));
        } catch (_) { say(t('sb_unavailable')); }
    }

    ui.add?.addEventListener('click', async () => {
        const r = await call('/api/security/routines', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: ui.name.value, time: ui.time.value, repeat: ui.repeat.value, tool: ui.tool.value }) });
        say(r.ok ? t('rt_added') : r.data.error || `HTTP ${r.status}`);
        if (r.ok) render(r.data);
    });

    refresh();
    setInterval(() => { if (!document.hidden) refresh(); }, 60000);  // picks up results of routines that ran meanwhile
    return { refresh };
}
