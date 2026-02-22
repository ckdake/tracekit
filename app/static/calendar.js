// Calendar page logic.
// Expects `PROVIDER_CONFIG` and `INITIAL_OLDEST` to be defined inline before this script loads.
/* global PROVIDER_CONFIG, INITIAL_OLDEST */

let oldestLoaded = INITIAL_OLDEST || null;

// ── Build a mini SMTWRFS calendar grid HTML for one provider ─────────────────
function buildMiniCal(yearMonth, activeDays) {
    const [year, month] = yearMonth.split('-').map(Number);
    const firstDow  = new Date(year, month - 1, 1).getDay(); // 0=Sun
    const totalDays = new Date(year, month, 0).getDate();
    const activeSet = new Set(activeDays || []);

    // Header row
    let html = '<div class="mini-cal">'
             + '<div class="mini-cal-head">'
             + ['S','M','T','W','R','F','S'].map(d => '<span>' + d + '</span>').join('')
             + '</div><div class="mini-cal-body">';

    // Blank cells before the 1st
    for (let i = 0; i < firstDow; i++) {
        html += '<span class="mc-empty"></span>';
    }
    // Day cells
    for (let d = 1; d <= totalDays; d++) {
        html += activeSet.has(d)
            ? '<span class="mc-dot mc-active"></span>'
            : '<span class="mc-dot mc-empty"></span>';
    }
    html += '</div></div>';
    return html;
}

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

    const counts = Object.values(data.activity_counts || {});
    const maxCount = counts.length ? Math.max(...counts) : 0;
    if (maxCount > 0) {
        totalEl.textContent = maxCount + ' activities';
    }

    const enabledProviders = data.providers.filter(p => {
        const cfg = PROVIDER_CONFIG[p] || {};
        return cfg.enabled !== false;
    });

    if (enabledProviders.length === 0) {
        grid.innerHTML = '<div class="card-loading">No active providers</div>';
        return;
    }

    const PROVIDER_DISPLAY = {
        strava:      { cls: 'provider-strava',      label: 'Strava',       logo: '/static/powered_by_strava.svg',      logoAlt: 'Powered by Strava',      logoHref: 'https://www.strava.com' },
        garmin:      { cls: 'provider-garmin',      label: 'Garmin',       logo: '/static/powered_by_garmin.svg',      logoAlt: 'Powered by Garmin',      logoHref: 'https://www.garmin.com' },
        stravajson:  { cls: 'provider-strava',      label: 'Strava (JSON)',logo: '/static/powered_by_strava.svg',      logoAlt: 'Powered by Strava',      logoHref: 'https://www.strava.com' },
        ridewithgps: { cls: 'provider-ridewithgps', label: 'RideWithGPS',  logo: '/static/powered_by_ridewithgps.svg', logoAlt: 'Powered by RideWithGPS', logoHref: 'https://ridewithgps.com' },
        spreadsheet: { cls: 'provider-spreadsheet', label: 'Spreadsheet',  logo: '', logoAlt: 'Spreadsheet' },
        file:        { cls: 'provider-file',        label: 'File',         logo: '', logoAlt: 'File' },
    };

    const meta = data.provider_metadata || {};

    grid.innerHTML = enabledProviders.map(p => {
        const synced      = data.provider_status[p];
        const cls         = synced ? 'synced' : 'not-synced';
        const tooltip     = synced ? 'Synced' : 'Not synced';
        const count       = data.activity_counts[p] || 0;
        const info        = PROVIDER_DISPLAY[p] || {};
        const providerCls = info.cls || '';
        const pullStatus  = data.pull_statuses && data.pull_statuses[p];
        const isActive    = pullStatus && (pullStatus.status === 'queued' || pullStatus.status === 'started');

        // Big integer count (no label)
        const countHtml = count > 0 ? '<div class="activity-count-big">' + count + '</div>' : '';

        // Mini calendar grid
        const activeDays = (data.activity_days && data.activity_days[p]) ? data.activity_days[p] : [];
        const miniCalHtml = synced ? buildMiniCal(yearMonth, activeDays) : '';

        // Device chip (Garmin-only)
        const devices = (synced && meta[p] && meta[p].devices) ? meta[p].devices : [];
        const deviceHtml = devices.length
            ? '<div class="provider-devices">' + devices.map(d => '<span class="device-chip">⌚ ' + d + '</span>').join('') + '</div>'
            : '';

        // Logo or fallback text label at bottom
        const logoHtml = info.logo
            ? '<div class="provider-logo-row"><a href="' + info.logoHref + '" target="_blank" rel="noopener"><img src="' + info.logo + '" alt="' + info.logoAlt + '" class="provider-logo-img"></a></div>'
            : '<div class="provider-name-label">' + (info.label || p) + '</div>';

        // Status label shown in the chiclet footer
        let statusHtml = '';
        if (pullStatus) {
            if (pullStatus.status === 'queued') {
                statusHtml = '<span class="pcs pcs-active"><span class="pcs-spinner"></span>queued</span>';
            } else if (pullStatus.status === 'started') {
                statusHtml = '<span class="pcs pcs-active"><span class="pcs-spinner"></span>syncing</span>';
            } else if (pullStatus.status === 'error') {
                const msg = (pullStatus.message || 'error').replace(/"/g, '&quot;').substring(0, 120);
                statusHtml = '<span class="pcs pcs-error" title="' + msg + '">⚠ error</span>';
            }
        }

        // Footer strip: status on left, pull button on right.
        // File provider has no per-month pull — only show footer if there is a status to display.
        let footerHtml = '';
        if (p !== 'file') {
            const isSuccess = pullStatus && pullStatus.status === 'success';
            const btnContent = isActive   ? '<span class="spinner spinner-sm"></span>'
                             : isSuccess  ? '<span class="btn-icon-check">✓</span><span class="btn-icon-pull">⬇</span>'
                             : pullStatus && pullStatus.status === 'error' ? '✗'
                             : '⬇';
            const btnClass = 'provider-pull-btn' + (isSuccess ? ' pull-btn-success' : '');
            const btnDisabled = isActive ? ' disabled' : '';
            const pullBtn = '<button class="' + btnClass + '"' + btnDisabled
                + ' data-month="' + yearMonth + '" data-provider="' + p
                + '" onclick="pullProviderMonth(this)" title="Pull ' + (info.label || p) + '">'
                + btnContent + '</button>';
            footerHtml = '<div class="provider-footer">' + statusHtml + pullBtn + '</div>';
        } else if (statusHtml) {
            footerHtml = '<div class="provider-footer">' + statusHtml + '</div>';
        }

        return '<div class="provider-status ' + cls + ' ' + providerCls + '" title="' + tooltip + '">'
            + '<div class="provider-content">' + countHtml + miniCalHtml + deviceHtml + logoHtml + '</div>'
            + footerHtml
            + '</div>';
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

// ── Exponential-backoff task poller ──────────────────────────────────────────
// Polls /api/sync/status/<taskId> with increasing delays.
//   initialDelay  – ms before first check  (default 2 s)
//   maxDelay      – cap on any single delay (default 5 min)
//   maxElapsed    – give-up wall-clock time  (default 60 min)
function pollTaskStatus(taskId, { onSuccess, onFailure, onTimeout,
                                  initialDelay = 2000, maxDelay = 300000,
                                  maxElapsed = 3600000 } = {}) {
    const start = Date.now();
    let delay = initialDelay;

    function schedule() {
        setTimeout(async () => {
            try {
                const res  = await fetch('/api/sync/status/' + taskId);
                const data = await res.json();
                if (data.state === 'SUCCESS') { onSuccess && onSuccess(data); return; }
                if (data.state === 'FAILURE') { onFailure && onFailure(data); return; }
                // PENDING / STARTED / RETRY — fall through to reschedule
            } catch (_) { /* ignore transient fetch errors */ }

            const elapsed = Date.now() - start;
            if (elapsed + delay >= maxElapsed) { onTimeout && onTimeout(); return; }
            delay = Math.min(delay * 2, maxDelay);
            schedule();
        }, delay);
    }

    schedule();
}

// ── Pull a month and refresh the card ─────────────────────────────────────────

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

    pollTaskStatus(taskId, {
        onSuccess: () => {
            btn.disabled = false;
            btn.textContent = '⬇';
            status.textContent = 'Done ✓';
            status.className = 'pull-status ok';
            loadCard(month);
            setTimeout(() => { status.textContent = ''; status.className = 'pull-status'; }, 30000);
        },
        onFailure: (data) => {
            btn.disabled = false;
            btn.textContent = '⬇';
            status.textContent = data.info || 'Failed';
            status.className = 'pull-status err';
        },
        onTimeout: () => {
            btn.disabled = false;
            btn.textContent = '⬇';
            status.textContent = 'Timed out – try again';
            status.className = 'pull-status err';
        },
    });
}

// ── Pull a single provider for a month and refresh the card ──────────────────
async function pullProviderMonth(btn) {
    const month    = btn.dataset.month;
    const provider = btn.dataset.provider;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner spinner-sm"></span>';

    let taskId;
    try {
        const res  = await fetch('/api/sync/' + month + '/' + provider, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
            btn.disabled = false;
            btn.textContent = '✗';
            return;
        }
        taskId = data.task_id;
    } catch (e) {
        btn.disabled = false;
        btn.textContent = '✗';
        return;
    }

    pollTaskStatus(taskId, {
        onSuccess: () => {
            btn.disabled = false;
            btn.textContent = '✓';
            loadCard(month);
        },
        onFailure: () => {
            btn.disabled = false;
            btn.textContent = '✗';
        },
        onTimeout: () => {
            btn.disabled = false;
            btn.textContent = '✗';
        },
    });
}

// ── Reset a month and refresh the card ────────────────────────────────────────
function resetMonth(btn) {
    const month  = btn.dataset.month;
    const status = document.getElementById('status-' + month);

    // Show inline confirmation
    btn.disabled = true;
    status.className = 'pull-status confirm';
    status.innerHTML =
        'Reset ' + month + '? ' +
        '<button class="confirm-yes" onclick="confirmResetMonth(\'' + month + '\', true)">Yes</button>' +
        '<button class="confirm-no"  onclick="confirmResetMonth(\'' + month + '\', false)">No</button>';
}

async function confirmResetMonth(month, confirmed) {
    const status  = document.getElementById('status-' + month);
    const card    = document.getElementById('card-' + month);
    const resetBtn = card ? card.querySelector('.reset-btn') : null;

    if (!confirmed) {
        if (resetBtn) resetBtn.disabled = false;
        status.textContent = '';
        status.className = 'pull-status';
        return;
    }

    if (resetBtn) {
        resetBtn.innerHTML = '<span class="spinner spinner-sm"></span>';
    }
    status.textContent = 'Resetting…';
    status.className = 'pull-status running';

    let taskId;
    try {
        const res  = await fetch('/api/reset/' + month, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
            status.textContent = data.error || 'Error';
            status.className = 'pull-status err';
            if (resetBtn) { resetBtn.disabled = false; resetBtn.textContent = '↺'; }
            return;
        }
        taskId = data.task_id;
    } catch (e) {
        status.textContent = 'Network error';
        status.className = 'pull-status err';
        if (resetBtn) { resetBtn.disabled = false; resetBtn.textContent = '↺'; }
        return;
    }

    pollTaskStatus(taskId, {
        onSuccess: () => {
            if (resetBtn) { resetBtn.disabled = false; resetBtn.textContent = '↺'; }
            status.textContent = 'Reset ✓';
            status.className = 'pull-status ok';
            loadCard(month);
            setTimeout(() => { status.textContent = ''; status.className = 'pull-status'; }, 30000);
        },
        onFailure: (data) => {
            if (resetBtn) { resetBtn.disabled = false; resetBtn.textContent = '↺'; }
            status.textContent = data.info || 'Reset failed';
            status.className = 'pull-status err';
        },
        onTimeout: () => {
            if (resetBtn) { resetBtn.disabled = false; resetBtn.textContent = '↺'; }
            status.textContent = 'Timed out – try again';
            status.className = 'pull-status err';
        },
    });
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
                <div class="month-btn-group">
                    <button class="pull-btn" data-month="${ym}" onclick="pullMonth(this)" title="Pull">⬇</button>
                    <button class="reset-btn" data-month="${ym}" onclick="resetMonth(this)" title="Reset month data">↺</button>
                </div>
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
