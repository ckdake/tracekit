// Calendar page logic.
// Expects `PROVIDER_CONFIG` to be defined inline before this script loads.
/* global PROVIDER_CONFIG */

// ── Render a card's provider grid from API data ───────────────────────────────
function renderGrid(yearMonth, data) {
    const grid    = document.getElementById('grid-'  + yearMonth);
    const totalEl = document.getElementById('total-' + yearMonth);
    if (!grid) return;

    if (data.error) {
        grid.innerHTML = '<div class="card-loading" style="color:#dc3545">' + data.error + '</div>';
        return;
    }
    if (!data.providers || data.providers.length === 0) {
        grid.innerHTML = '<div class="card-loading">No providers</div>';
        return;
    }

    if (data.total_activities > 0) {
        totalEl.textContent = data.total_activities + ' total activities';
    }

    grid.innerHTML = data.providers.map(p => {
        const synced  = data.provider_status[p];
        const cfg     = PROVIDER_CONFIG[p] || {};
        const enabled = cfg.enabled !== false;
        const cls     = !enabled ? 'disabled' : synced ? 'synced' : 'not-synced';
        const count   = data.activity_counts[p] || 0;
        const countHtml = count > 0 ? '<div class="activity-count">' + count + ' activities</div>' : '';
        return '<div class="provider-status ' + cls + '"><div>' + p.substring(0, 8) + '</div>' + countHtml + '</div>';
    }).join('');
}

// ── Load (or reload) a single card via API ────────────────────────────────────
async function loadCard(yearMonth) {
    try {
        const res  = await fetch('/api/calendar/' + yearMonth);
        const data = await res.json();
        renderGrid(yearMonth, data);
    } catch (e) {
        const grid = document.getElementById('grid-' + yearMonth);
        if (grid) grid.innerHTML = '<div class="card-loading" style="color:#dc3545">Load error</div>';
    }
}

// ── Pull a month and refresh the card ─────────────────────────────────────────
const _polling = {};

async function pullMonth(btn) {
    const month  = btn.dataset.month;
    const status = document.getElementById('status-' + month);

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Queuing…';
    status.textContent = '';
    status.className = 'pull-status';

    let taskId;
    try {
        const res  = await fetch('/api/sync/' + month, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
            status.textContent = data.error || 'Error';
            status.className = 'pull-status err';
            btn.disabled = false;
            btn.textContent = 'Pull';
            return;
        }
        taskId = data.task_id;
    } catch (e) {
        status.textContent = 'Network error';
        status.className = 'pull-status err';
        btn.disabled = false;
        btn.textContent = 'Pull';
        return;
    }

    btn.innerHTML = '<span class="spinner"></span>Running…';
    status.textContent = 'In progress';
    status.className = 'pull-status running';

    _polling[month] = setInterval(async () => {
        try {
            const res  = await fetch('/api/sync/status/' + taskId);
            const data = await res.json();
            if (data.state === 'SUCCESS') {
                clearInterval(_polling[month]);
                btn.disabled = false;
                btn.textContent = 'Pull';
                status.textContent = 'Done ✓';
                status.className = 'pull-status ok';
                loadCard(month);
            } else if (data.state === 'FAILURE') {
                clearInterval(_polling[month]);
                btn.disabled = false;
                btn.textContent = 'Pull';
                status.textContent = data.info || 'Failed';
                status.className = 'pull-status err';
            }
            // PENDING / STARTED / RETRY — keep spinning
        } catch (_) { /* ignore transient fetch errors */ }
    }, 2000);
}

// ── On page load: fetch all cards in parallel ─────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.month-card[id^="card-"]').forEach(card => {
        loadCard(card.id.replace('card-', ''));
    });
});
