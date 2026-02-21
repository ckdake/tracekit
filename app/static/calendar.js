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

        return '<div class="provider-status ' + cls + ' ' + providerCls + '" title="' + tooltip + '">' + countHtml + miniCalHtml + deviceHtml + logoHtml + '</div>';
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
