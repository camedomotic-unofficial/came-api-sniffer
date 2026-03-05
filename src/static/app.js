/**
 * CAME API Sniffer Dashboard - Vanilla JavaScript Application
 */

// Application state
const state = {
    exchanges: [],
    currentPage: 1,
    pageSize: 20,
    totalCount: 0,
    totalPages: 0,
    selectedExchange: null,
    pendingExchanges: [],
    autoRefresh: true,
    filters: {
        search: '',
        session_id: '',
        app_method: '',
        from_ts: '',
        to_ts: ''
    },
    wsConnected: false,
    exportMode: null
};

// API Client
const api = {
    async getExchanges(filters = {}) {
        const params = new URLSearchParams({
            page: state.currentPage,
            page_size: state.pageSize,
            ...filters
        });
        const response = await fetch(`/api/exchanges?${params}`);
        return await response.json();
    },

    async getExchange(exchangeId) {
        const response = await fetch(`/api/exchanges/${exchangeId}`);
        return await response.json();
    },

    async getSessions() {
        const response = await fetch('/api/sessions');
        return await response.json();
    },

    async getMethods() {
        const response = await fetch('/api/methods');
        return await response.json();
    },

    async getStats() {
        const response = await fetch('/api/stats');
        return await response.json();
    },

    async deleteAll() {
        const response = await fetch('/api/exchanges', { method: 'DELETE' });
        return await response.json();
    },

    async export(mode, params = {}) {
        const queryParams = new URLSearchParams({ mode, ...params });
        window.location.href = `/api/export?${queryParams}`;
    }
};

