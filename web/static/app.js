/* Reeleezee Exporter - Single Page Application */

const app = document.getElementById('app');
let currentEventSource = null;

// --- API helpers ---
async function api(method, path, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch('/api' + path, opts);
    if (res.status === 401) { navigate('/login'); throw new Error('Not authenticated'); }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Request failed');
    return data;
}

// --- Router ---
function navigate(hash) {
    window.location.hash = hash;
}

function getRoute() {
    const hash = window.location.hash.slice(1) || '/login';
    const parts = hash.split('/').filter(Boolean);
    return { path: hash, parts };
}

window.addEventListener('hashchange', route);

function route() {
    if (currentEventSource) { currentEventSource.close(); currentEventSource = null; }
    const { path, parts } = getRoute();

    if (path === '/login' || path === '/') renderLogin();
    else if (path === '/dashboard') renderDashboard();
    else if (parts[0] === 'job' && parts.length === 2) renderJobDetail(parts[1]);
    else if (parts[0] === 'job' && parts[2] === 'data' && parts[3]) renderDataBrowser(parts[1], parts[3]);
    else if (parts[0] === 'job' && parts[2] === 'files') renderFileBrowser(parts[1]);
    else renderLogin();
}

// --- Pages ---

function renderLogin() {
    app.innerHTML = `
        <div class="login-container">
            <div class="card">
                <h2>Reeleezee Exporter</h2>
                <p class="text-light mb-16">Connect to your Reeleezee account to export data</p>
                <div id="login-error" class="error-msg hidden"></div>
                <form id="login-form">
                    <div class="form-group">
                        <label>Username</label>
                        <input type="text" id="username" required autocomplete="username">
                    </div>
                    <div class="form-group">
                        <label>Password</label>
                        <input type="password" id="password" required autocomplete="current-password">
                    </div>
                    <button type="submit" class="btn btn-primary" style="width:100%">
                        Connect
                    </button>
                </form>
            </div>
        </div>`;

    document.getElementById('login-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = e.target.querySelector('button');
        const errEl = document.getElementById('login-error');
        btn.disabled = true;
        btn.textContent = 'Connecting...';
        errEl.classList.add('hidden');

        try {
            await api('POST', '/login', {
                username: document.getElementById('username').value,
                password: document.getElementById('password').value,
            });
            navigate('/dashboard');
        } catch (err) {
            errEl.textContent = err.message;
            errEl.classList.remove('hidden');
            btn.disabled = false;
            btn.textContent = 'Connect';
        }
    });
}

