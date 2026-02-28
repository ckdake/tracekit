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
    strava: {
        label: 'Strava', sync_equipment: true, sync_name: true,
        // No text_fields by default — client_id/secret come from system credentials.
        // They are revealed in personal_credential_fields when the toggle is on.
        text_fields: [],
        personal_credential_fields: [
            { key: 'client_id',     label: 'client id' },
            { key: 'client_secret', label: 'client secret', field_type: 'password' },
        ],
    },
    ridewithgps: {
        label: 'RideWithGPS', sync_equipment: true, sync_name: true,
        text_fields: [],
        personal_credential_fields: [
            { key: 'client_id',     label: 'client id' },
            { key: 'client_secret', label: 'client secret', field_type: 'password' },
        ],
    },
    garmin:      { label: 'Garmin',       sync_equipment: true,  sync_name: true,
        instructions: 'Garmin authentication tokens are valid for approximately one year. Re-authenticate before they expire to avoid interruption.',
        text_fields: [] },
    spreadsheet: {
        label: 'Spreadsheet', sync_equipment: true, sync_name: true,
        instructions: `Point <strong>path</strong> at an <code>.xlsx</code> file. Row 1 is a header row (skipped). Each subsequent row is one activity.<br>
Columns (A–U):
<code>A</code> date/datetime <em>(required)</em> &nbsp;
<code>B</code> activity type &nbsp;
<code>C</code> location name &nbsp;
<code>D</code> city &nbsp;
<code>E</code> state &nbsp;
<code>F</code> temperature &nbsp;
<code>G</code> equipment &nbsp;
<code>H</code> duration (HH:MM:SS) &nbsp;
<code>I</code> distance &nbsp;
<code>J</code> max speed &nbsp;
<code>K</code> avg heart rate &nbsp;
<code>L</code> max heart rate &nbsp;
<code>M</code> calories &nbsp;
<code>N</code> max elevation &nbsp;
<code>O</code> total elevation gain &nbsp;
<code>P</code> with (names) &nbsp;
<code>Q</code> avg cadence &nbsp;
<code>R</code> strava id &nbsp;
<code>S</code> garmin id &nbsp;
<code>T</code> ridewithgps id &nbsp;
<code>U</code> notes / name`,
        text_fields: [{ key: 'path', label: 'path' }],
    },
    file: {
        label: 'File',
        sync_equipment: false,
        sync_name: false,
        instructions: 'Drop any supported activity file (<code>.gpx</code>, <code>.fit</code>, <code>.tcx</code>, or their <code>.gz</code> variants) ' +
            'into <code>~/data/activities</code> and it will be picked up on the next sync. ' +
            'Intended for importing files directly or hydrating activities with their original source data. ' +
            '<strong>Equipment and name are not synced from files</strong> — use Strava, Garmin, RideWithGPS, or the Spreadsheet provider for those.',
        text_fields: [],
    },
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
    const inputType = fieldMeta.field_type || 'text';
    const wrap = document.createElement('div');
    wrap.className = 'editable-field';
    wrap.innerHTML = `
        <span class="field-label">${fieldMeta.label}</span>
        <input type="${inputType}" class="field-${fieldMeta.key}" value="${escHtml(value)}" placeholder="(not set)">
        <span class="edit-hint">click to edit</span>
        <span class="save-check" aria-hidden="true">✓</span>`;

    const input = wrap.querySelector('input');
    input.addEventListener('focus', () => {
        wrap.querySelector('.edit-hint').style.display = 'none';
        wrap.querySelector('.save-check').classList.remove('visible');
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
    header.innerHTML = `<span class="drag-handle">⠿</span><span class="provider-name">${escHtml(meta.label)}</span><span class="provider-activity-count"></span><span class="provider-inline-status"></span>`;

    const enabledToggle = makeToggle(`en-${name}`, data.enabled, 'Enabled');
    enabledToggle.querySelector('input').addEventListener('change', e => {
        const enabled = e.target.checked;
        card.classList.toggle('disabled-card', !enabled);
        card.querySelectorAll('.provider-controls input[type="checkbox"]').forEach(cb => {
            cb.disabled = !enabled;
        });
        autoSave();
    });
    header.appendChild(enabledToggle);
    card.appendChild(header);

    const controls = document.createElement('div');
    controls.className = 'provider-controls';

    if (meta.sync_equipment) {
        const t = makeToggle(`se-${name}`, data.sync_equipment ?? false, 'Sync equipment');
        t.querySelector('input').disabled = !data.enabled;
        t.querySelector('input').addEventListener('change', autoSave);
        controls.appendChild(t);
    }
    if (meta.sync_name) {
        const t = makeToggle(`sn-${name}`, data.sync_name ?? false, 'Sync name');
        t.querySelector('input').disabled = !data.enabled;
        t.querySelector('input').addEventListener('change', autoSave);
        controls.appendChild(t);
    }

    if (controls.children.length > 0) card.appendChild(controls);

    if (meta.instructions) {
        const note = document.createElement('p');
        note.className = 'provider-note';
        note.innerHTML = meta.instructions;
        card.appendChild(note);
    }

    // Strava: auth button appears before the personal-credentials section so the
    // card looks like Garmin's by default (just a connect button + a toggle below).
    if (name === 'strava') {
        const authBtn = document.createElement('button');
        authBtn.type = 'button';
        authBtn.className = 'strava-auth-btn';
        authBtn.textContent = data.access_token ? 'Re-authenticate with Strava' : 'Connect with Strava';
        authBtn.addEventListener('click', () => { window.location.href = '/api/auth/strava/authorize'; });
        card.appendChild(authBtn);
    }

    // RideWithGPS: OAuth button, same pattern as Strava.
    if (name === 'ridewithgps') {
        const authBtn = document.createElement('button');
        authBtn.type = 'button';
        authBtn.className = 'ridewithgps-auth-btn';
        authBtn.textContent = data.access_token ? 'Re-authenticate with RideWithGPS' : 'Connect with RideWithGPS';
        authBtn.addEventListener('click', () => { window.location.href = '/api/auth/ridewithgps/authorize'; });
        card.appendChild(authBtn);
    }

    // Always-visible text fields (e.g. email/password for RideWithGPS).
    for (const f of meta.text_fields) {
        const field = makeEditableField(f, data[f.key] ?? '');
        const inp = field.querySelector('input');
        inp.addEventListener('change', () => autoSave(inp));
        card.appendChild(field);
    }

    // ── Personal-credentials toggle (Strava, RideWithGPS) ─────────────────────
    if (meta.personal_credential_fields && meta.personal_credential_fields.length > 0) {
        // Smart default: if use_personal_credentials not yet set but the user
        // already has personal creds stored, initialize the toggle to ON so
        // existing setups aren't silently broken.
        let usePersonal = data.use_personal_credentials;
        if (usePersonal === undefined || usePersonal === null) {
            if (name === 'strava' || name === 'ridewithgps') {
                usePersonal = Boolean(data.client_id && data.client_secret);
            } else {
                usePersonal = false;
            }
        }

        const pcToggle = makeToggle(`pc-${name}`, usePersonal, 'Use personal API credentials');
        pcToggle.classList.add('personal-creds-toggle-row');
        const pcSection = document.createElement('div');
        pcSection.className = 'personal-cred-section';
        pcSection.style.display = usePersonal ? '' : 'none';

        // Build personal-cred fields inside the section
        for (const f of meta.personal_credential_fields) {
            const field = makeEditableField(f, data[f.key] ?? '');
            const inp = field.querySelector('input');
            inp.addEventListener('change', () => autoSave(inp));
            pcSection.appendChild(field);
        }

        // For Strava: the "Before authenticating" note lives inside the section
        if (name === 'strava') {
            const callbackUrl = `${window.location.origin}/api/auth/strava/callback`;
            const redirectNote = document.createElement('p');
            redirectNote.className = 'strava-redirect-note';
            redirectNote.innerHTML =
                `<strong>Before authenticating:</strong> in your <a href="https://www.strava.com/settings/api" target="_blank" rel="noopener">Strava API app settings</a>, ` +
                `set the <strong>Authorization Callback Domain</strong> to <code>${window.location.hostname}</code>. ` +
                `The full callback URL tracekit uses is <code>${callbackUrl}</code>.`;
            pcSection.appendChild(redirectNote);
        }

        // System-credentials status note (shown when toggle is OFF)
        const sysCreds = (typeof SYSTEM_CREDENTIALS !== 'undefined') ? SYSTEM_CREDENTIALS : {};
        const sysNote = document.createElement('p');
        sysNote.className = 'provider-note provider-sys-creds-note';
        sysNote.style.display = usePersonal ? 'none' : '';
        if (sysCreds[name]) {
            sysNote.textContent = 'Using system API credentials.';
        } else {
            sysNote.innerHTML = '<strong>Warning:</strong> No system API credentials configured. Turn on personal credentials or ask the operator to add them.';
        }

        pcToggle.querySelector('input').addEventListener('change', e => {
            const isPersonal = e.target.checked;
            pcSection.style.display = isPersonal ? '' : 'none';
            sysNote.style.display = isPersonal ? 'none' : '';

            // Strava/RideWithGPS: clear stored OAuth tokens — they were issued for the
            // previous client_id, so they are invalid after switching credential source.
            if (name === 'strava') {
                if (INITIAL_CONFIG.providers && INITIAL_CONFIG.providers.strava) {
                    INITIAL_CONFIG.providers.strava.access_token = '';
                    INITIAL_CONFIG.providers.strava.refresh_token = '';
                    INITIAL_CONFIG.providers.strava.token_expires = '0';
                }
                const authBtn = card.querySelector('.strava-auth-btn');
                if (authBtn) authBtn.textContent = 'Connect with Strava';
            }
            if (name === 'ridewithgps') {
                if (INITIAL_CONFIG.providers && INITIAL_CONFIG.providers.ridewithgps) {
                    INITIAL_CONFIG.providers.ridewithgps.access_token = '';
                }
                const authBtn = card.querySelector('.ridewithgps-auth-btn');
                if (authBtn) authBtn.textContent = 'Connect with RideWithGPS';
            }

            autoSave();
        });

        card.appendChild(pcToggle);
        card.appendChild(sysNote);
        card.appendChild(pcSection);
    }

    if (name === 'garmin') {
        const authBtn = document.createElement('button');
        authBtn.type = 'button';
        authBtn.className = 'garmin-auth-btn';
        authBtn.textContent = data.garth_tokens ? 'Re-authenticate with Garmin' : 'Authenticate with Garmin';
        authBtn.addEventListener('click', () => openGarminModal(card, data, name));
        card.appendChild(authBtn);
    }

    if (name === 'file') {
        const pullBtn = document.createElement('button');
        pullBtn.type = 'button';
        pullBtn.className = 'provider-auth-btn';
        pullBtn.textContent = 'Pull Files';
        pullBtn.addEventListener('click', () => pullFileActivities(pullBtn));
        card.appendChild(pullBtn);

        const statusEl = document.createElement('div');
        statusEl.className = 'file-pull-status';
        card.appendChild(statusEl);
    }

    addDragListeners(card);
    return card;
}

// ── Render providers ──────────────────────────────────────────────────────────
function renderProviders(config) {
    const pconf = config.providers || {};
    const enabledSet = typeof ENABLED_PROVIDERS !== 'undefined' ? new Set(ENABLED_PROVIDERS) : null;
    const entries = Object.entries(pconf)
        .filter(([name]) => !enabledSet || enabledSet.has(name))
        .sort((a, b) => {
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
const fieldCheckTimers = new WeakMap();
function showFieldCheck(inputEl) {
    if (!inputEl) return;
    const check = inputEl.closest('.editable-field')?.querySelector('.save-check');
    if (!check) return;
    check.classList.add('visible');
    clearTimeout(fieldCheckTimers.get(check));
    fieldCheckTimers.set(check, setTimeout(() => check.classList.remove('visible'), 3000));
}

async function autoSave(triggerEl) {
    const tz    = document.getElementById('timezone').value;
    const debug = document.getElementById('debug-toggle')?.checked ?? INITIAL_CONFIG.debug ?? false;

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

        // Capture personal-credentials toggle
        const pcToggle = card.querySelector(`#pc-${name}`);
        if (pcToggle) newData.use_personal_credentials = pcToggle.checked;

        for (const f of (meta.text_fields || [])) {
            const input = card.querySelector(`.field-${f.key}`);
            if (input) newData[f.key] = input.value;
        }

        // Personal-credential fields are always persisted (even when toggle is OFF)
        // so the values aren't lost if the user flips back.
        // Exception: Strava tokens are zeroed when use_personal_credentials changes
        // (handled in the toggle change listener above via INITIAL_CONFIG mutation).
        for (const f of (meta.personal_credential_fields || [])) {
            const input = card.querySelector(`.field-${f.key}`);
            if (input) newData[f.key] = input.value;
        }

        // Pick up any token fields that were zeroed via INITIAL_CONFIG mutation
        if (name === 'strava' && INITIAL_CONFIG.providers?.strava) {
            const src = INITIAL_CONFIG.providers.strava;
            newData.access_token   = src.access_token   ?? newData.access_token;
            newData.refresh_token  = src.refresh_token  ?? newData.refresh_token;
            newData.token_expires  = src.token_expires  ?? newData.token_expires;
        }
        if (name === 'ridewithgps' && INITIAL_CONFIG.providers?.ridewithgps) {
            const src = INITIAL_CONFIG.providers.ridewithgps;
            newData.access_token = src.access_token ?? newData.access_token;
        }

        newProviders[name] = newData;
        priority++;
    });

    // Re-attach hidden (system-disabled) provider configs so their credentials
    // are preserved on the server even while those providers aren't rendered.
    const hiddenConfigs = typeof HIDDEN_PROVIDER_CONFIGS !== 'undefined' ? HIDDEN_PROVIDER_CONFIGS : {};
    const newConfig = { ...INITIAL_CONFIG, home_timezone: tz, debug, providers: { ...hiddenConfigs, ...newProviders } };

    try {
        const resp = await fetch('/api/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newConfig),
        });

        if (resp.ok) {
            Object.assign(INITIAL_CONFIG, newConfig);
            showStatus('Saved.');
            showFieldCheck(triggerEl);
        } else {
            const err = await resp.json().catch(() => ({}));
            showStatus('Error: ' + (err.error || resp.statusText), 'err');
        }
    } catch (e) {
        showStatus('Network error: ' + e.message, 'err');
    }
}

// ── Garmin auth modal ────────────────────────────────────────────────────────

function buildModal() {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay hidden';
    overlay.id = 'garmin-auth-modal';
    overlay.innerHTML = `
        <div class="modal-box" role="dialog" aria-modal="true" aria-labelledby="garmin-modal-title">
            <h3 id="garmin-modal-title">Garmin Connect</h3>
            <p class="modal-subtitle" id="garmin-modal-subtitle">Sign in to save tokens.</p>
            <div id="garmin-modal-body"></div>
            <div class="modal-error" id="garmin-modal-error"></div>
            <div class="modal-actions" id="garmin-modal-actions"></div>
        </div>`;
    overlay.addEventListener('click', e => { if (e.target === overlay) closeGarminModal(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeGarminModal(); });
    document.body.appendChild(overlay);
    return overlay;
}

const _modal = buildModal();
let _modalCard = null;
let _modalProviderName = null;
let _mfaSessionId = null;
let _modalBusy = false;
let _modalEmail = '';

function closeGarminModal() {
    if (_modalBusy) return;
    _modal.classList.add('hidden');
    _mfaSessionId = null;
    _modalEmail = '';
}

function setModalError(msg) {
    document.getElementById('garmin-modal-error').textContent = msg || '';
}

function setModalBusy(busy) {
    _modalBusy = busy;
    _modal.querySelectorAll('button').forEach(b => {
        b.disabled = busy;
        if (b.classList.contains('btn-primary')) {
            b.textContent = busy ? 'Please wait…' : b.dataset.label;
        }
    });
}

function showCredentialsStep(prefillEmail) {
    document.getElementById('garmin-modal-subtitle').textContent = 'Enter your Garmin Connect credentials.';
    const body = document.getElementById('garmin-modal-body');
    body.innerHTML = `
        <div class="modal-field">
            <label for="gm-email">Email</label>
            <input type="email" id="gm-email" value="${escHtml(prefillEmail)}" autocomplete="username" placeholder="you@example.com">
        </div>
        <div class="modal-field">
            <label for="gm-password">Password</label>
            <input type="password" id="gm-password" autocomplete="current-password" placeholder="••••••••">
        </div>`;

    const actions = document.getElementById('garmin-modal-actions');
    actions.innerHTML = '';

    const cancel = document.createElement('button');
    cancel.type = 'button'; cancel.className = 'btn btn-secondary';
    cancel.textContent = 'Cancel';
    cancel.addEventListener('click', closeGarminModal);

    const submit = document.createElement('button');
    submit.type = 'button'; submit.className = 'btn btn-primary';
    submit.textContent = 'Sign in'; submit.dataset.label = 'Sign in';
    submit.addEventListener('click', submitCredentials);
    actions.appendChild(cancel);
    actions.appendChild(submit);

    // Allow Enter to submit
    body.querySelectorAll('input').forEach(inp =>
        inp.addEventListener('keydown', e => { if (e.key === 'Enter') submitCredentials(); }));

    const emailInput = body.querySelector('#gm-email');
    setTimeout(() => (prefillEmail ? body.querySelector('#gm-password') : emailInput).focus(), 50);
}

function showMfaStep() {
    document.getElementById('garmin-modal-subtitle').textContent = 'Check your email for a one-time code from Garmin.';
    const body = document.getElementById('garmin-modal-body');
    body.innerHTML = `
        <div class="modal-field">
            <label for="gm-mfa">One-time code</label>
            <input type="text" id="gm-mfa" inputmode="numeric" autocomplete="one-time-code" placeholder="123456" style="letter-spacing:.15em;">
        </div>`;

    const actions = document.getElementById('garmin-modal-actions');
    actions.innerHTML = '';

    const back = document.createElement('button');
    back.type = 'button'; back.className = 'btn btn-secondary';
    back.textContent = 'Back';
    back.addEventListener('click', () => { _mfaSessionId = null; showCredentialsStep(_modalEmail); setModalError(''); });

    const submit = document.createElement('button');
    submit.type = 'button'; submit.className = 'btn btn-primary';
    submit.textContent = 'Verify'; submit.dataset.label = 'Verify';
    submit.addEventListener('click', submitMfa);
    actions.appendChild(back);
    actions.appendChild(submit);

    body.querySelector('#gm-mfa').addEventListener('keydown', e => { if (e.key === 'Enter') submitMfa(); });
    setTimeout(() => body.querySelector('#gm-mfa').focus(), 50);
}

async function submitCredentials() {
    const email = document.getElementById('gm-email')?.value.trim();
    const password = document.getElementById('gm-password')?.value;
    if (!email || !password) { setModalError('Please enter both email and password.'); return; }
    _modalEmail = email;
    setModalError('');
    setModalBusy(true);

    try {
        const resp = await fetch('/api/auth/garmin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const json = await resp.json().catch(() => ({}));
        setModalBusy(false);

        if (!resp.ok) { setModalError(json.error || 'Authentication failed.'); return; }

        if (json.status === 'needs_mfa') {
            _mfaSessionId = json.session_id;
            showMfaStep();
        } else if (json.status === 'ok') {
            onAuthSuccess(email, json.full_name);
        }
    } catch (e) {
        setModalBusy(false);
        setModalError('Network error: ' + e.message);
    }
}

async function submitMfa() {
    const mfa_code = document.getElementById('gm-mfa')?.value.trim();
    if (!mfa_code) { setModalError('Please enter the one-time code.'); return; }
    setModalError('');
    setModalBusy(true);

    try {
        const resp = await fetch('/api/auth/garmin/mfa', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: _mfaSessionId, mfa_code }),
        });
        const json = await resp.json().catch(() => ({}));
        setModalBusy(false);

        if (!resp.ok) { setModalError(json.error || 'Verification failed.'); return; }
        onAuthSuccess('', json.full_name);
    } catch (e) {
        setModalBusy(false);
        setModalError('Network error: ' + e.message);
    }
}

