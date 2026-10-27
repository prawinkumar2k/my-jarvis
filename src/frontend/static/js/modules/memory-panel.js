/**
 * Memory panel: see, search, add, edit, forget, export, clear and private mode.
 * Talks only to /api/security/memory*. Memory text is rendered with textContent only.
 */

const CONFIRM_WINDOW_MS = 5000;

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
}

export function initMemoryPanel({ t, fetchImpl = (...a) => fetch(...a) }) {
    const $ = (id) => document.getElementById(id);
    const ui = { list: $('mem-list'), count: $('mem-count'), search: $('mem-search'), add: $('mem-add'), input: $('mem-new'),
        priv: $('mem-private'), exportBtn: $('mem-export'), clear: $('mem-clear'), status: $('mem-status') };
    if (!ui.list) return null;
    let clearArmedUntil = 0;
    let clearTimer = null;

    const say = (message) => { if (ui.status) ui.status.textContent = message || ''; };

    async function call(path, options) {
        const res = await fetchImpl(path, { cache: 'no-store', ...options });
        const data = await res.json().catch(() => ({}));
        return { ok: res.ok, status: res.status, data };
    }

    function render(data) {
        if (!data) return;
        if (ui.count) ui.count.textContent = String(data.count ?? 0);
        if (ui.priv) ui.priv.checked = data.private_mode === true;
        const facts = Array.isArray(data.facts) ? data.facts : [];
        ui.list.replaceChildren(...(facts.length ? facts.map(row) : [el('li', 'control-empty', t(ui.search.value ? 'mem_no_match' : 'mem_empty'))]));
    }

    function row(fact) {
        const item = el('li', 'mem-item');
        const text = el('span', 'mem-text', fact.text);
        const edit = el('button', 'mem-btn', t('mem_edit'));
        const forget = el('button', 'mem-btn mem-btn-danger', t('mem_forget'));
        edit.type = forget.type = 'button';
        edit.addEventListener('click', () => startEdit(item, fact));
        forget.addEventListener('click', async () => {
            const r = await call(`/api/security/memory/${fact.n}/delete`, { method: 'POST' });
            say(r.ok ? t('mem_forgotten') : r.data.message || r.data.error || `HTTP ${r.status}`);
            render(r.data);
        });
        item.append(text, edit, forget);
        return item;
    }

    function startEdit(item, fact) {
        const input = el('input', 'mem-input');
        input.type = 'text';
        input.maxLength = 500;
        input.value = fact.text;
        const save = el('button', 'mem-btn', t('mem_save'));
        const cancel = el('button', 'mem-btn', t('mem_cancel'));
        save.type = cancel.type = 'button';
        const finish = async () => {
            const r = await call(`/api/security/memory/${fact.n}/edit`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: input.value }) });
            say(r.ok ? t('mem_saved') : r.data.message || r.data.error || `HTTP ${r.status}`);
            if (r.ok) render(r.data); else input.focus();
        };
        save.addEventListener('click', finish);
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); finish(); } });
        cancel.addEventListener('click', refresh);
        item.replaceChildren(input, save, cancel);
        input.focus();
    }

    async function refresh() {
        try {
            const r = await call(`/api/security/memory?q=${encodeURIComponent(ui.search?.value || '')}`);
            if (r.ok) render(r.data); else say(t('sb_unavailable'));
        } catch (_) { say(t('sb_unavailable')); }
    }

    ui.search?.addEventListener('input', refresh);
    ui.add?.addEventListener('click', async () => {
        const text = (ui.input.value || '').trim();
        if (!text) return;
        const r = await call('/api/security/memory', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
        say(r.ok ? t('mem_added') : r.data.message || r.data.error || `HTTP ${r.status}`);
        if (r.ok) ui.input.value = '';
        render(r.data);
    });
    ui.input?.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); ui.add.click(); } });

    ui.priv?.addEventListener('change', async () => {
        const r = await call('/api/security/memory/private', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: ui.priv.checked }) });
        say(r.ok ? t(r.data.private_mode ? 'mem_private_on' : 'mem_private_off') : r.data.error || `HTTP ${r.status}`);
        refresh();
    });

    ui.exportBtn?.addEventListener('click', async () => {
        try {
            const res = await fetchImpl('/api/security/memory/export', { cache: 'no-store' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const url = URL.createObjectURL(await res.blob());
            const link = el('a');
            link.href = url;
            link.download = 'jarvis-memory.json';
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 4000);
            say(t('mem_exported'));
        } catch (err) { say(err.message); }
    });

    // "Forget all" needs a second click within a few seconds, then the backend still needs the exact phrase.
    ui.clear?.addEventListener('click', async () => {
        if (Date.now() > clearArmedUntil) {
            clearArmedUntil = Date.now() + CONFIRM_WINDOW_MS;
            ui.clear.textContent = t('mem_clear_confirm');
            clearTimeout(clearTimer);
            clearTimer = setTimeout(() => { ui.clear.textContent = t('mem_clear'); clearArmedUntil = 0; }, CONFIRM_WINDOW_MS);
            return;
        }
        clearArmedUntil = 0;
        clearTimeout(clearTimer);
        ui.clear.textContent = t('mem_clear');
        const r = await call('/api/security/memory/clear', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirm: 'DELETE ALL' }) });
        say(r.ok ? t('mem_cleared').replace('{n}', String(r.data.removed ?? 0)) : r.data.error || `HTTP ${r.status}`);
        render(r.data);
    });

    // Memories can also change by talking to JARVIS ("remember that ..."): refresh after each command.
    window.addEventListener('jarvis:command-outcome', () => setTimeout(refresh, 1200));
    refresh();
    return { refresh };
}