async function renderDashboard() {
    app.innerHTML = '<div class="container"><p>Loading...</p></div>';

    let me;
    try { me = await api('GET', '/me'); } catch { return; }

    const admins = me.administrations || [];
    let jobs = [];
    try { jobs = await api('GET', '/jobs'); } catch {}

    // Endpoint options for export config
    const dataEndpoints = [
        { key: 'salesinvoices', label: 'Sales Invoices' },
        { key: 'purchaseinvoices', label: 'Purchase Invoices' },
        { key: 'customers', label: 'Customers' },
        { key: 'vendors', label: 'Vendors' },
        { key: 'products', label: 'Products' },
        { key: 'bankimports', label: 'Bank Imports' },
        { key: 'bankstatements', label: 'Bank Statements' },
        { key: 'offerings', label: 'Offerings' },
        { key: 'relations', label: 'Relations' },
        { key: 'addresses', label: 'Addresses' },
        { key: 'accounts', label: 'Accounts' },
        { key: 'documents', label: 'Documents' },
        { key: 'purchaseinvoicescans', label: 'Purchase Invoice Scans (metadata)' },
    ];

    const fileEndpoints = [
        { key: 'purchase_scans', label: 'Purchase Invoice Scan Files' },
        { key: 'sales_pdfs', label: 'Sales Invoice PDFs' },
        { key: 'offering_pdfs', label: 'Offering PDFs' },
    ];

    const adminId = admins[0]?.id || admins[0]?.Id || '';
    const adminName = admins[0]?.Name || admins[0]?.name || 'Unknown';

    // Phase 1: Quick year list from CreateDate
    let quickYears = [];
    try {
        const yr = await api('GET', `/administrations/${adminId}/years`);
        quickYears = yr.years || [];
    } catch {}

    app.innerHTML = `
        <div class="header">
            <h1>Reeleezee Exporter</h1>
            <div class="nav">
                <span>${adminName}</span>
                <button onclick="logout()">Logout</button>
            </div>
        </div>
        <div class="container">
            <div class="card">
                <h2>New Export</h2>
                <div class="form-group">
                    <label>Job Type</label>
                    <select id="job-type" style="padding:8px;border:1px solid var(--border);border-radius:var(--radius);font-size:14px;">
                        <option value="data">Data only (JSON)</option>
                        <option value="files">Files only (PDFs, scans)</option>
                        <option value="both" selected>Both data and files</option>
                    </select>
                </div>

                <h3>Years</h3>
                <div id="years-section" class="mb-16">
                    <div class="flex gap-8 mb-16" style="flex-wrap:wrap" id="year-buttons">
                        ${quickYears.map(y => `
                            <label class="year-btn" style="display:inline-flex;align-items:center;gap:4px;padding:6px 14px;border:1px solid var(--border);border-radius:var(--radius);cursor:pointer;font-size:14px;transition:all 0.2s">
                                <input type="checkbox" value="${y.year}" checked class="year-cb">
                                <span>${y.year}</span>
                                <span class="year-count text-light" style="font-size:11px" data-year="${y.year}"></span>
                            </label>
                        `).join('')}
                    </div>
                    <div class="flex gap-8">
                        <button class="btn btn-sm btn-outline" onclick="toggleYears(true)">Select All Years</button>
                        <button class="btn btn-sm btn-outline" onclick="toggleYears(false)">Deselect All</button>
                        <span id="years-loading" class="text-light" style="font-size:12px;align-self:center">Checking data per year...</span>
                    </div>
                </div>

                <h3>Data Endpoints</h3>
                <div class="checkbox-grid mb-16" id="data-endpoints">
                    ${dataEndpoints.map(ep => `
                        <label><input type="checkbox" value="${ep.key}" checked><span>${ep.label}</span></label>
                    `).join('')}
                </div>

                <h3>File Downloads</h3>
                <div class="checkbox-grid mb-16" id="file-endpoints">
                    ${fileEndpoints.map(ep => `
                        <label><input type="checkbox" value="${ep.key}" checked><span>${ep.label}</span></label>
                    `).join('')}
                </div>

                <div class="flex gap-8">
                    <button class="btn btn-primary" onclick="startExport('${adminId}')">Start Export</button>
                    <button class="btn btn-outline" onclick="selectAll(true)">Select All</button>
                    <button class="btn btn-outline" onclick="selectAll(false)">Deselect All</button>
                </div>
            </div>

            <div class="card">
                <h2>Export History</h2>
                ${jobs.length === 0 ? '<p class="text-light">No exports yet</p>' : `
                <div class="table-wrap">
                    <table>
                        <thead><tr>
                            <th>Date</th><th>Administration</th><th>Type</th>
                            <th>Status</th><th>Progress</th><th>Actions</th>
                        </tr></thead>
                        <tbody>
                            ${jobs.map(j => {
                                const completed = (j.completed_steps || []).length;
                                const total = (j.endpoints || []).length;
                                const pct = total > 0 ? Math.round(completed / total * 100) : 0;
                                return `<tr>
                                    <td>${new Date(j.created_at).toLocaleString()}</td>
                                    <td>${j.admin_name}</td>
                                    <td>${j.job_type}</td>
                                    <td><span class="badge badge-${j.status}">${j.status}</span></td>
                                    <td>
                                        <div class="progress-bar">
                                            <div class="fill ${j.status === 'completed' ? 'complete' : ''}" style="width:${pct}%"></div>
                                        </div>
                                        <span class="text-light" style="font-size:12px">${completed}/${total} steps</span>
                                    </td>
                                    <td>
                                        <button class="btn btn-sm btn-outline" onclick="navigate('/job/${j.id}')">View</button>
                                        ${j.status === 'failed' ? `<button class="btn btn-sm btn-outline" onclick="resumeJob('${j.id}')">Resume</button>` : ''}
                                    </td>
                                </tr>`;
                            }).join('')}
                        </tbody>
                    </table>
                </div>`}
            </div>
        </div>`;

    // Phase 2: Fetch detailed year counts in background
    if (adminId) {
        loadDetailedYears(adminId);
    }
}