// ── Strava auth popup ──────────────────────────────────────────────────────────

function openStravaPopup(card) {
    const popup = window.open(
        '/api/auth/strava/authorize',
        'stravaAuth',
        'width=600,height=700,left=200,top=100'
    );
    if (!popup) {
        showStatus('Popup blocked \u2014 please allow popups for this site.', 'err');
        return;
    }

    const btn = card.querySelector('.provider-auth-btn');

    function onMessage(e) {
        if (!e.data?.stravaAuth) return;
        window.removeEventListener('message', onMessage);
        clearInterval(closedCheck);
        if (e.data.status === 'ok') {
            showStatus('Strava authenticated successfully!', 'ok');
            if (btn) btn.textContent = 'Re-authenticate with Strava';
            fetch('/api/config').then(r => r.json()).then(cfg => Object.assign(INITIAL_CONFIG, cfg)).catch(() => {});
        } else {
            showStatus('Strava auth failed: ' + (e.data.message || 'unknown error'), 'err');
        }
    }
    window.addEventListener('message', onMessage);

    const closedCheck = setInterval(() => {
        if (popup.closed) {
            clearInterval(closedCheck);
            window.removeEventListener('message', onMessage);
        }
    }, 1000);
}

function onAuthSuccess(email, fullName) {
    closeGarminModal();
    showStatus(`Garmin authenticated${fullName ? ` as ${fullName}` : ''}.`, 'ok');
    // Update the button label on the card
    if (_modalCard) {
        const btn = _modalCard.querySelector('.garmin-auth-btn');
        if (btn) btn.textContent = 'Re-authenticate with Garmin';
        // Reload config silently to pick up new tokens
        fetch('/api/config').then(r => r.json()).then(cfg => {
            Object.assign(INITIAL_CONFIG, cfg);
            // Update the displayed email field if present
            const emailInput = _modalCard.querySelector('.field-email');
            if (emailInput && email) emailInput.value = email;
        }).catch(() => {});
    }
}