// WebSocket Manager
const ws = {
    connection: null,
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws`;

        this.connection = new WebSocket(url);

        this.connection.onopen = () => {
            console.log('WebSocket connected');
            state.wsConnected = true;
            this.reconnectAttempts = 0;
            updateWSIndicator();
        };

        this.connection.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'new_exchange') {
                    handleNewExchange(data);
                }
            } catch (e) {
                console.error('Error parsing WebSocket message:', e);
            }
        };

        this.connection.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.connection.onclose = () => {
            console.log('WebSocket disconnected');
            state.wsConnected = false;
            updateWSIndicator();
            this.reconnect();
        };
    },

    reconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.pow(2, this.reconnectAttempts) * 1000;
            console.log(`Reconnecting WebSocket in ${delay}ms...`);
            setTimeout(() => this.connect(), delay);
        }
    }
};

// DOM Utilities
function updateWSIndicator() {
    const indicator = document.getElementById('ws-indicator');
    const dot = indicator.querySelector('.ws-dot');
    const label = indicator.querySelector('.ws-label');

    if (state.wsConnected) {
        dot.classList.add('connected');
        label.textContent = 'Connected';
    } else {
        dot.classList.remove('connected');
        label.textContent = 'Disconnected';
    }
}

function formatTimestamp(ts) {
    if (!ts) return 'N/A';
    const date = new Date(ts);
    return date.toLocaleString();
}

function formatDuration(ms) {
    if (!ms) return 'N/A';
    return `${ms}ms`;
}

function getStatusClass(statusCode) {
    if (!statusCode) return '';
    if (statusCode < 300) return 'status-2xx';
    if (statusCode < 400) return 'status-3xx';
    if (statusCode < 500) return 'status-4xx';
    return 'status-5xx';
}

function formatJSON(obj) {
    if (!obj) return '';
    if (typeof obj === 'string') return obj;
    return JSON.stringify(obj, null, 2);
}

function syntaxHighlightJSON(json) {
    if (!json) return '';

    return json
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, (match) => {
            let cls = 'json-number';
            if (/^"/.test(match)) {
                if (/:$/.test(match)) {
                    cls = 'json-key';
                } else {
                    cls = 'json-string';
                }
            } else if (/true|false/.test(match)) {
                cls = 'json-boolean';
            } else if (/null/.test(match)) {
                cls = 'json-null';
            }
            return `<span class="${cls}">${match}</span>`;
        });
}

// Render functions
async function renderExchangeList() {
    const tbody = document.getElementById('exchange-tbody');
    tbody.innerHTML = '';

    const results = await api.getExchanges(state.filters);
    state.exchanges = results.exchanges;
    state.totalCount = results.total_count;
    state.totalPages = results.total_pages;
    state.currentPage = results.page;

    document.getElementById('total-exchanges').textContent = state.totalCount;

    if (state.exchanges.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 32px;">No exchanges found</td></tr>';
        updatePagination();
        return;
    }

    state.exchanges.forEach(exchange => {
        const row = document.createElement('tr');
        row.onclick = () => showDetail(exchange.exchange_id);

        const statusClass = getStatusClass(exchange.status_code);
        const statusCode = exchange.status_code || '-';

        row.innerHTML = `
            <td>${formatTimestamp(exchange.timestamp_start)}</td>
            <td>${exchange.session_id || 'N/A'}</td>
            <td><span class="method-badge">${exchange.app_method || 'N/A'}</span></td>
            <td>${exchange.path || '/'}</td>
            <td class="${statusClass}">${statusCode}</td>
            <td>${formatDuration(exchange.duration_ms)}</td>
        `;
        tbody.appendChild(row);
    });

    updatePagination();
}

function updatePagination() {
    const pageInfo = document.getElementById('page-info');
    const prevBtn = document.getElementById('prev-page');
    const nextBtn = document.getElementById('next-page');

    pageInfo.textContent = `${state.currentPage} / ${state.totalPages || 1}`;
    prevBtn.disabled = state.currentPage <= 1;
    nextBtn.disabled = state.currentPage >= state.totalPages;
}

async function showDetail(exchangeId) {
    const exchange = await api.getExchange(exchangeId);
    state.selectedExchange = exchange;

    const panel = document.getElementById('detail-panel');
    const content = document.getElementById('detail-content');

    content.innerHTML = `
        <div class="detail-section">
            <div class="detail-section-title">Exchange Information</div>
            <div class="detail-field">
                <span class="detail-field-label">ID</span>
                <span class="detail-field-value">${exchange.exchange_id}</span>
            </div>
            <div class="detail-field">
                <span class="detail-field-label">Session ID</span>
                <span class="detail-field-value">${exchange.session_id || 'N/A'}</span>
            </div>
            <div class="detail-field">
                <span class="detail-field-label">Method</span>
                <span class="detail-field-value">${exchange.app_method || 'N/A'}</span>
            </div>
            <div class="detail-field">
                <span class="detail-field-label">Time</span>
                <span class="detail-field-value">${formatTimestamp(exchange.timestamp_start)} → ${formatTimestamp(exchange.timestamp_end)} (${exchange.duration_ms}ms)</span>
            </div>
        </div>

        <div class="detail-section">
            <div class="detail-section-title">Request</div>
            <div class="detail-field">
                <span class="detail-field-label">Method & URL</span>
                <span class="detail-field-value">${exchange.method} ${exchange.path}${exchange.query_string || ''}</span>
            </div>
            <div class="detail-field">
                <span class="headers-collapsible">Headers (${Object.keys(exchange.request_headers || {}).length})</span>
                <div class="headers-content">
                    ${renderHeaders(exchange.request_headers || {})}
                </div>
            </div>
            ${exchange.request_body ? `
            <div class="detail-field">
                <span class="detail-field-label">Body</span>
                <div class="json-code">${syntaxHighlightJSON(formatJSON(exchange.request_body))}</div>
            </div>
            ` : ''}
        </div>

        <div class="detail-section">
            <div class="detail-section-title">Response</div>
            <div class="detail-field">
                <span class="detail-field-label">Status</span>
                <span class="detail-field-value ${getStatusClass(exchange.status_code)}">${exchange.status_code}</span>
            </div>
            <div class="detail-field">
                <span class="headers-collapsible">Headers (${Object.keys(exchange.response_headers || {}).length})</span>
                <div class="headers-content">
                    ${renderHeaders(exchange.response_headers || {})}
                </div>
            </div>
            ${exchange.response_body ? `
            <div class="detail-field">
                <span class="detail-field-label">Body</span>
                <div class="json-code">${syntaxHighlightJSON(formatJSON(exchange.response_body))}</div>
            </div>
            ` : ''}
        </div>

        <div class="action-buttons">
            <button class="btn btn-primary" onclick="copyAsCurl()">📋 Copy as cURL</button>
            <button class="btn btn-primary" onclick="exportExchange()">💾 Export as TXT</button>
        </div>
    `;

    panel.style.display = 'block';

    // Add event listeners for headers collapse
    content.querySelectorAll('.headers-collapsible').forEach(el => {
        el.onclick = (e) => {
            e.target.classList.toggle('collapsed');
        };
    });
}

function renderHeaders(headers) {
    return Object.entries(headers)
        .map(([key, value]) => `<div class="header-row"><span class="header-key">${key}:</span> <span class="header-value">${value}</span></div>`)
        .join('');
}

async function copyAsCurl() {
    if (!state.selectedExchange) return;

    const ex = state.selectedExchange;
    let cmd = `curl -X ${ex.method} 'http://${window.location.host}${ex.path}${ex.query_string || ''}'`;

    // Add headers
    Object.entries(ex.request_headers || {}).forEach(([key, value]) => {
        cmd += ` -H '${key}: ${value}'`;
    });

    // Add body if present
    if (ex.request_body) {
        const body = typeof ex.request_body === 'string' ? ex.request_body : JSON.stringify(ex.request_body);
        cmd += ` -d '${body.replace(/'/g, "'\\''")}'`;
    }

    await navigator.clipboard.writeText(cmd);
    alert('cURL command copied to clipboard');
}

