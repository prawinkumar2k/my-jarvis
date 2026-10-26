/**
 * Control-panel view of the persistent task engine (/api/security/tasks).
 *
 * Everything shown comes from the API; nothing is invented on the client.
 * Text from tasks (goals, errors, results) is untrusted and is only ever set
 * through textContent. Buttons are offered only for actions the backend will
 * accept, and the backend re-checks eligibility (409) and permissions.
 */

const TERMINAL = new Set(['completed', 'failed', 'cancelled']);

export function describeTask(task) {
    const steps = Array.isArray(task?.steps) ? task.steps : [];
    const done = steps.filter((s) => s.state === 'completed').length;
    const failed = steps.filter((s) => s.state === 'failed' || s.state === 'rejected').length;
    const retries = steps.reduce((sum, s) => sum + Math.max(0, Number(s.attempts || 0) - 1), 0);
    const waiting = steps.find((s) => s.state === 'approval_required') || null;
    const current = steps.find((s) => !['completed', 'failed', 'rejected'].includes(s.state)) || null;
    return {
        done,
        failed,
        total: steps.length,
        retries,
        waiting,
        activeStep: current ? Number(current.idx) + 1 : null,
        running: task?.active === true,
        // A task stored as "running" that this process is not executing is stale (JARVIS restarted).
        stale: task?.state === 'running' && task?.active !== true,
    };
}

export function allowedActions(task) {
    const info = describeTask(task);
    const state = task?.state;
    const actions = [];
    if (state === 'approval_required' && !info.running) actions.push('approve', 'reject');
    if ((state === 'pending' || state === 'interrupted') && !info.running) actions.push('resume');
    if (!TERMINAL.has(state)) actions.push('cancel');
    return actions;
}

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
}

export function renderTasks(container, tasks, { t = (k) => k, busy = new Set(), onAction } = {}) {
    if (!container) return;
    container.replaceChildren();
    const list = Array.isArray(tasks) ? tasks : [];
    if (list.length === 0) {
        container.appendChild(el('div', 'control-empty', t('tasks_empty')));
        return;
    }
    for (const task of list) {
        const info = describeTask(task);
        // Wrapper keeps the action buttons visible; details/history collapse inside it.
        const card = el('div', `task-card task-${task.state}`);
        const body = el('details', 'task-body');
        if (task.state === 'approval_required') body.open = true;
        card.appendChild(body);
        const summary = el('summary', 'task-summary');
        summary.appendChild(el('span', 'task-state', info.stale ? t('task_state_stale') : t(`task_state_${task.state}`)));
        summary.appendChild(el('span', 'task-goal', task.goal));
        summary.appendChild(el('span', 'task-progress', `${info.done}/${info.total}`));
        body.appendChild(summary);

        const meta = el('div', 'task-meta hud-font-alt');
        const facts = [
            `ID ${task.id}`,
            info.activeStep ? `${t('task_step')} ${info.activeStep}/${info.total}` : null,
            info.failed ? `${t('task_failed_steps')} ${info.failed}` : null,
            info.retries ? `${t('task_retries')} ${info.retries}` : null,
            task.started ? `${t('task_started')} ${task.started}` : null,
            task.finished ? `${t('task_finished')} ${task.finished}` : null,
        ].filter(Boolean);
        meta.textContent = facts.join(' · ');
        body.appendChild(meta);
        if (info.waiting) {
            body.appendChild(el('div', 'task-approval', `${t('task_needs_approval')}: ${info.waiting.tool} ${JSON.stringify(info.waiting.args || {})}`));
        }
        if (task.error) body.appendChild(el('div', 'task-error', task.error));

        const history = el('ol', 'task-steps');
        for (const step of task.steps || []) {
            const line = `${step.tool} — ${t(`task_state_${step.state}`)}${Number(step.attempts) > 1 ? ` (${step.attempts}×)` : ''}`;
            const item = el('li', `task-step step-${step.state}`, line);
            if (step.error) item.appendChild(el('div', 'task-error', step.error));
            history.appendChild(item);
        }
        body.appendChild(history);

        const actions = allowedActions(task);
        if (actions.length) {
            const row = el('div', 'task-actions');
            for (const action of actions) {
                const button = el('button', `tech-btn task-btn task-btn-${action}`, t(`task_action_${action}`));
                button.type = 'button';
                button.disabled = busy.has(task.id);
                button.addEventListener('click', () => onAction?.(task.id, action));
                row.appendChild(button);
            }
            card.appendChild(row);
        }
        container.appendChild(card);
    }
}
