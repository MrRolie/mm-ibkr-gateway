/**
 * MM-Control Operator Dashboard
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
    guardFileStatus: document.getElementById('guard-file-status'),
    disabledBy: document.getElementById('disabled-by'),
    disabledReason: document.getElementById('disabled-reason'),
    disabledAt: document.getElementById('disabled-at'),
    timeUntilExpiry: document.getElementById('time-until-expiry'),
    ttlRow: document.getElementById('ttl-row'),

    // Controls
    enableBtn: document.getElementById('enable-btn'),
    disableBtn: document.getElementById('disable-btn'),
    ttlSelect: document.getElementById('ttl-select'),
    customTtlGroup: document.getElementById('custom-ttl-group'),
    customTtlInput: document.getElementById('custom-ttl'),
    reasonInput: document.getElementById('reason-input'),

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
    startPolling();
    fetchAuditLog();
});

// Event Listeners
function setupEventListeners() {
    // Token management
    elements.saveTokenBtn.addEventListener('click', saveToken);
    elements.adminTokenInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') saveToken();
    });

    // Control buttons
    elements.enableBtn.addEventListener('click', () => showConfirmation('enable'));
    elements.disableBtn.addEventListener('click', () => showConfirmation('disable'));

    // TTL selector
    elements.ttlSelect.addEventListener('change', () => {
        elements.customTtlGroup.classList.toggle('hidden', elements.ttlSelect.value !== 'custom');
    });

    // Audit refresh
    elements.refreshAuditBtn.addEventListener('click', fetchAuditLog);

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
    fetchStatus();
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
        updateStatusDisplay(status);
        setConnectionStatus(true);
    } catch (error) {
        setConnectionStatus(false);
        console.error('Failed to fetch status:', error);
    }
}

function updateStatusDisplay(status) {
    // Main status
    const isEnabled = status.trading_enabled;
    elements.statusValue.textContent = isEnabled ? 'ENABLED' : 'DISABLED';
    elements.statusValue.className = `status-badge ${isEnabled ? 'enabled' : 'disabled'}`;

    // Guard file
    elements.guardFileStatus.textContent = status.guard_file_exists ? 'Present (blocking)' : 'Not present';

    // Disable details
    elements.disabledBy.textContent = status.disabled_by || '--';
    elements.disabledReason.textContent = status.disabled_reason || '--';
    elements.disabledAt.textContent = status.disabled_at ? formatDateTime(status.disabled_at) : '--';

    // TTL
    if (status.time_until_expiry_seconds && status.time_until_expiry_seconds > 0) {
        elements.ttlRow.classList.remove('hidden');
        elements.timeUntilExpiry.textContent = formatDuration(status.time_until_expiry_seconds);
    } else {
        elements.ttlRow.classList.add('hidden');
        elements.timeUntilExpiry.textContent = '--';
    }

    // Update button states
    elements.enableBtn.disabled = isEnabled;
    elements.disableBtn.disabled = !isEnabled;
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
        elements.auditLog.innerHTML = '<p class="loading-text">Failed to load audit log</p>';
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
function showConfirmation(action) {
    const reason = elements.reasonInput.value.trim();
    if (!reason) {
        alert('Please enter a reason for this action');
        elements.reasonInput.focus();
        return;
    }

    pendingAction = {
        action,
        reason,
        ttl: action === 'disable' ? getTtlValue() : null,
    };

    const word = action.toUpperCase();
    elements.modalTitle.textContent = `Confirm ${action === 'enable' ? 'Enable' : 'Disable'} Trading`;
    elements.modalMessage.textContent = action === 'enable'
        ? 'This will enable live trading operations.'
        : `This will disable all trading operations${pendingAction.ttl ? ` for ${pendingAction.ttl} minutes` : ''}.`;
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
    const expected = pendingAction?.action?.toUpperCase() || '';
    const entered = elements.confirmationInput.value.toUpperCase();
    elements.modalConfirm.disabled = entered !== expected;
}

async function confirmAction() {
    if (!pendingAction) return;

    const { action, reason, ttl } = pendingAction;
    hideModal();

    try {
        const body = {
            action,
            reason,
            ...(ttl && { ttl_minutes: parseInt(ttl, 10) }),
        };

        const result = await apiCall('/admin/toggle', {
            method: 'POST',
            body: JSON.stringify(body),
        });

        // Refresh status and audit log
        await fetchStatus();
        await fetchAuditLog();

        // Clear reason input
        elements.reasonInput.value = '';

        alert(result.message || 'Action completed successfully');
    } catch (error) {
        alert(`Action failed: ${error.message}`);
    }
}

function getTtlValue() {
    const value = elements.ttlSelect.value;
    if (value === 'custom') {
        return elements.customTtlInput.value;
    }
    return value || null;
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