async function exportExchange() {
    if (!state.selectedExchange) return;

    const ex = state.selectedExchange;
    const content = formatExchangeAsText(ex);

    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `exchange_${ex.exchange_id.substring(0, 8)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function formatExchangeAsText(ex) {
    const separator = '='.repeat(70);
    const sep_req = '-'.repeat(70);

    let text = `${separator}\n`;
    text += `EXCHANGE: ${ex.exchange_id}\n`;
    text += `SESSION:  ${ex.session_id || 'N/A'}\n`;
    text += `METHOD:   ${ex.app_method || 'N/A'}\n`;
    text += `TIME:     ${formatTimestamp(ex.timestamp_start)} → ${formatTimestamp(ex.timestamp_end)} (${ex.duration_ms}ms)\n`;
    text += `${separator}\n\n`;

    text += `${sep_req}\nREQUEST\n${sep_req}\n`;
    text += `${ex.method} ${ex.path}${ex.query_string || ''}\n\n`;

    if (Object.keys(ex.request_headers || {}).length > 0) {
        text += `Headers:\n`;
        Object.entries(ex.request_headers).forEach(([key, value]) => {
            text += `  ${key}: ${value}\n`;
        });
        text += `\n`;
    }

    if (ex.request_body) {
        text += `Body:\n${formatJSON(ex.request_body)}\n\n`;
    }

    text += `${sep_req}\nRESPONSE\n${sep_req}\n`;
    text += `Status: ${ex.status_code}\n\n`;

    if (Object.keys(ex.response_headers || {}).length > 0) {
        text += `Headers:\n`;
        Object.entries(ex.response_headers).forEach(([key, value]) => {
            text += `  ${key}: ${value}\n`;
        });
        text += `\n`;
    }

    if (ex.response_body) {
        text += `Body:\n${formatJSON(ex.response_body)}\n\n`;
    }

    text += `${separator}\n`;
    return text;
}

function handleNewExchange(exchange) {
    if (state.autoRefresh) {
        state.pendingExchanges = [];
        renderExchangeList();
    } else {
        state.pendingExchanges.push(exchange);
        updatePendingBadge();
    }
}

function updatePendingBadge() {
    const badge = document.getElementById('pending-badge');
    const count = document.getElementById('pending-count');

    if (state.pendingExchanges.length > 0) {
        count.textContent = state.pendingExchanges.length;
        badge.style.display = 'block';
    } else {
        badge.style.display = 'none';
    }
}

// Event Listeners
function setupEventListeners() {
    // Filters
    document.getElementById('search-btn').onclick = () => {
        state.currentPage = 1;
        state.filters = {
            search: document.getElementById('search-text').value,
            session_id: document.getElementById('session-id').value,
            app_method: document.getElementById('app-method').value,
            from_ts: document.getElementById('from-ts').value,
            to_ts: document.getElementById('to-ts').value
        };
        renderExchangeList();
    };

    document.getElementById('reset-btn').onclick = () => {
        state.currentPage = 1;
        state.filters = { search: '', session_id: '', app_method: '', from_ts: '', to_ts: '' };
        document.getElementById('search-text').value = '';
        document.getElementById('session-id').value = '';
        document.getElementById('app-method').value = '';
        document.getElementById('from-ts').value = '';
        document.getElementById('to-ts').value = '';
        renderExchangeList();
    };

    // Pagination
    document.getElementById('prev-page').onclick = () => {
        if (state.currentPage > 1) {
            state.currentPage--;
            renderExchangeList();
        }
    };

    document.getElementById('next-page').onclick = () => {
        if (state.currentPage < state.totalPages) {
            state.currentPage++;
            renderExchangeList();
        }
    };

    // Auto-refresh
    document.getElementById('auto-refresh').onchange = (e) => {
        state.autoRefresh = e.target.checked;
        if (state.autoRefresh) {
            state.pendingExchanges = [];
            updatePendingBadge();
            renderExchangeList();
        }
    };

    // Pending badge
    document.getElementById('pending-badge').onclick = () => {
        state.pendingExchanges = [];
        updatePendingBadge();
        renderExchangeList();
    };

    // Close detail panel
    document.getElementById('close-detail').onclick = () => {
        document.getElementById('detail-panel').style.display = 'none';
    };

    // Export dropdown
    document.getElementById('export-btn').onclick = (e) => {
        e.stopPropagation();
        document.getElementById('export-menu').classList.toggle('open');
    };

    document.querySelectorAll('.export-option').forEach(btn => {
        btn.onclick = async (e) => {
            const mode = e.target.dataset.mode;
            document.getElementById('export-menu').classList.remove('open');

            if (mode === 'current') {
                const params = new URLSearchParams({
                    page: 1,
                    page_size: 10000,
                    ...state.filters
                });
                window.location.href = `/api/export?mode=all&${new URLSearchParams(state.filters)}`;
            } else {
                showExportModal(mode);
            }
        };
    });

    // Modal
    document.getElementById('close-modal').onclick = () => {
        document.getElementById('export-modal').style.display = 'none';
    };

    document.getElementById('export-confirm').onclick = async () => {
        const mode = state.exportMode;
        const params = {};

        if (mode === 'session') {
            params.session_id = document.getElementById('export-session-select').value;
        } else if (mode === 'range') {
            params.from_ts = document.getElementById('export-from').value;
            params.to_ts = document.getElementById('export-to').value;
        }

        await api.export(mode, params);
        document.getElementById('export-modal').style.display = 'none';
    };
}

async function showExportModal(mode) {
    state.exportMode = mode;
    const modal = document.getElementById('export-modal');
    const form = document.getElementById('export-form');

    form.innerHTML = '';

    if (mode === 'session') {
        const sessions = await api.getSessions();
        form.innerHTML = `
            <div class="form-group">
                <label>Select Session:</label>
                <select id="export-session-select">
                    ${sessions.sessions.map(s => `<option value="${s.session_id}">${s.session_id} (${s.count})</option>`).join('')}
                </select>
            </div>
        `;
    } else if (mode === 'range') {
        form.innerHTML = `
            <div class="form-group">
                <label>From:</label>
                <input type="datetime-local" id="export-from">
            </div>
            <div class="form-group">
                <label>To:</label>
                <input type="datetime-local" id="export-to">
            </div>
        `;
    }

    modal.style.display = 'flex';
}

// Initialize
async function init() {
    await renderExchangeList();
    await loadFilterOptions();
    setupEventListeners();
    ws.connect();

    // Refresh stats periodically
    setInterval(async () => {
        const stats = await api.getStats();
        document.getElementById('total-exchanges').textContent = stats.total_exchanges;
    }, 5000);
}

async function loadFilterOptions() {
    const methods = await api.getMethods();
    const methodSelect = document.getElementById('app-method');
    methods.methods.forEach(m => {
        const option = document.createElement('option');
        option.value = m.app_method;
        option.textContent = `${m.app_method} (${m.count})`;
        methodSelect.appendChild(option);
    });
}

// Start application
document.addEventListener('DOMContentLoaded', init);
