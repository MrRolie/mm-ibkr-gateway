/**
 * IBKR Gateway Operator Dashboard
 * Client-side JavaScript for trading control UI
 */

// Configuration
const CONFIG = {
    pollInterval: 5000,  // Status poll interval in ms
    apiBaseUrl: '',      // Empty for same-origin
};

// State
let adminToken = localStorage.getItem('adminToken') || '';
let pollTimer = null;
let pendingAction = null;
let runWindowTimer = null;
let controlStateSnapshot = null;

// DOM Elements
const elements = {
    // Auth
    adminTokenInput: document.getElementById('admin-token'),
    saveTokenBtn: document.getElementById('save-token-btn'),
    authStatus: document.getElementById('auth-status'),
    connectionStatus: document.getElementById('connection-status'),
    runWindowBanner: document.getElementById('run-window-banner'),
    runWindowMessage: document.getElementById('run-window-message'),
    runWindowNext: document.getElementById('run-window-next'),

    // Status
    statusValue: document.getElementById('status-value'),
    tradingMode: document.getElementById('trading-mode'),

    // Control.json
    controlTradingMode: document.getElementById('control-trading-mode'),
    controlOrdersEnabled: document.getElementById('control-orders-enabled'),
    controlDryRun: document.getElementById('control-dry-run'),
    controlOverrideFile: document.getElementById('control-override-file'),
    controlOverrideStatus: document.getElementById('control-override-status'),
    effectiveMode: document.getElementById('effective-mode'),
    liveTradingEnabled: document.getElementById('live-trading-enabled'),
    controlValidationRow: document.getElementById('control-validation-row'),
    controlValidationErrors: document.getElementById('control-validation-errors'),
    controlReasonInput: document.getElementById('control-reason-input'),
    saveControlBtn: document.getElementById('save-control-btn'),
    controlSaveStatus: document.getElementById('control-save-status'),
    refreshControlBtn: document.getElementById('refresh-control-btn'),

    // Audit
    auditLog: document.getElementById('audit-log'),
    refreshAuditBtn: document.getElementById('refresh-audit-btn'),

    // Modal
    modal: document.getElementById('confirmation-modal'),
    modalTitle: document.getElementById('modal-title'),
    modalMessage: document.getElementById('modal-message'),
    confirmationWord: document.getElementById('confirmation-word'),
    confirmationInput: document.getElementById('confirmation-input'),
    modalCancel: document.getElementById('modal-cancel'),
    modalConfirm: document.getElementById('modal-confirm'),
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    loadSavedToken();
    fetchStatus();
    fetchControlSettings();
    fetchAuditLog();
    startPolling();
});

// Event Listeners
function setupEventListeners() {
    // Token management
    elements.saveTokenBtn.addEventListener('click', saveToken);
    elements.adminTokenInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') saveToken();
    });

    // Audit refresh
    elements.refreshAuditBtn.addEventListener('click', fetchAuditLog);

    // Control.json save
    if (elements.saveControlBtn) {
        elements.saveControlBtn.addEventListener('click', saveControlSettings);
    }
    if (elements.refreshControlBtn) {
        elements.refreshControlBtn.addEventListener('click', fetchControlSettings);
    }

    // Modal
    elements.modalCancel.addEventListener('click', hideModal);
    elements.modalConfirm.addEventListener('click', confirmAction);
    elements.confirmationInput.addEventListener('input', validateConfirmation);

    // Close modal on outside click
    elements.modal.addEventListener('click', (e) => {
        if (e.target === elements.modal) hideModal();
    });
}

// Token Management
function loadSavedToken() {
    if (adminToken) {
        elements.adminTokenInput.value = adminToken;
        elements.authStatus.textContent = 'Token loaded from storage';
        elements.authStatus.className = 'status-text success';
    }
}

function saveToken() {
    adminToken = elements.adminTokenInput.value.trim();
    if (adminToken) {
        localStorage.setItem('adminToken', adminToken);
        elements.authStatus.textContent = 'Token saved';
        elements.authStatus.className = 'status-text success';
        fetchStatus();
        fetchControlSettings();
        fetchAuditLog();
    } else {
        localStorage.removeItem('adminToken');
        elements.authStatus.textContent = 'Token cleared';
        elements.authStatus.className = 'status-text';
    }
}

function scheduleRunWindowClear(nextStartIso) {
    if (runWindowTimer) {
        clearTimeout(runWindowTimer);
        runWindowTimer = null;
    }
    if (!nextStartIso) return;
    const nextStartMs = Date.parse(nextStartIso);
    if (Number.isNaN(nextStartMs)) return;
    const delay = nextStartMs - Date.now();
    if (delay <= 0) {
        hideRunWindowBanner();
        return;
    }
    runWindowTimer = setTimeout(() => {
        hideRunWindowBanner();
    }, delay + 1000);
}

