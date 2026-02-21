// Calendar page logic.
// Expects `PROVIDER_CONFIG` and `INITIAL_OLDEST` to be defined inline before this script loads.
/* global PROVIDER_CONFIG, INITIAL_OLDEST */

let oldestLoaded = INITIAL_OLDEST || null;

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

    const enabledProviders = data.providers.filter(p => {
        const cfg = PROVIDER_CONFIG[p] || {};
        return cfg.enabled !== false;
    });

    if (enabledProviders.length === 0) {
        grid.innerHTML = '<div class="card-loading">No active providers</div>';
        return;
    }

    grid.innerHTML = enabledProviders.map(p => {
        const synced  = data.provider_status[p];
        const cls     = synced ? 'synced' : 'not-synced';
        const tooltip = synced ? 'Synced' : 'Not synced';
        const count   = data.activity_counts[p] || 0;
        const countHtml = count > 0 ? '<div class="activity-count">' + count + ' activities</div>' : '';
        return '<div class="provider-status ' + cls + '" title="' + tooltip + '"><div>' + p.substring(0, 8) + '</div>' + countHtml + '</div>';
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
    btn.innerHTML = '<span class="spinner spinner-sm"></span>';
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
            btn.textContent = '⬇';
            return;
        }
        taskId = data.task_id;
    } catch (e) {
        status.textContent = 'Network error';
        status.className = 'pull-status err';
        btn.disabled = false;
        btn.textContent = '⬇';
        return;
    }

    btn.innerHTML = '<span class="spinner spinner-sm"></span>';
    status.textContent = 'In progress';
    status.className = 'pull-status running';

    _polling[month] = setInterval(async () => {
        try {
            const res  = await fetch('/api/sync/status/' + taskId);
            const data = await res.json();
            if (data.state === 'SUCCESS') {
                clearInterval(_polling[month]);
                btn.disabled = false;
                btn.textContent = '⬇';
                status.textContent = 'Done ✓';
                status.className = 'pull-status ok';
                loadCard(month);
            } else if (data.state === 'FAILURE') {
                clearInterval(_polling[month]);
                btn.disabled = false;
                btn.textContent = '⬇';
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
// ── Append a month card to the grid ────────────────────────────────────────────────
function appendMonthCard(ym, year, month) {
    const monthName = new Date(year, month - 1, 1).toLocaleString('default', { month: 'long' });
    const div = document.createElement('div');
    div.className = 'month-card';
    div.id = 'card-' + ym;
    div.innerHTML = `
        <div class="month-header">
            <div class="month-title-row">
                <span>${monthName} ${year}</span>
                <button class="pull-btn" data-month="${ym}" onclick="pullMonth(this)" title="Pull">⬇</button>
            </div>
            <div class="total-label" id="total-${ym}"></div>
        </div>
        <div class="provider-grid" id="grid-${ym}">
            <div class="card-loading">Loading…</div>
        </div>
        <div class="pull-status" id="status-${ym}"></div>`;
    document.getElementById('calendar-grid').appendChild(div);
}

// ── Load 12 more months going back in time ────────────────────────────────────────
function loadMoreMonths() {
    if (!oldestLoaded) return;
    let [y, m] = oldestLoaded.split('-').map(Number);
    for (let i = 0; i < 12; i++) {
        m--;
        if (m === 0) { m = 12; y--; }
        const ym = `${String(y).padStart(4, '0')}-${String(m).padStart(2, '0')}`;
        appendMonthCard(ym, y, m);
        loadCard(ym);
        oldestLoaded = ym;
    }
}