function openGarminModal(card, data, providerName) {
    _modalCard = card;
    _modalProviderName = providerName;
    _mfaSessionId = null;
    _modalBusy = false;
    _modalEmail = data.email || '';
    setModalError('');
    showCredentialsStep(_modalEmail);
    _modal.classList.remove('hidden');
}

// ── File provider pull ────────────────────────────────────────────────────────
async function pullFileActivities(btn) {
    const card     = btn.closest('.provider-card');
    const statusEl = card ? card.querySelector('.file-pull-status') : null;

    btn.disabled = true;
    btn.textContent = 'Pulling…';
    if (statusEl) { statusEl.textContent = ''; statusEl.className = 'file-pull-status'; }

    let taskId;
    try {
        const res  = await fetch('/api/sync/file', { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
            if (statusEl) { statusEl.textContent = data.error || 'Error'; statusEl.className = 'file-pull-status err'; }
            btn.disabled = false;
            btn.textContent = 'Pull Files';
            return;
        }
        taskId = data.task_id;
    } catch (e) {
        if (statusEl) { statusEl.textContent = 'Network error'; statusEl.className = 'file-pull-status err'; }
        btn.disabled = false;
        btn.textContent = 'Pull Files';
        return;
    }

    if (statusEl) { statusEl.textContent = 'In progress…'; statusEl.className = 'file-pull-status running'; }

    const poll = setInterval(async () => {
        try {
            const sr = await fetch('/api/sync/status/' + taskId);
            const sd = await sr.json();
            if (sd.state === 'SUCCESS') {
                clearInterval(poll);
                btn.disabled = false;
                btn.textContent = 'Pull Files';
                if (statusEl) { statusEl.textContent = 'Done ✓'; statusEl.className = 'file-pull-status ok'; }
                setTimeout(() => {
                    if (statusEl) { statusEl.textContent = ''; statusEl.className = 'file-pull-status'; }
                }, 30000);
            } else if (sd.state === 'FAILURE') {
                clearInterval(poll);
                btn.disabled = false;
                btn.textContent = 'Pull Files';
                if (statusEl) { statusEl.textContent = sd.info || 'Failed'; statusEl.className = 'file-pull-status err'; }
            }
        } catch (_) { /* transient */ }
    }, 2000);
}

// ── Provider status ───────────────────────────────────────────────────────────
function formatRelativeTime(ts) {
    if (!ts) return null;
    const diff = Math.floor(Date.now() / 1000) - ts;
    if (diff < 60)  return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

function formatAbsTime(ts) {
    if (!ts) return null;
    return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatCountdown(ts) {
    const secs = ts - Math.floor(Date.now() / 1000);
    if (secs <= 0) return 'soon';
    if (secs < 3600) return `${Math.floor(secs / 60)}m ${secs % 60}s`;
    return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
}

function renderProviderStatuses(statuses) {
    document.querySelectorAll('.provider-card').forEach(card => {
        const name = card.dataset.provider;
        const status = statuses[name];

        // Remove old rate-limit banners if re-rendering
        card.querySelectorAll('.provider-rate-limit').forEach(el => el.remove());

        // Update activity count in the header
        const countEl = card.querySelector('.provider-activity-count');
        if (countEl) {
            const count = status?.activity_count;
            if (typeof count === 'number' && count > 0) {
                countEl.textContent = count.toLocaleString();
                countEl.title = `${count.toLocaleString()} activities`;
            } else {
                countEl.textContent = '';
            }
        }

        // Update inline status in the header
        const inlineStatus = card.querySelector('.provider-inline-status');
        if (inlineStatus) {
            inlineStatus.innerHTML = '';
            const hasStatus = status?.last_operation !== null && status?.last_operation !== undefined;
            const dotClass  = !status || !hasStatus ? 'unknown' : status.last_success ? 'ok' : 'error';

            const dot = document.createElement('span');
            dot.className = `status-dot ${dotClass}-dot`;
            inlineStatus.appendChild(dot);

            if (status && hasStatus) {
                const t = formatRelativeTime(status.last_operation_at);
                const text = document.createElement('span');
                text.className = 'status-inline-text';
                text.textContent = t ? `${status.last_operation} · ${t}` : status.last_operation;
                inlineStatus.appendChild(text);

                if (status.last_message) {
                    const info = document.createElement('span');
                    info.className = 'status-info-icon';
                    info.textContent = 'ⓘ';
                    info.setAttribute('data-tooltip', status.last_message);
                    inlineStatus.appendChild(info);
                }
            }
        }

        // Rate-limit banner (shown at bottom of card if present)
        if (status?.rate_limit_type) {
            const isLong = status.rate_limit_type === 'long_term';
            const banner = document.createElement('div');
            banner.className = `provider-rate-limit ${isLong ? 'long-term' : 'short-term'}`;
            const resetIn  = formatCountdown(status.rate_limit_reset_at);
            const resetAt  = formatAbsTime(status.rate_limit_reset_at);
            if (isLong) {
                banner.innerHTML =
                    `<span class="rl-icon">⚠</span>` +
                    `<span>Daily rate limit exceeded — resets at midnight UTC` +
                    (resetAt ? ` (~${resetIn}, at ${resetAt})` : '') +
                    `. <a href="https://developers.strava.com/docs/rate-limits/" target="_blank" rel="noopener">Strava rate limit docs</a></span>`;
            } else {
                banner.innerHTML =
                    `<span class="rl-icon">⏱</span>` +
                    `<span>Short-term rate limit — retrying in ~${resetIn}.</span>`;
            }
            card.appendChild(banner);
        }
    });
}

// ── Init ──────────────────────────────────────────────────────────────────────
renderProviders(INITIAL_CONFIG);renderProviderResetButtons(INITIAL_CONFIG);document.getElementById('timezone').addEventListener('change', autoSave);

// Fetch and render provider status after initial render
fetch('/api/provider-status')
    .then(r => r.json())
    .then(statuses => renderProviderStatuses(statuses))
    .catch(() => {}); // non-fatal
document.getElementById('debug-toggle').addEventListener('change', autoSave);

// ── Per-provider reset (Danger Zone) ─────────────────────────────────────────
let _resetProviderName = null;

function renderProviderResetButtons(config) {
    const list = document.getElementById('provider-reset-list');
    if (!list) return;
    list.innerHTML = '';
    const pconf = config.providers || {};
    const enabledSet = typeof ENABLED_PROVIDERS !== 'undefined' ? new Set(ENABLED_PROVIDERS) : null;
    let shown = 0;
    for (const [name, data] of Object.entries(pconf)) {
        if (!data.enabled) continue;
        if (enabledSet && !enabledSet.has(name)) continue;
        const meta = PROVIDER_META[name] || {};
        const label = meta.label || (name.charAt(0).toUpperCase() + name.slice(1));
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-danger btn-sm';
        btn.textContent = label;
        btn.addEventListener('click', () => openResetProviderModal(name, label));
        list.appendChild(btn);
        shown++;
    }
    if (!shown) {
        list.innerHTML = '<span class="field-help" style="margin:0;color:#999">No providers enabled.</span>';
    }
}

function openResetProviderModal(name, label) {
    _resetProviderName = name;
    document.getElementById('reset-provider-title').textContent = `Reset ${label}`;
    document.getElementById('reset-provider-subtitle').innerHTML =
        `This will permanently delete all <strong>${escHtml(label)}</strong> activities and sync records ` +
        `from the database. Files on disk are never touched.`;
    document.getElementById('reset-provider-error').textContent = '';
    const btn = document.getElementById('reset-provider-confirm-btn');
    btn.disabled = false;
    btn.textContent = 'Reset';
    document.getElementById('reset-provider-modal').classList.remove('hidden');
}

function closeResetProviderModal() {
    document.getElementById('reset-provider-modal').classList.add('hidden');
    _resetProviderName = null;
}

async function submitResetProvider() {
    const name = _resetProviderName;
    if (!name) return;
    const errorEl = document.getElementById('reset-provider-error');
    const btn     = document.getElementById('reset-provider-confirm-btn');

    btn.disabled = true;
    btn.textContent = 'Resetting…';
    errorEl.textContent = '';

    try {
        const res  = await fetch('/api/reset/provider/' + name, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
            errorEl.textContent = data.error || 'Error starting reset.';
            btn.disabled = false;
            btn.textContent = 'Reset';
            return;
        }
        const taskId = data.task_id;
        const poll = setInterval(async () => {
            try {
                const sr = await fetch('/api/sync/status/' + taskId);
                const sd = await sr.json();
                if (sd.state === 'SUCCESS') {
                    clearInterval(poll);
                    closeResetProviderModal();
                    showStatus(`${name} data reset successfully.`, 'ok');
                } else if (sd.state === 'FAILURE') {
                    clearInterval(poll);
                    errorEl.textContent = sd.info || 'Reset failed.';
                    btn.disabled = false;
                    btn.textContent = 'Reset';
                }
            } catch (_) { /* transient */ }
        }, 2000);
    } catch (e) {
        errorEl.textContent = 'Network error.';
        btn.disabled = false;
        btn.textContent = 'Reset';
    }
}

// ── Reset All Data ─────────────────────────────────────────────────────────────
function openResetAllModal() {
    document.getElementById('reset-confirm-input').value = '';
    document.getElementById('reset-modal-error').textContent = '';
    document.getElementById('reset-confirm-btn').disabled = false;
    document.getElementById('reset-all-modal').classList.remove('hidden');
    setTimeout(() => document.getElementById('reset-confirm-input').focus(), 50);
}

function closeResetAllModal() {
    document.getElementById('reset-all-modal').classList.add('hidden');
}

async function submitResetAll() {
    const input = document.getElementById('reset-confirm-input').value.trim().toLowerCase();
    const errorEl = document.getElementById('reset-modal-error');
    const btn = document.getElementById('reset-confirm-btn');

    if (input !== 'reset') {
        errorEl.textContent = 'Type "reset" to confirm.';
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Resetting…';
    errorEl.textContent = '';

    try {
        const res  = await fetch('/api/reset', { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
            errorEl.textContent = data.error || 'Error starting reset.';
            btn.disabled = false;
            btn.textContent = 'Reset All Data';
            return;
        }
        // Poll for completion
        const taskId = data.task_id;
        const poll = setInterval(async () => {
            try {
                const sr   = await fetch('/api/sync/status/' + taskId);
                const sd   = await sr.json();
                if (sd.state === 'SUCCESS') {
                    clearInterval(poll);
                    closeResetAllModal();
                    showStatus('All data reset successfully.', 'ok');
                } else if (sd.state === 'FAILURE') {
                    clearInterval(poll);
                    errorEl.textContent = sd.info || 'Reset failed.';
                    btn.disabled = false;
                    btn.textContent = 'Reset All Data';
                }
            } catch (_) { /* ignore transient errors */ }
        }, 2000);
    } catch (e) {
        errorEl.textContent = 'Network error.';
        btn.disabled = false;
        btn.textContent = 'Reset All Data';
    }
}

// Close modal on backdrop click
document.getElementById('reset-all-modal').addEventListener('click', e => {
    if (e.target === document.getElementById('reset-all-modal')) closeResetAllModal();
});
document.getElementById('reset-provider-modal').addEventListener('click', e => {
    if (e.target === document.getElementById('reset-provider-modal')) closeResetProviderModal();
});

// Close modal on Escape
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        if (!document.getElementById('reset-all-modal').classList.contains('hidden')) closeResetAllModal();
        if (!document.getElementById('reset-provider-modal').classList.contains('hidden')) closeResetProviderModal();
    }
});