function hideRunWindowBanner() {
    if (!elements.runWindowBanner) return;
    if (runWindowTimer) {
        clearTimeout(runWindowTimer);
        runWindowTimer = null;
    }
    elements.runWindowBanner.classList.add('hidden');
}

function formatWindowDays(days) {
    if (!days) return '';
    if (Array.isArray(days)) return days.join(', ');
    if (typeof days === 'string') {
        return days.split(',').map((day) => day.trim()).filter(Boolean).join(', ');
    }
    return '';
}

function formatDateTimeInZone(isoString, timeZone) {
    if (!isoString) return '--';
    try {
        const date = new Date(isoString);
        if (!timeZone) {
            return date.toLocaleString();
        }
        return new Intl.DateTimeFormat(undefined, {
            timeZone,
            year: 'numeric',
            month: 'short',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        }).format(date);
    } catch {
        return isoString;
    }
}

function showRunWindowBanner(detail) {
    if (!elements.runWindowBanner) return;
    const message = detail?.message || 'Service unavailable outside run window.';
    elements.runWindowMessage.textContent = message;

    const tz = detail?.window_timezone || detail?.timezone;
    const nextStart = detail?.next_window_start;
    const nextEnd = detail?.next_window_end;
    const windowStart = detail?.window_start;
    const windowEnd = detail?.window_end;
    const windowDays = formatWindowDays(detail?.window_days);
    const tzSuffix = tz ? ` ${tz}` : '';

    if (nextStart && nextEnd) {
        const startText = formatDateTimeInZone(nextStart, tz);
        const endText = formatDateTimeInZone(nextEnd, tz);
        elements.runWindowNext.textContent = `Next window: ${startText} - ${endText}${tzSuffix}`;
        scheduleRunWindowClear(nextStart);
    } else if (windowStart && windowEnd) {
        const daysSuffix = windowDays ? ` on ${windowDays}` : '';
        elements.runWindowNext.textContent = `Window hours: ${windowStart}-${windowEnd}${tzSuffix}${daysSuffix}`;
    } else {
        elements.runWindowNext.textContent = '';
    }

    elements.runWindowBanner.classList.remove('hidden');
}

function getRunWindowDetail(data) {
    if (!data) return { message: 'Service unavailable outside run window.' };
    const detail = data.detail ?? data;
    if (typeof detail === 'string') {
        return { message: detail };
    }
    if (detail && typeof detail === 'object') {
        return detail;
    }
    if (typeof data.message === 'string') {
        return { message: data.message };
    }
    return { message: 'Service unavailable outside run window.' };
}

function isOutsideRunWindowError(data, response) {
    if (!response || response.status !== 503) return false;
    const detail = data?.detail;
    if (typeof detail === 'string') {
        return detail.toLowerCase().includes('outside run window');
    }
    if (detail && typeof detail === 'object') {
        if (detail.error === 'OUTSIDE_RUN_WINDOW') return true;
        if (typeof detail.message === 'string') {
            return detail.message.toLowerCase().includes('outside run window');
        }
    }
    if (typeof data?.message === 'string') {
        return data.message.toLowerCase().includes('outside run window');
    }
    return false;
}

function getErrorMessage(data, response) {
    if (data) {
        if (typeof data.detail === 'string') {
            return data.detail;
        }
        if (data.detail && typeof data.detail === 'object' && typeof data.detail.message === 'string') {
            return data.detail.message;
        }
        if (typeof data.message === 'string') {
            return data.message;
        }
    }
    return `HTTP ${response?.status || 'error'}`;
}

// API Calls
async function apiCall(endpoint, options = {}) {
    const url = `${CONFIG.apiBaseUrl}${endpoint}`;
    const headers = {
        'Content-Type': 'application/json',
        ...(adminToken && { 'X-Admin-Token': adminToken }),
    };

    try {
        const response = await fetch(url, { ...options, headers });
        let data = null;
        try {
            data = await response.json();
        } catch {
            data = null;
        }

        if (!response.ok) {
            if (isOutsideRunWindowError(data, response)) {
                showRunWindowBanner(getRunWindowDetail(data));
            }
            throw new Error(getErrorMessage(data, response));
        }

        return data;
    } catch (error) {
        console.error(`API call failed: ${endpoint}`, error);
        throw error;
    }
}

// Status Polling
function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(fetchStatus, CONFIG.pollInterval);
}

function stopPolling() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

async function fetchStatus() {
    try {
        const status = await apiCall('/admin/status');
        updateTradingStatus(status);
        setConnectionStatus(true);
        hideRunWindowBanner();
    } catch (error) {
        setConnectionStatus(false);
        console.error('Failed to fetch status:', error);
    }
}

