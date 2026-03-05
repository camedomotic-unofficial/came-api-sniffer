/**
 * CAME API Sniffer Dashboard - Vanilla JavaScript Application
 */

// Application state
const state = {
    exchanges: [],
    currentPage: 1,
    pageSize: 100,
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
    exportMode: null,
    sessionAnnotations: {}
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

    async updateSessionAnnotation(sessionId, name, notes) {
        const response = await fetch(`/api/sessions/${sessionId}/annotation`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, notes })
        });
        return await response.json();
    },

    async deleteSessionAnnotation(sessionId) {
        const response = await fetch(`/api/sessions/${sessionId}/annotation`, {
            method: 'DELETE'
        });
        return await response.json();
    },

    async deleteSession(sessionId) {
        const response = await fetch(`/api/sessions/${sessionId}`, {
            method: 'DELETE'
        });
        return await response.json();
    },

    async deleteExchange(exchangeId) {
        const response = await fetch(`/api/exchanges/${exchangeId}`, {
            method: 'DELETE'
        });
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
    const d = new Date(ts);
    const pad = n => String(n).padStart(2, '0');
    return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
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

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
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

// Method color palette
const METHOD_COLORS = [
    '#e06c75', '#e5c07b', '#98c379', '#56b6c2', '#61afef',
    '#c678dd', '#d19a66', '#be5046', '#7ec8e3', '#c3a6ff',
    '#f0a1c2', '#a8d5ba', '#f5d76e', '#7fb3d8', '#d4a5a5',
    '#9ad0c2', '#e8b86d', '#b39ddb', '#80cbc4', '#ffab91'
];

function getMethodColor(method) {
    if (!method) return null;
    let hash = 0;
    for (let i = 0; i < method.length; i++) hash = ((hash << 5) - hash + method.charCodeAt(i)) | 0;
    return METHOD_COLORS[Math.abs(hash) % METHOD_COLORS.length];
}

function getSessionDisplay(sessionId) {
    if (!sessionId) return 'N/A';
    const ann = state.sessionAnnotations[sessionId];
    if (ann && ann.session_name) {
        return `${sessionId} (${escapeHtml(ann.session_name)})`;
    }
    return sessionId;
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
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 32px;">No exchanges found</td></tr>';
        updatePagination();
        return;
    }

    state.exchanges.forEach(exchange => {
        const row = document.createElement('tr');
        row.onclick = () => showDetail(exchange.exchange_id);

        const statusClass = getStatusClass(exchange.status_code);
        const statusCode = exchange.status_code || '-';
        const methodColor = getMethodColor(exchange.app_method);
        const methodStyle = methodColor ? `style="color:${methodColor};border-color:${methodColor}44;background-color:${methodColor}22"` : '';

        row.innerHTML = `
            <td>${formatTimestamp(exchange.timestamp_start)}</td>
            <td>${getSessionDisplay(exchange.session_id)}</td>
            <td><span class="method-badge" ${methodStyle}>${exchange.app_method || 'N/A'}</span></td>
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
                <button class="btn-delete-session" onclick="showDeleteExchangeModal('${exchange.exchange_id}')">&#128465;</button>
            </div>
            <div class="detail-field">
                <span class="detail-field-label">Session ID</span>
                <span class="detail-field-value">${exchange.session_id || 'N/A'}</span>
                ${exchange.session_id ? `<button class="btn-edit-session" onclick="showSessionAnnotationModal('${exchange.session_id}')">&#9998;</button><button class="btn-delete-session" onclick="showDeleteSessionModal('${exchange.session_id}')">&#128465;</button>` : ''}
            </div>
            ${(() => {
                const ann = state.sessionAnnotations[exchange.session_id];
                if (!ann || (!ann.session_name && !ann.session_notes)) return '';
                let html = '';
                if (ann.session_name) {
                    html += `<div class="detail-field"><span class="detail-field-label">Session Name</span><span class="detail-field-value">${escapeHtml(ann.session_name)}</span></div>`;
                }
                if (ann.session_notes) {
                    html += `<div class="detail-field detail-field--block"><span class="detail-field-label">Session Notes</span><div class="session-notes">${escapeHtml(ann.session_notes)}</div></div>`;
                }
                return html;
            })()}
            <div class="detail-field">
                <span class="detail-field-label">Method</span>
                <span class="detail-field-value">${exchange.app_method || 'N/A'}</span>
            </div>
            <div class="detail-field">
                <span class="detail-field-label">Time</span>
                <span class="detail-field-value">${formatTimestamp(exchange.timestamp_start)} &rarr; ${formatTimestamp(exchange.timestamp_end)} (${exchange.duration_ms}ms)</span>
            </div>
        </div>

        <div class="detail-section">
            <div class="detail-section-title">Request</div>
            <div class="detail-field">
                <span class="detail-field-label">Method & URI</span>
                <span class="detail-field-value">${exchange.method} ${exchange.path}${exchange.query_string || ''}</span>
            </div>
            <div class="detail-field detail-field--block">
                <span class="headers-collapsible">Headers (${Object.keys(exchange.request_headers || {}).length})</span>
                <div class="headers-content">
                    ${renderHeaders(exchange.request_headers || {})}
                </div>
            </div>
            ${exchange.request_body_parsed ? `
            <div class="detail-field detail-field--block">
                <span class="detail-field-label">Body (parsed)</span>
                <div class="json-code">${syntaxHighlightJSON(formatJSON(exchange.request_body_parsed))}</div>
            </div>
            ` : exchange.request_body ? `
            <div class="detail-field detail-field--block">
                <span class="detail-field-label">Body (raw)</span>
                <div class="json-code">${escapeHtml(exchange.request_body)}</div>
            </div>
            ` : ''}
        </div>

        <div class="detail-section">
            <div class="detail-section-title">Response</div>
            <div class="detail-field">
                <span class="detail-field-label">Status</span>
                <span class="detail-field-value ${getStatusClass(exchange.status_code)}">${exchange.status_code}</span>
            </div>
            <div class="detail-field detail-field--block">
                <span class="headers-collapsible">Headers (${Object.keys(exchange.response_headers || {}).length})</span>
                <div class="headers-content">
                    ${renderHeaders(exchange.response_headers || {})}
                </div>
            </div>
            ${exchange.response_body ? `
            <div class="detail-field detail-field--block">
                <span class="detail-field-label">Body</span>
                <div class="json-code">${syntaxHighlightJSON(formatJSON(exchange.response_body))}</div>
            </div>
            ` : ''}
        </div>

        <div class="action-buttons">
            <button class="btn btn-primary" onclick="copyAsCurl()">Copy as cURL</button>
            <button class="btn btn-primary" onclick="exportExchange()">Export as TXT</button>
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

    // Add raw body if present
    if (ex.request_body) {
        cmd += ` -d '${ex.request_body.replace(/'/g, "'\\''")}'`;
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
    const sep = '-'.repeat(70);

    let text = `${separator}\n`;
    text += `EXCHANGE: ${ex.exchange_id}\n`;
    text += `SESSION:  ${ex.session_id || 'N/A'}\n`;
    text += `METHOD:   ${ex.app_method || 'N/A'}\n`;
    text += `TIME:     ${formatTimestamp(ex.timestamp_start)} → ${formatTimestamp(ex.timestamp_end)} (${ex.duration_ms}ms)\n`;
    text += `${separator}\n\n`;

    // REQUEST — full HTTP format
    text += `${sep}\nREQUEST\n${sep}\n`;
    const qs = ex.query_string ? `?${ex.query_string}` : '';
    text += `${ex.method} ${ex.path}${qs} HTTP/1.1\n`;

    Object.entries(ex.request_headers || {}).forEach(([key, value]) => {
        text += `${key}: ${value}\n`;
    });

    text += `\n`;
    if (ex.request_body) {
        text += `${ex.request_body}\n`;
    }
    text += `\n`;

    // RESPONSE — full HTTP format
    text += `${sep}\nRESPONSE\n${sep}\n`;
    text += `HTTP/1.1 ${ex.status_code}\n`;

    Object.entries(ex.response_headers || {}).forEach(([key, value]) => {
        text += `${key}: ${value}\n`;
    });

    text += `\n`;
    if (ex.response_body) {
        const body = typeof ex.response_body === 'string' ? ex.response_body : JSON.stringify(ex.response_body);
        text += `${body}\n`;
    }
    text += `\n`;

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
        document.getElementById('session-id').selectedIndex = 0;
        document.getElementById('app-method').selectedIndex = 0;
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
            const excludeCheckbox = document.getElementById('export-exclude-status-update');
            if (excludeCheckbox && excludeCheckbox.checked) {
                params.exclude_method = 'status_update_req';
            }
        } else if (mode === 'range') {
            params.from_ts = document.getElementById('export-from').value;
            params.to_ts = document.getElementById('export-to').value;
        }

        await api.export(mode, params);
        document.getElementById('export-modal').style.display = 'none';
    };

    // Clear All
    document.getElementById('clear-all-btn').onclick = () => {
        document.getElementById('clear-all-modal').style.display = 'flex';
    };

    document.getElementById('close-clear-modal').onclick = () => {
        document.getElementById('clear-all-modal').style.display = 'none';
    };

    document.getElementById('clear-cancel').onclick = () => {
        document.getElementById('clear-all-modal').style.display = 'none';
    };

    document.getElementById('clear-confirm').onclick = async () => {
        await api.deleteAll();
        document.getElementById('clear-all-modal').style.display = 'none';
        state.currentPage = 1;
        state.selectedExchange = null;
        state.sessionAnnotations = {};
        document.getElementById('detail-panel').style.display = 'none';
        await renderExchangeList();
        await loadSessionAnnotations();
    };

    // Session Annotation modal
    document.getElementById('close-annotation-modal').onclick = () => {
        document.getElementById('session-annotation-modal').style.display = 'none';
    };

    document.getElementById('annotation-save').onclick = async () => {
        const modal = document.getElementById('session-annotation-modal');
        const sessionId = modal.dataset.sessionId;
        const name = document.getElementById('annotation-name').value.trim();
        const notes = document.getElementById('annotation-notes').value.trim();

        await api.updateSessionAnnotation(sessionId, name || null, notes || null);
        modal.style.display = 'none';

        await loadSessionAnnotations();
        await renderExchangeList();

        if (state.selectedExchange && state.selectedExchange.session_id === sessionId) {
            await showDetail(state.selectedExchange.exchange_id);
        }
    };

    document.getElementById('annotation-delete').onclick = async () => {
        const modal = document.getElementById('session-annotation-modal');
        const sessionId = modal.dataset.sessionId;

        await api.deleteSessionAnnotation(sessionId);
        modal.style.display = 'none';

        await loadSessionAnnotations();
        await renderExchangeList();

        if (state.selectedExchange && state.selectedExchange.session_id === sessionId) {
            await showDetail(state.selectedExchange.exchange_id);
        }
    };

    document.getElementById('close-delete-session-modal').onclick = () => {
        document.getElementById('delete-session-modal').style.display = 'none';
    };

    document.getElementById('delete-session-cancel').onclick = () => {
        document.getElementById('delete-session-modal').style.display = 'none';
    };

    document.getElementById('delete-session-confirm').onclick = async () => {
        const modal = document.getElementById('delete-session-modal');
        const sessionId = modal.dataset.sessionId;
        await api.deleteSession(sessionId);
        modal.style.display = 'none';

        // If viewing an exchange from this session, close the detail panel
        if (state.selectedExchange && state.selectedExchange.session_id === sessionId) {
            state.selectedExchange = null;
            document.getElementById('detail-panel').style.display = 'none';
        }

        state.currentPage = 1;
        await renderExchangeList();
        await loadFilterOptions();
    };

    // Delete single exchange modal
    document.getElementById('close-delete-exchange-modal').onclick = () => {
        document.getElementById('delete-exchange-modal').style.display = 'none';
    };

    document.getElementById('delete-exchange-cancel').onclick = () => {
        document.getElementById('delete-exchange-modal').style.display = 'none';
    };

    document.getElementById('delete-exchange-confirm').onclick = async () => {
        const modal = document.getElementById('delete-exchange-modal');
        const exchangeId = modal.dataset.exchangeId;
        await api.deleteExchange(exchangeId);
        modal.style.display = 'none';

        if (state.selectedExchange && state.selectedExchange.exchange_id === exchangeId) {
            state.selectedExchange = null;
            document.getElementById('detail-panel').style.display = 'none';
        }

        await renderExchangeList();
    };
}

function showDeleteSessionModal(sessionId) {
    document.getElementById('delete-session-id').textContent = sessionId;
    const deleteModal = document.getElementById('delete-session-modal');
    deleteModal.dataset.sessionId = sessionId;
    deleteModal.style.display = 'flex';
}

function showDeleteExchangeModal(exchangeId) {
    document.getElementById('delete-exchange-id').textContent = exchangeId.substring(0, 8) + '...';
    const modal = document.getElementById('delete-exchange-modal');
    modal.dataset.exchangeId = exchangeId;
    modal.style.display = 'flex';
}

function showSessionAnnotationModal(sessionId) {
    const modal = document.getElementById('session-annotation-modal');
    const ann = state.sessionAnnotations[sessionId];

    document.getElementById('annotation-session-id').textContent = sessionId;
    document.getElementById('annotation-name').value = (ann && ann.session_name) || '';
    document.getElementById('annotation-notes').value = (ann && ann.session_notes) || '';

    modal.dataset.sessionId = sessionId;
    modal.style.display = 'flex';
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
                    ${sessions.sessions.map(s => `<option value="${s.session_id}">${s.session_name ? `${s.session_name} (${s.session_id})` : s.session_id} [${s.count}]</option>`).join('')}
                </select>
            </div>
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" id="export-exclude-status-update">
                    Exclude status_update_req exchanges
                </label>
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
    await loadFilterOptions();
    await renderExchangeList();
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
    // Keep first option, clear rest
    while (methodSelect.options.length > 1) methodSelect.remove(1);
    methods.methods.forEach(m => {
        const option = document.createElement('option');
        option.value = m.app_method;
        option.textContent = `${m.app_method} (${m.count})`;
        methodSelect.appendChild(option);
    });

    await loadSessionAnnotations();
}

async function loadSessionAnnotations() {
    const sessionsData = await api.getSessions();
    state.sessionAnnotations = {};
    const sessionSelect = document.getElementById('session-id');

    // Keep first option ("All Sessions"), clear rest
    while (sessionSelect.options.length > 1) sessionSelect.remove(1);

    sessionsData.sessions.forEach(s => {
        state.sessionAnnotations[s.session_id] = {
            session_name: s.session_name,
            session_notes: s.session_notes
        };

        const option = document.createElement('option');
        option.value = s.session_id;
        option.textContent = s.session_name
            ? `${s.session_name} (${s.session_id}) [${s.count}]`
            : `${s.session_id} (${s.count})`;
        sessionSelect.appendChild(option);
    });
}

// Start application
document.addEventListener('DOMContentLoaded', init);
