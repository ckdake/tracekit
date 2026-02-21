// Settings page logic.
// Expects `INITIAL_CONFIG` to be defined inline before this script loads.
/* global INITIAL_CONFIG */

// ── Status toast ─────────────────────────────────────────────────────────────
let toastTimer = null;
function showStatus(text, type = 'ok') {
    const msg = document.getElementById('status-msg');
    msg.textContent = text;
    msg.className = type;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { msg.textContent = ''; msg.className = ''; }, 3000);
}

const PROVIDER_META = {
    strava:      { label: 'Strava',       sync_equipment: true,  sync_name: true,  text_fields: [] },
    ridewithgps: { label: 'RideWithGPS',  sync_equipment: true,  sync_name: true,  text_fields: [] },
    garmin:      { label: 'Garmin',       sync_equipment: true,  sync_name: true,  text_fields: [] },
    spreadsheet: { label: 'Spreadsheet',  sync_equipment: true,  sync_name: true,  text_fields: [{ key: 'path', label: 'path' }] },
    file:        { label: 'File',         sync_equipment: true,  sync_name: true,  text_fields: [{ key: 'glob', label: 'glob' }] },
    stravajson:  { label: 'StravaJSON',   sync_equipment: false, sync_name: false, text_fields: [] },
};

// ── Drag-and-drop ─────────────────────────────────────────────────────────────
let dragSrc = null;

function addDragListeners(card) {
    card.addEventListener('dragstart', e => {
        dragSrc = card;
        e.dataTransfer.effectAllowed = 'move';
        setTimeout(() => card.classList.add('dragging'), 0);
    });
    card.addEventListener('dragend', () => {
        card.classList.remove('dragging');
        dragSrc = null;
    });
    card.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (dragSrc && dragSrc !== card) card.classList.add('drag-over');
    });
    card.addEventListener('dragleave', () => card.classList.remove('drag-over'));
    card.addEventListener('drop', e => {
        e.preventDefault();
        e.stopPropagation();
        card.classList.remove('drag-over');
        if (!dragSrc || dragSrc === card) return;
        const list = card.parentNode;
        const srcIdx = [...list.children].indexOf(dragSrc);
        const dstIdx = [...list.children].indexOf(card);
        if (srcIdx < dstIdx) list.insertBefore(dragSrc, card.nextSibling);
        else                 list.insertBefore(dragSrc, card);
        autoSave();
    });
}

// ── Build a provider card ─────────────────────────────────────────────────────
function makeToggle(id, checked, labelText) {
    const label = document.createElement('label');
    label.className = 'toggle';
    label.innerHTML = `
        <input type="checkbox" id="${id}" ${checked ? 'checked' : ''}>
        <span class="toggle-track"><span class="toggle-thumb"></span></span>
        <span class="toggle-label">${labelText}</span>`;
    return label;
}

function makeEditableField(fieldMeta, value) {
    const wrap = document.createElement('div');
    wrap.className = 'editable-field';
    wrap.innerHTML = `
        <span class="field-label">${fieldMeta.label}</span>
        <input type="text" class="field-${fieldMeta.key}" value="${escHtml(value)}" placeholder="(not set)">
        <span class="edit-hint">click to edit</span>`;

    const input = wrap.querySelector('input');
    input.addEventListener('focus', () => {
        wrap.querySelector('.edit-hint').style.display = 'none';
    });
    input.addEventListener('blur', () => {
        if (!input.value) wrap.querySelector('.edit-hint').style.display = '';
    });
    return wrap;
}

function escHtml(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}