function toggleYears(checked) {
    document.querySelectorAll('.year-cb').forEach(cb => cb.checked = checked);
}

async function loadDetailedYears(adminId) {
    try {
        const data = await api('GET', `/administrations/${adminId}/years/detailed`);
        const loadingEl = document.getElementById('years-loading');
        if (loadingEl) loadingEl.textContent = '';

        for (const y of (data.years || [])) {
            const countEl = document.querySelector(`.year-count[data-year="${y.year}"]`);
            const label = countEl?.closest('label');
            if (!countEl || !label) continue;

            if (y.has_data) {
                const parts = [];
                if (y.counts?.sales_invoices) parts.push('SI');
                if (y.counts?.purchase_invoices) parts.push('PI');
                countEl.textContent = parts.length ? `(${parts.join(', ')})` : '(data)';
                label.style.borderColor = 'var(--success)';
                label.style.background = '#f0faf4';
            } else {
                countEl.textContent = '(empty)';
                label.style.borderColor = '#eee';
                label.style.background = '#fafafa';
                label.style.opacity = '0.6';
                // Uncheck years with no data
                const cb = label.querySelector('.year-cb');
                if (cb) cb.checked = false;
            }
        }
    } catch (e) {
        const loadingEl = document.getElementById('years-loading');
        if (loadingEl) loadingEl.textContent = 'Could not load detailed year info';
    }
}

async function renderJobDetail(jobId) {
    app.innerHTML = '<div class="container"><p>Loading...</p></div>';

    let job;
    try { job = await api('GET', '/jobs/' + jobId); } catch { return; }

    const steps = job.steps || [];
    const completed = (job.completed_steps || []).length;
    const total = (job.endpoints || []).length;
    const pct = total > 0 ? Math.round(completed / total * 100) : 0;

    app.innerHTML = `
        <div class="header">
            <h1>Reeleezee Exporter</h1>
            <div class="nav">
                <a href="#/dashboard">Dashboard</a>
                <button onclick="logout()">Logout</button>
            </div>
        </div>
        <div class="container">
            <div class="card">
                <div class="flex flex-between" style="align-items:center">
                    <h2>Export: ${job.admin_name}</h2>
                    <span class="badge badge-${job.status}" id="job-status">${job.status}</span>
                </div>
                <p class="text-light">Type: ${job.job_type} | Created: ${new Date(job.created_at).toLocaleString()}</p>

                <div class="progress-bar mt-8">
                    <div class="fill ${job.status === 'completed' ? 'complete' : ''}" id="progress-fill" style="width:${pct}%"></div>
                </div>
                <p class="text-light mt-8" id="progress-text">${completed} of ${total} steps | ${job.items_exported} items exported</p>

                ${job.error_message ? `<div class="error-msg mt-16">${job.error_message}</div>` : ''}

                <div class="flex gap-8 mt-16">
                    ${job.status === 'running' ? `<button class="btn btn-sm btn-danger" onclick="cancelJob('${jobId}')">Cancel</button>` : ''}
                    ${job.status === 'failed' ? `<button class="btn btn-sm btn-primary" onclick="resumeJob('${jobId}')">Resume</button>` : ''}
                    ${['completed', 'failed'].includes(job.status) ? `<button class="btn btn-sm btn-success" onclick="downloadZip('${jobId}')">Download ZIP</button>` : ''}
                    <button class="btn btn-sm btn-outline" onclick="navigate('/job/${jobId}/files')">Browse Files</button>
                </div>
            </div>

            <div class="card">
                <h2>Steps</h2>
                <ul class="steps-list" id="steps-list">
                    ${steps.map(s => stepHtml(s)).join('')}
                </ul>
            </div>

            <div class="card" id="data-preview">
                <h2>Data Preview</h2>
                <div id="data-cards" class="checkbox-grid">
                    ${steps.filter(s => s.status === 'completed' && !['purchase_scans','sales_pdfs','offering_pdfs','export_files'].includes(s.step_name)).map(s => `
                        <div class="file-card" onclick="navigate('/job/${jobId}/data/${s.step_name.replace('invoices_detail','invoices')}')">
                            <div class="icon">📄</div>
                            <div class="name">${s.step_name}</div>
                            <div class="text-light" style="font-size:12px">${s.items_count || 0} items</div>
                        </div>
                    `).join('') || '<p class="text-light">No data available yet</p>'}
                </div>
            </div>
        </div>`;

    // Connect SSE for live updates
    if (['pending', 'running'].includes(job.status)) {
        connectSSE(jobId);
    }
}

