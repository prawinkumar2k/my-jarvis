/**
 * Setup check panel: runs /api/security/setup-check and lists each result with the exact fix.
 * Read-only: it only shows information; backend text is rendered with textContent.
 */

export function initSetupPanel({ t, fetchImpl = (...a) => fetch(...a) }) {
    const $ = (id) => document.getElementById(id);
    const ui = { run: $('sc-run'), list: $('sc-list'), summary: $('sc-summary') };
    if (!ui.run) return null;
    let busy = false;

    function render(data) {
        const checks = Array.isArray(data?.checks) ? data.checks : [];
        ui.list.replaceChildren(...checks.map((c) => {
            const li = document.createElement('li');
            li.className = `sc-item sc-${c.status}`;
            const head = document.createElement('div');
            head.className = 'sc-head';
            head.textContent = `${t(`sc_${c.status}`)} · ${c.label}`;
            const detail = document.createElement('div');
            detail.className = 'sc-detail';
            detail.textContent = c.detail;
            li.append(head, detail);
            if (c.fix) {
                const fix = document.createElement('div');
                fix.className = 'sc-fix';
                fix.textContent = `${t('sc_fix')}: ${c.fix}`;
                li.append(fix);
            }
            return li;
        }));
        const s = data?.summary || {};
        ui.summary.textContent = checks.length
            ? t('sc_summary').replace('{ok}', s.ok ?? 0).replace('{warn}', s.warn ?? 0).replace('{missing}', s.missing ?? 0)
            : '';
    }

    ui.run.addEventListener('click', async () => {
        if (busy) return;  // one check at a time
        busy = true;
        ui.run.disabled = true;
        ui.summary.textContent = t('sc_running');
        try {
            const res = await fetchImpl('/api/security/setup-check', { cache: 'no-store' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            render(await res.json());
        } catch (err) {
            ui.list.replaceChildren();
            ui.summary.textContent = `${t('sb_unavailable')} (${err.message})`;
        } finally {
            busy = false;
            ui.run.disabled = false;
        }
    });
    return { run: () => ui.run.click() };
}
