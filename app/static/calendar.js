// Calendar page logic.
// Expects `PROVIDER_CONFIG`, `INITIAL_OLDEST`, `OLDEST_ACTIVITY_MONTH`, and `HOME_TIMEZONE` to be defined inline before this script loads.
/* global PROVIDER_CONFIG, INITIAL_OLDEST, OLDEST_ACTIVITY_MONTH, HOME_TIMEZONE */

// ── Format a Unix timestamp in the user's home timezone ──────────────────────
function formatSyncTime(ts) {
    if (!ts) return '';
    try {
        return new Intl.DateTimeFormat('en-US', {
            timeZone: HOME_TIMEZONE,
            month: 'short', day: 'numeric',
            hour: 'numeric', minute: '2-digit', hour12: false,
        }).format(new Date(ts * 1000));
    } catch (_) {
        return new Date(ts * 1000).toLocaleString();
    }
}

let oldestLoaded = INITIAL_OLDEST || null;
let _loadingMore  = false;

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

    // Show all providers enabled in config (even before first pull), plus any
    // with existing data that are still enabled.
    const enabledProviders = [...new Set([
        ...Object.keys(PROVIDER_CONFIG).filter(p => PROVIDER_CONFIG[p] && PROVIDER_CONFIG[p].enabled),
        ...(data.providers || []),
    ])].filter(p => (PROVIDER_CONFIG[p] || {}).enabled !== false);

    if (enabledProviders.length === 0) {
        grid.innerHTML = '<div class="card-loading">No active providers</div>';
        return;
    }

    const maxCount = Math.max(0, ...enabledProviders.map(p => data.activity_counts[p] || 0));
    totalEl.textContent = maxCount > 0 ? maxCount + ' activities' : '';
    const syncStatus = data.month_sync_status;

    // Update the timeline rail dot and the month card status ring.
    const _ringCls = syncStatus === 'synced' ? 'ok' : syncStatus === 'requires_action' ? 'warn' : 'pending';

    const tlLink = document.querySelector(`.timeline-month[href="#card-${yearMonth}"]`);
    if (tlLink) {
        const dot = tlLink.querySelector('.tl-dot');
        if (dot) dot.className = 'tl-dot ' + _ringCls;
    }

    const RING_ICONS = {
        ok:      '<polyline points="20 6 9 17 4 12"/>',
        warn:    '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
        pending: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    };
    const ringEl = document.getElementById('ring-' + yearMonth);
    if (ringEl) {
        ringEl.className = 'month-status-ring ' + _ringCls;
        ringEl.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="20" height="20">${RING_ICONS[_ringCls]}</svg>`;
    }

    const PROVIDER_DISPLAY = {
        strava:       { cls: 'provider-strava',       label: 'Strava' },
        garmin:       { cls: 'provider-garmin',       label: 'Garmin' },
        ridewithgps:  { cls: 'provider-ridewithgps',  label: 'RideWithGPS' },
        intervalsicu: { cls: 'provider-intervalsicu', label: 'Intervals.icu' },
        spreadsheet:  { cls: 'provider-spreadsheet',  label: 'Spreadsheet' },
        file:         { cls: 'provider-file',         label: 'File' },
        stravajson:   { cls: 'provider-strava',       label: 'Strava JSON' },
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

        // Big integer count (no label) — always shown, even for 0
        const countHtml = '<div class="activity-count-big">' + count + '</div>';

        // Mini calendar grid — always shown; dots are off when activeDays is empty
        const activeDays = (data.activity_days && data.activity_days[p]) ? data.activity_days[p] : [];
        const miniCalHtml = buildMiniCal(yearMonth, activeDays);

        // Device chip (Garmin-only)
        const devices = (synced && meta[p] && meta[p].devices) ? meta[p].devices : [];
        const deviceHtml = devices.length
            ? '<div class="provider-devices">' + devices.map(d => '<span class="device-chip">⌚ ' + d + '</span>').join('') + '</div>'
            : '';

        // Provider name at the top
        const nameHtml = '<div class="provider-name-label">' + (info.label || p) + '</div>';

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

        // Sync timestamp shown in footer when not actively syncing
        const syncTime = (!isActive && pullStatus && pullStatus.updated_at)
            ? formatSyncTime(pullStatus.updated_at) : '';
        const syncTimeHtml = syncTime
            ? '<span class="pcs-sync-time">' + syncTime + '</span>' : '';

        // Footer strip: status/time on left, pull button on right.
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
        const footerHtml = '<div class="provider-footer">'
            + (statusHtml || syncTimeHtml) + pullBtn + '</div>';

        return '<div class="provider-status ' + cls + ' ' + providerCls + '" title="' + tooltip + '">'
            + '<div class="provider-content">' + nameHtml + countHtml + miniCalHtml + deviceHtml + '</div>'
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

// ── Poll a card until all active provider syncs complete ─────────────────────
// Polls the month API on an interval and re-renders the card each tick.
// Stops when every provider has finished (no queued/started status).
//
// minElapsed: keep polling for this long even if nothing appears active yet.
//   This covers the race between the HTTP response and the pull_month Celery
//   task actually running and writing statuses to the DB.  Without it, a
//   second month started while the worker is busy with the first would see an
//   empty status table, think it was done, and stop polling prematurely.
function pollCard(yearMonth, { interval = 2000, maxElapsed = 3600000, minElapsed = 30000 } = {}) {
    const start = Date.now();
    let sawActive = false; // have we ever seen a queued/started status for this month?

    async function attempt() {
        try {
            const res  = await fetch('/api/calendar/' + yearMonth);
            const data = await res.json();
            renderGrid(yearMonth, data);

            const statuses = data.pull_statuses || {};
            const anyActive = Object.values(statuses).some(
                s => s && (s.status === 'queued' || s.status === 'started')
            );

            if (anyActive) sawActive = true;

            const elapsed = Date.now() - start;

            // Keep polling while within the hard cap AND either:
            //  - a provider is still active, OR
            //  - we haven't seen any activity yet and are within the grace window
            const keepPolling = elapsed < maxElapsed &&
                (anyActive || (!sawActive && elapsed < minElapsed));

            if (keepPolling) setTimeout(attempt, interval);
        } catch (_) { /* ignore transient errors */ }
    }

    setTimeout(attempt, interval);
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
    const month = btn.dataset.month;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner spinner-sm"></span>';

    try {
        const res = await fetch('/api/sync/' + month, { method: 'POST' });
        if (!res.ok) {
            btn.disabled = false;
            btn.textContent = '⬇';
            return;
        }
    } catch (e) {
        btn.disabled = false;
        btn.textContent = '⬇';
        return;
    }

    btn.disabled = false;
    btn.textContent = '⬇';
    pollCard(month);
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

// ── On page load: fetch all initial cards in one request ─────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    const cards = Array.from(document.querySelectorAll('.month-card[id^="card-"]'));
    if (cards.length === 0) return;
    const months = cards.map(c => c.id.replace('card-', ''));
    // Cards are newest-first in the DOM, so last = oldest, first = newest
    const from = months[months.length - 1];
    const to   = months[0];
    try {
        const res  = await fetch('/api/calendar?from=' + from + '&to=' + to);
        const data = await res.json();
        months.forEach(ym => {
            renderGrid(ym, data[ym] || { error: 'No data' });
            const statuses = (data[ym] && data[ym].pull_statuses) || {};
            const anyActive = Object.values(statuses).some(
                s => s && (s.status === 'queued' || s.status === 'started')
            );
            if (anyActive) pollCard(ym, { minElapsed: 0 });
        });
    } catch (e) {
        months.forEach(ym => {
            const grid = document.getElementById('grid-' + ym);
            if (grid) grid.innerHTML = '<div class="card-loading" style="color:#dc3545">Load error</div>';
        });
    }
    setupInfiniteScroll();
});
// ── Append a month card to the main grid ─────────────────────────────────────
function appendMonthCard(ym, year, monthNum) {
    const monthName = new Date(year, monthNum - 1, 1).toLocaleString('default', { month: 'long' });
    const div = document.createElement('div');
    div.className = 'month-card';
    div.id = 'card-' + ym;
    div.innerHTML = `
        <div class="month-header" onclick="this.parentElement.classList.toggle('expanded')">
            <div class="month-status-ring pending" id="ring-${ym}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            </div>
            <div class="month-info">
                <div class="month-title">${monthName} ${year}</div>
                <div class="month-meta" id="total-${ym}"></div>
            </div>
            <div class="month-btn-group">
                <a class="sync-review-link month-action-btn" href="/month/${ym}" title="Sync Review" onclick="event.stopPropagation()">⇄</a>
                <button class="pull-btn month-action-btn" data-month="${ym}"
                        onclick="event.stopPropagation(); pullMonth(this)" title="Pull">⬇</button>
                <button class="reset-btn month-action-btn" data-month="${ym}"
                        onclick="event.stopPropagation(); resetMonth(this)" title="Reset month data">↺</button>
            </div>
            <svg class="expand-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
        </div>
        <div class="month-body">
            <div class="provider-grid" id="grid-${ym}">
                <div class="card-loading">Loading…</div>
            </div>
            <div class="pull-status" id="status-${ym}"></div>
        </div>`;
    const sentinel = document.getElementById('load-more-sentinel');
    const grid = document.getElementById('calendar-grid');
    if (sentinel) grid.insertBefore(div, sentinel);
    else grid.appendChild(div);
}

// ── Append a month entry to the timeline rail ─────────────────────────────────
function appendTimelineEntry(ym, year, monthNum) {
    const monthName = new Date(year, monthNum - 1, 1).toLocaleString('default', { month: 'long' });
    const list = document.querySelector('.timeline-list');
    if (!list) return;
    const sentinel = document.getElementById('tl-sentinel');

    // Add a year header when crossing a year boundary
    const yearDivs = list.querySelectorAll('.timeline-year');
    const lastYearEl = yearDivs[yearDivs.length - 1];
    const lastYear = lastYearEl ? parseInt(lastYearEl.textContent) : null;
    if (lastYear !== year) {
        const yearDiv = document.createElement('div');
        yearDiv.className = 'timeline-year';
        yearDiv.textContent = year;
        if (sentinel) list.insertBefore(yearDiv, sentinel);
        else list.appendChild(yearDiv);
    }

    const a = document.createElement('a');
    a.href = '#card-' + ym;
    a.className = 'timeline-month';
    a.innerHTML = `<div class="tl-dot pending"></div>${monthName}`;
    a.addEventListener('click', e => {
        e.preventDefault();
        const card = document.getElementById('card-' + ym);
        if (card) {
            card.classList.add('expanded');
            card.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
    if (sentinel) list.insertBefore(a, sentinel);
    else list.appendChild(a);
}

// ── Load 12 more months going back in time ────────────────────────────────────
async function loadMoreMonths() {
    if (!oldestLoaded || _loadingMore) return;
    // Stop once we've passed the oldest month that has any activity data.
    if (OLDEST_ACTIVITY_MONTH && oldestLoaded <= OLDEST_ACTIVITY_MONTH) return;
    _loadingMore = true;
    let [y, m] = oldestLoaded.split('-').map(Number);
    const newMonths = [];
    for (let i = 0; i < 12; i++) {
        m--;
        if (m === 0) { m = 12; y--; }
        const ym = `${String(y).padStart(4, '0')}-${String(m).padStart(2, '0')}`;
        appendMonthCard(ym, y, m);
        appendTimelineEntry(ym, y, m);
        newMonths.push(ym);
        oldestLoaded = ym;
    }
    const from = newMonths[newMonths.length - 1];
    const to   = newMonths[0];
    try {
        const res  = await fetch('/api/calendar?from=' + from + '&to=' + to);
        const data = await res.json();
        newMonths.forEach(ym => renderGrid(ym, data[ym] || { error: 'No data' }));
    } catch (e) {
        newMonths.forEach(ym => {
            const grid = document.getElementById('grid-' + ym);
            if (grid) grid.innerHTML = '<div class="card-loading" style="color:#dc3545">Load error</div>';
        });
    } finally {
        _loadingMore = false;
        requestAnimationFrame(_recheckSentinels);
    }
}

// ── Re-check whether sentinels are still visible after a load ────────────────
// IntersectionObserver only fires on state *changes*; if the sentinel is still
// visible after inserting 12 months, we need to trigger another load manually.
function _recheckSentinels() {
    if (OLDEST_ACTIVITY_MONTH && oldestLoaded <= OLDEST_ACTIVITY_MONTH) return;
    const syncContent = document.querySelector('.sync-content');
    const mainSentinel = document.getElementById('load-more-sentinel');
    if (syncContent && mainSentinel) {
        const sr = mainSentinel.getBoundingClientRect();
        const cr = syncContent.getBoundingClientRect();
        if (sr.top < cr.bottom && sr.bottom > cr.top) { loadMoreMonths(); return; }
    }
    const tlList = document.querySelector('.timeline-list');
    const tlSentinel = document.getElementById('tl-sentinel');
    if (tlList && tlSentinel) {
        const sr = tlSentinel.getBoundingClientRect();
        const lr = tlList.getBoundingClientRect();
        if (sr.top < lr.bottom && sr.bottom > lr.top) loadMoreMonths();
    }
}

// ── Wire up IntersectionObserver for infinite scroll ──────────────────────────
function setupInfiniteScroll() {
    const syncContent = document.querySelector('.sync-content');
    if (syncContent) {
        const obs = new IntersectionObserver(entries => {
            if (entries.some(e => e.isIntersecting)) loadMoreMonths();
        }, { root: syncContent, threshold: 0 });
        const sentinel = document.getElementById('load-more-sentinel');
        if (sentinel) obs.observe(sentinel);
    }

    const tlList = document.querySelector('.timeline-list');
    if (tlList) {
        const obs = new IntersectionObserver(entries => {
            if (entries.some(e => e.isIntersecting)) loadMoreMonths();
        }, { root: tlList, threshold: 0 });
        const sentinel = document.getElementById('tl-sentinel');
        if (sentinel) obs.observe(sentinel);
    }
}