function stepHtml(s) {
    const icons = { pending: '○', running: '◉', completed: '✓', failed: '✗' };
    return `<li class="step-${s.status}">
        <div class="step-icon">${icons[s.status] || '○'}</div>
        <span class="step-name">${s.step_name}</span>
        <span class="step-count">${s.items_count || ''}${s.items_total ? '/' + s.items_total : ''}</span>
    </li>`;
}

function connectSSE(jobId) {
    if (currentEventSource) currentEventSource.close();
    currentEventSource = new EventSource('/api/jobs/' + jobId + '/events');

    currentEventSource.addEventListener('progress', (e) => {
        try {
            const data = JSON.parse(e.data);
            // Refresh page on terminal status
            if (['completed', 'failed', 'cancelled'].includes(data.status)) {
                currentEventSource.close();
                currentEventSource = null;
                renderJobDetail(jobId);
                return;
            }
            // Update progress text
            const txt = document.getElementById('progress-text');
            if (txt && data.items_exported !== undefined) {
                txt.textContent = `${data.items_exported} items exported`;
            }
            if (data.event === 'step_progress') {
                const txt2 = document.getElementById('progress-text');
                if (txt2) txt2.textContent = `${data.step}: ${data.processed}/${data.total}`;
            }
        } catch {}
    });

    currentEventSource.addEventListener('state', (e) => {
        // Initial state - already rendered
    });

    currentEventSource.onerror = () => {
        // Reconnect after delay
        setTimeout(() => {
            if (getRoute().parts[0] === 'job' && getRoute().parts[1] === jobId) {
                connectSSE(jobId);
            }
        }, 3000);
    };
}

async function renderDataBrowser(jobId, dataType) {
    app.innerHTML = '<div class="container"><p>Loading...</p></div>';

    const page = parseInt(new URLSearchParams(window.location.hash.split('?')[1]).get('page')) || 1;
    let result;
    try { result = await api('GET', `/jobs/${jobId}/data/${dataType}?page=${page}&per_page=50`); } catch (e) {
        app.innerHTML = `<div class="container"><div class="error-msg">${e.message}</div></div>`;
        return;
    }

    const items = result.data || [];
    const columns = items.length > 0 ? Object.keys(items[0]).slice(0, 12) : [];

    app.innerHTML = `
        <div class="header">
            <h1>Reeleezee Exporter</h1>
            <div class="nav">
                <a href="#/job/${jobId}">Back to Job</a>
                <a href="#/dashboard">Dashboard</a>
            </div>
        </div>
        <div class="container">
            <div class="card">
                <div class="flex flex-between" style="align-items:center">
                    <h2>${dataType} (${result.total} items)</h2>
                    <span class="text-light">Page ${result.page} of ${result.total_pages}</span>
                </div>
                <div class="table-wrap mt-16">
                    <table>
                        <thead><tr>${columns.map(c => `<th>${c}</th>`).join('')}</tr></thead>
                        <tbody>
                            ${items.map(item => `<tr>${columns.map(c => {
                                let raw = item[c];
                                if (raw === null || raw === undefined) raw = '';
                                else if (typeof raw === 'object') raw = JSON.stringify(raw);
                                else raw = String(raw);
                                const display = raw.length > 60 ? raw.substring(0, 60) + '...' : raw;
                                const escaped = raw.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
                                return `<td title="${escaped}">${display}</td>`;
                            }).join('')}</tr>`).join('')}
                        </tbody>
                    </table>
                </div>
                <div class="pagination mt-16">
                    ${result.page > 1 ? `<button class="btn btn-sm btn-outline" onclick="navigate('/job/${jobId}/data/${dataType}?page=${result.page-1}')">Prev</button>` : ''}
                    <span class="text-light">Page ${result.page} of ${result.total_pages}</span>
                    ${result.page < result.total_pages ? `<button class="btn btn-sm btn-outline" onclick="navigate('/job/${jobId}/data/${dataType}?page=${result.page+1}')">Next</button>` : ''}
                </div>
            </div>
        </div>`;
}