async function fetchControlSettings() {
    try {
        const status = await apiCall('/admin/status');
        updateControlDisplay(status);
        updateTradingStatus(status);
        setConnectionStatus(true);
        hideRunWindowBanner();
    } catch (error) {
        controlStateSnapshot = null;
        if (elements.controlSaveStatus) {
            elements.controlSaveStatus.textContent = `Refresh failed: ${error.message}`;
            elements.controlSaveStatus.className = 'status-text error';
        }
        setConnectionStatus(false);
        console.error('Failed to fetch control settings:', error);
    }
}

function updateTradingStatus(status) {
    // Main status
    const isEnabled = Boolean(status.orders_enabled);
    elements.statusValue.textContent = isEnabled ? 'ENABLED' : 'DISABLED';
    elements.statusValue.className = `status-badge ${isEnabled ? 'enabled' : 'disabled'}`;

    // Trading mode (paper/live)
    const modeValue = status.trading_mode ? String(status.trading_mode).toLowerCase() : '';
    if (elements.tradingMode) {
        if (modeValue === 'paper' || modeValue === 'live') {
            elements.tradingMode.textContent = modeValue.toUpperCase();
            elements.tradingMode.className = `mode-badge ${modeValue}`;
        } else {
            elements.tradingMode.textContent = '--';
            elements.tradingMode.className = '';
        }
    }

}

function updateControlDisplay(status) {
    if (elements.controlTradingMode && status.trading_mode) {
        elements.controlTradingMode.value = status.trading_mode;
    }
    if (elements.controlOrdersEnabled) {
        elements.controlOrdersEnabled.checked = Boolean(status.orders_enabled);
    }
    if (elements.controlDryRun) {
        elements.controlDryRun.checked = Boolean(status.dry_run);
    }
    if (elements.controlOverrideFile) {
        elements.controlOverrideFile.value = status.live_trading_override_file || '';
    }
    if (elements.effectiveMode) {
        let effectiveLabel = '--';
        if (status.orders_enabled === false) {
            effectiveLabel = 'ORDERS DISABLED';
        } else if (typeof status.effective_dry_run === 'boolean') {
            effectiveLabel = status.effective_dry_run ? 'DRY RUN' : 'LIVE ORDERS';
        }
        elements.effectiveMode.textContent = effectiveLabel;
    }
    if (elements.liveTradingEnabled) {
        const liveEnabled = Boolean(status.is_live_trading_enabled);
        elements.liveTradingEnabled.textContent = liveEnabled ? 'YES' : 'NO';
    }
    if (elements.controlOverrideStatus) {
        const isLiveEnabled = Boolean(status.is_live_trading_enabled);
        if (!isLiveEnabled) {
            elements.controlOverrideStatus.textContent = 'Not required (paper mode or orders disabled).';
            elements.controlOverrideStatus.className = 'status-text';
        } else if (status.override_file_exists) {
            elements.controlOverrideStatus.textContent = 'Override file present.';
            elements.controlOverrideStatus.className = 'status-text success';
        } else {
            const message = status.override_file_message || 'Override file missing.';
            elements.controlOverrideStatus.textContent = message;
            elements.controlOverrideStatus.className = 'status-text error';
        }
    }
    if (elements.controlValidationRow && elements.controlValidationErrors) {
        const errors = status.validation_errors || [];
        if (errors.length > 0) {
            elements.controlValidationErrors.textContent = errors.join('; ');
            elements.controlValidationRow.classList.remove('hidden');
        } else {
            elements.controlValidationErrors.textContent = '--';
            elements.controlValidationRow.classList.add('hidden');
        }
    }

    controlStateSnapshot = {
        trading_mode: status.trading_mode || '',
        orders_enabled: Boolean(status.orders_enabled),
        dry_run: Boolean(status.dry_run),
        live_trading_override_file: normalizeOverrideValue(status.live_trading_override_file),
    };
}

function normalizeOverrideValue(value) {
    if (!value) return '';
    return String(value).trim();
}

function buildControlPayload(reason) {
    return {
        reason,
        trading_mode: elements.controlTradingMode?.value || null,
        orders_enabled: Boolean(elements.controlOrdersEnabled?.checked),
        dry_run: Boolean(elements.controlDryRun?.checked),
        live_trading_override_file: normalizeOverrideValue(elements.controlOverrideFile?.value) || null,
    };
}

