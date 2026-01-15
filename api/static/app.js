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

// DOM Elements
const elements = {
    // Auth
    adminTokenInput: document.getElementById('admin-token'),
    saveTokenBtn: document.getElementById('save-token-btn'),
    authStatus: document.getElementById('auth-status'),
    connectionStatus: document.getElementById('connection-status'),

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

// API Calls
async function apiCall(endpoint, options = {}) {
    const url = `${CONFIG.apiBaseUrl}${endpoint}`;
    const headers = {
        'Content-Type': 'application/json',
        ...(adminToken && { 'X-Admin-Token': adminToken }),
    };

    try {
        const response = await fetch(url, { ...options, headers });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail?.message || data.message || `HTTP ${response.status}`);
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