async function renderFileBrowser(jobId) {
    app.innerHTML = '<div class="container"><p>Loading...</p></div>';

    let result;
    try { result = await api('GET', `/jobs/${jobId}/files`); } catch (e) {
        app.innerHTML = `<div class="container"><div class="error-msg">${e.message}</div></div>`;
        return;
    }

    const files = result.files || [];
    const iconMap = { pdf: '📄', jpg: '🖼', jpeg: '🖼', png: '🖼', bin: '📎' };

    app.innerHTML = `
        <div class="header">
            <h1>Reeleezee Exporter</h1>
            <div class="nav">
                <a href="#/job/${jobId}">Back to Job</a>
                <a href="#/dashboard">Dashboard</a>
            </div>
        </div>
        <div class="container">
            <div class="card">
                <h2>Files (${files.length})</h2>
                ${files.length === 0 ? '<p class="text-light">No files downloaded yet</p>' : `
                <div class="file-grid mt-16">
                    ${files.map(f => `
                        <a href="/api/jobs/${jobId}/files/${f.path}" target="_blank" class="file-card" style="text-decoration:none;color:inherit">
                            <div class="icon">${iconMap[f.type] || '📎'}</div>
                            <div class="name">${f.name}</div>
                            <div class="text-light" style="font-size:11px">${f.size_kb} KB</div>
                        </a>
                    `).join('')}
                </div>`}
            </div>
        </div>`;
}

// --- Actions ---

async function startExport(adminId) {
    const jobType = document.getElementById('job-type').value;
    const dataChecked = [...document.querySelectorAll('#data-endpoints input:checked')].map(i => i.value);
    const fileChecked = [...document.querySelectorAll('#file-endpoints input:checked')].map(i => i.value);
    const yearsChecked = [...document.querySelectorAll('.year-cb:checked')].map(i => parseInt(i.value));

    let endpoints = [];
    if (jobType === 'data' || jobType === 'both') endpoints.push(...dataChecked);
    if (jobType === 'files' || jobType === 'both') endpoints.push(...fileChecked);

    if (yearsChecked.length === 0) {
        alert('Please select at least one year');
        return;
    }

    try {
        const result = await api('POST', '/jobs', {
            admin_id: adminId,
            job_type: jobType,
            endpoints,
            years: yearsChecked,
        });
        navigate('/job/' + result.id);
    } catch (e) {
        alert('Failed to start export: ' + e.message);
    }
}

function selectAll(checked) {
    document.querySelectorAll('#data-endpoints input, #file-endpoints input').forEach(i => i.checked = checked);
}

async function cancelJob(jobId) {
    if (!confirm('Cancel this export?')) return;
    try { await api('DELETE', '/jobs/' + jobId); renderJobDetail(jobId); } catch (e) { alert(e.message); }
}

async function resumeJob(jobId) {
    try { await api('POST', '/jobs/' + jobId + '/resume'); renderJobDetail(jobId); } catch (e) { alert(e.message); }
}

async function downloadZip(jobId) {
    try {
        const result = await api('POST', '/jobs/' + jobId + '/download');
        if (result.zip_ready) {
            window.open('/api/jobs/' + jobId + '/download', '_blank');
        } else {
            alert('ZIP generation started. Try again in a moment.');
        }
    } catch (e) { alert(e.message); }
}

async function logout() {
    try { await api('POST', '/logout'); } catch {}
    navigate('/login');
}

// --- Init ---
(async function init() {
    // Check if already authenticated
    try {
        await api('GET', '/me');
        if (getRoute().path === '/login' || getRoute().path === '/') {
            navigate('/dashboard');
            return;
        }
    } catch {}
    route();
})();