async function saveControlSettings() {
    if (!elements.controlReasonInput) return;
    const reason = elements.controlReasonInput.value.trim();
    if (!reason) {
        elements.controlSaveStatus.textContent = 'Reason is required.';
        elements.controlSaveStatus.className = 'status-text error';
        elements.controlReasonInput.focus();
        return;
    }

    elements.controlSaveStatus.textContent = '';
    elements.controlSaveStatus.className = 'status-text';

    const payload = buildControlPayload(reason);
    const previousOrdersEnabled = controlStateSnapshot?.orders_enabled;
    const ordersEnabledChanged = typeof previousOrdersEnabled === 'boolean'
        && payload.orders_enabled !== previousOrdersEnabled;

    if (ordersEnabledChanged) {
        const action = payload.orders_enabled ? 'enable' : 'disable';
        showControlConfirmation(action, payload);
        return;
    }

    await submitControlSettings(payload);
}

function setConnectionStatus(connected) {
    elements.connectionStatus.textContent = connected ? 'Connected' : 'Disconnected';
    elements.connectionStatus.className = `status-badge ${connected ? 'connected' : 'disconnected'}`;
}

// Audit Log
async function fetchAuditLog() {
    try {
        const data = await apiCall('/admin/audit-log?lines=50');
        displayAuditLog(data.entries || []);
    } catch (error) {
        elements.auditLog.innerHTML = '';
        const message = `Failed to load audit log: ${error.message}`;
        const placeholder = document.createElement('p');
        placeholder.className = 'loading-text';
        placeholder.textContent = message;
        elements.auditLog.appendChild(placeholder);
    }
}

function displayAuditLog(entries) {
    if (entries.length === 0) {
        elements.auditLog.innerHTML = '<p class="loading-text">No audit entries found</p>';
        return;
    }

    elements.auditLog.innerHTML = entries.map(entry => {
        const actionClass = entry.action?.toLowerCase().includes('enable') ? 'enable' :
                           entry.action?.toLowerCase().includes('disable') ? 'disable' : '';

        return `
            <div class="audit-entry ${actionClass}">
                <span class="audit-timestamp">${formatDateTime(entry.timestamp)}</span>
                <span class="audit-user">${entry.user || '--'}</span>
                <span class="audit-action ${actionClass}">${entry.action || '--'}</span>
                <span class="audit-reason">${entry.reason || ''}</span>
            </div>
        `;
    }).join('');
}

// Confirmation Modal
function showControlConfirmation(action, payload) {
    pendingAction = { action, payload };
    const word = action.toUpperCase();
    elements.modalTitle.textContent = `Confirm ${action === 'enable' ? 'Enable' : 'Disable'} Orders`;
    elements.modalMessage.textContent = action === 'enable'
        ? 'This will set orders_enabled=true in control.json.'
        : 'This will set orders_enabled=false in control.json.';
    elements.confirmationWord.textContent = word;
    elements.confirmationInput.value = '';
    elements.confirmationInput.placeholder = `Type ${word} to confirm`;
    elements.modalConfirm.disabled = true;
    elements.modalConfirm.className = `btn ${action === 'enable' ? 'btn-success' : 'btn-danger'}`;

    elements.modal.classList.remove('hidden');
    elements.confirmationInput.focus();
}

function hideModal() {
    elements.modal.classList.add('hidden');
    pendingAction = null;
}

function validateConfirmation() {
    if (!pendingAction) return;
    const expected = pendingAction.action.toUpperCase();
    const entered = elements.confirmationInput.value.toUpperCase();
    elements.modalConfirm.disabled = entered !== expected;
}

async function confirmAction() {
    if (!pendingAction) return;

    const { payload } = pendingAction;
    hideModal();
    await submitControlSettings(payload);
}

async function submitControlSettings(payload) {
    try {
        const response = await apiCall('/admin/control', {
            method: 'PUT',
            body: JSON.stringify(payload),
        });

        if (response.status) {
            updateTradingStatus(response.status);
            updateControlDisplay(response.status);
        } else {
            await fetchStatus();
            await fetchControlSettings();
        }
        await fetchAuditLog();

        elements.controlSaveStatus.textContent = response.message || 'Control settings updated.';
        elements.controlSaveStatus.className = 'status-text success';
        elements.controlReasonInput.value = '';
        hideRunWindowBanner();
    } catch (error) {
        elements.controlSaveStatus.textContent = `Update failed: ${error.message}`;
        elements.controlSaveStatus.className = 'status-text error';
    }
}

// Utility Functions
function formatDateTime(isoString) {
    if (!isoString) return '--';
    try {
        const date = new Date(isoString);
        return date.toLocaleString();
    } catch {
        return isoString;
    }
}

function formatDuration(seconds) {
    if (seconds < 60) {
        return `${Math.round(seconds)} seconds`;
    }
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) {
        return `${minutes} minute${minutes !== 1 ? 's' : ''}`;
    }
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    if (remainingMinutes === 0) {
        return `${hours} hour${hours !== 1 ? 's' : ''}`;
    }
    return `${hours}h ${remainingMinutes}m`;
}