function makeProviderCard(name, data) {
    const meta = PROVIDER_META[name] || { label: name, sync_equipment: false, sync_name: false, text_fields: [] };

    const card = document.createElement('div');
    card.className = 'provider-card' + (data.enabled ? '' : ' disabled-card');
    card.draggable = true;
    card.dataset.provider = name;

    const header = document.createElement('div');
    header.className = 'provider-header';
    header.innerHTML = `<span class="drag-handle">⠿</span><span class="provider-name">${escHtml(meta.label)}</span>`;

    const enabledToggle = makeToggle(`en-${name}`, data.enabled, 'Enabled');
    enabledToggle.querySelector('input').addEventListener('change', e => {
        card.classList.toggle('disabled-card', !e.target.checked);
        autoSave();
    });
    header.appendChild(enabledToggle);
    card.appendChild(header);

    const controls = document.createElement('div');
    controls.className = 'provider-controls';

    if (meta.sync_equipment) {
        const t = makeToggle(`se-${name}`, data.sync_equipment ?? false, 'Sync equipment');
        t.querySelector('input').addEventListener('change', autoSave);
        controls.appendChild(t);
    }
    if (meta.sync_name) {
        const t = makeToggle(`sn-${name}`, data.sync_name ?? false, 'Sync name');
        t.querySelector('input').addEventListener('change', autoSave);
        controls.appendChild(t);
    }

    if (controls.children.length > 0) card.appendChild(controls);

    for (const f of meta.text_fields) {
        const field = makeEditableField(f, data[f.key] ?? '');
        field.querySelector('input').addEventListener('change', autoSave);
        card.appendChild(field);
    }

    addDragListeners(card);
    return card;
}

// ── Render providers ──────────────────────────────────────────────────────────
function renderProviders(config) {
    const pconf = config.providers || {};
    const entries = Object.entries(pconf).sort((a, b) => {
        const pa = a[1].priority ?? 999;
        const pb = b[1].priority ?? 999;
        return pa !== pb ? pa - pb : a[0].localeCompare(b[0]);
    });

    const list = document.getElementById('provider-list');
    list.innerHTML = '';
    for (const [name, data] of entries) {
        list.appendChild(makeProviderCard(name, data));
    }
}

// ── Collect settings from DOM and save ───────────────────────────────────────
async function autoSave() {
    const tz    = document.getElementById('timezone').value;
    const debug = document.getElementById('debug-toggle').checked;

    const cards = document.querySelectorAll('.provider-card');
    const newProviders = {};
    let priority = 1;

    cards.forEach(card => {
        const name    = card.dataset.provider;
        const oldData = (INITIAL_CONFIG.providers || {})[name] || {};
        const meta    = PROVIDER_META[name] || {};

        const enabled   = card.querySelector(`#en-${name}`)?.checked ?? oldData.enabled ?? false;
        const syncEquip = meta.sync_equipment ? (card.querySelector(`#se-${name}`)?.checked ?? false) : undefined;
        const syncName  = meta.sync_name      ? (card.querySelector(`#sn-${name}`)?.checked ?? false) : undefined;

        const newData = { ...oldData, enabled, priority };
        if (syncEquip !== undefined) newData.sync_equipment = syncEquip;
        if (syncName  !== undefined) newData.sync_name = syncName;

        for (const f of (meta.text_fields || [])) {
            const input = card.querySelector(`.field-${f.key}`);
            if (input) newData[f.key] = input.value;
        }

        newProviders[name] = newData;
        priority++;
    });

    const newConfig = { ...INITIAL_CONFIG, home_timezone: tz, debug, providers: newProviders };

    try {
        const resp = await fetch('/api/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newConfig),
        });

        if (resp.ok) {
            Object.assign(INITIAL_CONFIG, newConfig);
            showStatus('Saved.');
        } else {
            const err = await resp.json().catch(() => ({}));
            showStatus('Error: ' + (err.error || resp.statusText), 'err');
        }
    } catch (e) {
        showStatus('Network error: ' + e.message, 'err');
    }
}

// ── Init ──────────────────────────────────────────────────────────────────────
renderProviders(INITIAL_CONFIG);
document.getElementById('timezone').addEventListener('change', autoSave);
document.getElementById('debug-toggle').addEventListener('change', autoSave);
