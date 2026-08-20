const API_BASE = 'http://127.0.0.1:5000';
let currentToken = localStorage.getItem('token') || null;
let currentUser = JSON.parse(localStorage.getItem('user') || 'null');
let allResults = null;

function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon();
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon();
}

function updateThemeIcon() {
    const theme = document.documentElement.getAttribute('data-theme') || 'dark';
    const icon = document.getElementById('theme-icon');
    if (icon) {
        icon.innerHTML = theme === 'dark' 
            ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
            : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    }
}

function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function showLoading(text = 'Searching multiple sources...') {
    const overlay = document.createElement('div');
    overlay.id = 'loading-overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);backdrop-filter:blur(8px);z-index:9999;display:flex;align-items:center;justify-content:center;';
    const card = document.createElement('div');
    card.style.cssText = 'background:var(--bg-primary);padding:40px 50px;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,0.4);border:1px solid var(--border);text-align:center;min-width:300px;max-width:90%;';
    card.innerHTML = `<div class="spinner"></div><p style="margin-top:20px;color:var(--text-primary);font-size:16px;font-weight:500;">${text}</p><p style="margin-top:8px;color:var(--text-muted);font-size:13px;">Google, YouTube, Stack Overflow, GitHub, Wikipedia, Dev.to, Reddit, Gemini AI</p>`;
    overlay.appendChild(card);
    document.body.appendChild(overlay);
}

function hideLoading() {
    const loading = document.getElementById('loading-overlay');
    if (loading) loading.remove();
}

function redirect(page) { window.location.href = page; }
function isLoggedIn() { return currentToken !== null; }
function getHeaders() { return { 'Content-Type': 'application/json', 'Authorization': `Bearer ${currentToken}` }; }
function formatDate(d) { if (!d) return ''; const dt = new Date(d); return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); }
function escapeHtml(t) { if (!t) return ''; return t.replace(/'/g, "\\'").replace(/"/g, '\\"'); }

async function register() {
    const name = document.getElementById('register-name').value;
    const email = document.getElementById('register-email').value;
    const password = document.getElementById('register-password').value;
    if (!name || !email || !password) { showToast('Please fill all fields', 'error'); return; }
    try {
        const r = await fetch(`${API_BASE}/api/auth/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, email, password }) });
        const d = await r.json();
        if (d.success) { showToast('Registration successful! Please login.'); setTimeout(() => redirect('login.html'), 1000); }
        else showToast(d.error || 'Registration failed', 'error');
    } catch { showToast('Server error', 'error'); }
}

async function login() {
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    if (!email || !password) { showToast('Please fill all fields', 'error'); return; }
    try {
        const r = await fetch(`${API_BASE}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
        const d = await r.json();
        if (d.success) {
            currentToken = d.token; currentUser = d.user;
            localStorage.setItem('token', d.token); localStorage.setItem('user', JSON.stringify(d.user));
            showToast('Welcome back, ' + d.user.name + '!');
            setTimeout(() => redirect('dashboard.html'), 800);
        } else showToast(d.error || 'Login failed', 'error');
    } catch { showToast('Server error', 'error'); }
}

function logout() {
    localStorage.removeItem('token'); localStorage.removeItem('user');
    currentToken = null; currentUser = null;
    showToast('Logged out');
    setTimeout(() => redirect('index.html'), 500);
}

async function performSearch() {
    const query = document.getElementById('search-input').value;
    if (!query.trim()) { showToast('Please enter a question', 'error'); return; }
    showLoading();
    try {
        const headers = { 'Content-Type': 'application/json' };
        if (currentToken) headers['Authorization'] = `Bearer ${currentToken}`;
        const r = await fetch(`${API_BASE}/api/search`, { method: 'POST', headers, body: JSON.stringify({ query }) });
        const d = await r.json();
        if (d.success) { localStorage.setItem('searchResults', JSON.stringify(d)); hideLoading(); redirect('results.html'); }
        else { hideLoading(); showToast(d.error || 'Search failed', 'error'); }
    } catch { hideLoading(); showToast('Server error', 'error'); }
}

function quickSearch(q) { document.getElementById('search-input').value = q; performSearch(); }

function displayResults() {
    const rd = localStorage.getItem('searchResults');
    if (!rd) { redirect('dashboard.html'); return; }
    const data = JSON.parse(rd);
    allResults = data;
    document.getElementById('query-display').textContent = data.query;
    document.getElementById('topic-display').textContent = `Topic: ${data.topic}`;
    document.getElementById('sources-displayed').textContent = data.sources_searched.join(', ');
    renderAnalysis(data.comparison, data);
    renderResults(data.answers);
    loadRelatedQuestions(data.query);
}

function renderAnalysis(comparison, data) {
    const sc = document.getElementById('search-analysis-content');
    if (sc && data) {
        sc.innerHTML = `<p style="font-size:14px;margin-bottom:12px;"><strong>Sources searched:</strong><br><span style="color:var(--accent);font-weight:600;font-size:28px;">${data.sources_searched.length}</span></p><p style="font-size:14px;margin-bottom:8px;"><strong>Sources:</strong></p><div style="display:flex;flex-wrap:wrap;gap:6px;">${data.sources_searched.map(s => `<span class="card-source">${s}</span>`).join('')}</div><div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border);"><p style="font-size:13px;color:var(--text-secondary);">Topic: <strong>${data.topic}</strong></p><p style="font-size:13px;color:var(--text-secondary);">Query: <strong>${data.query}</strong></p></div>`;
    }
    const cc = document.getElementById('consensus-content');
    if (cc && comparison) {
        const conf = Math.round(comparison.avg_confidence * 100);
        cc.innerHTML = `<div class="confidence-bar" style="margin-bottom:8px;"><div class="confidence-fill ${conf > 70 ? 'confidence-high' : conf > 40 ? 'confidence-medium' : 'confidence-low'}" style="width:${conf}%;"></div></div><p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">Overall Confidence: ${conf}%</p>${comparison.consensus && comparison.consensus.length > 0 ? `<div style="margin-bottom:12px;padding:10px;background:var(--success-bg);border-radius:6px;"><p style="font-size:12px;color:var(--success);font-weight:600;">AGREEING (${comparison.consensus.length})</p><p style="font-size:13px;margin-top:4px;">${comparison.consensus.join(', ')}</p></div>` : ''}${comparison.minority && comparison.minority.length > 0 ? `<div style="margin-bottom:12px;padding:10px;background:var(--warning-bg);border-radius:6px;"><p style="font-size:12px;color:var(--warning);font-weight:600;">DISAGREEING (${comparison.minority.length})</p><p style="font-size:13px;margin-top:4px;">${comparison.minority.join(', ')}</p></div>` : '<p style="font-size:13px;color:var(--text-muted);margin-bottom:12px;">No disagreement.</p>'}<p style="font-size:13px;font-weight:500;">${comparison.consensus_recommendation || ''}</p>`;
    }
}

function renderResults(answers) {
    const c = document.getElementById('results-container');
    if (!c) return;
    if (!answers || answers.length === 0) { c.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:40px;">No results found.</p>'; return; }
    c.innerHTML = `<div class="grid-2">` + answers.map((a, i) => {
        const conf = Math.round((a.confidence || 0.5) * 100);
        const cls = conf > 70 ? 'confidence-high' : conf > 40 ? 'confidence-medium' : 'confidence-low';
        const isAI = a.source === 'Gemini AI';
        const fullBody = a.body || '';
        const shortBody = fullBody.substring(0, 150);
        const isLong = fullBody.length > 150;
        const answerId = `ans-${i}`;
        return `<div class="card" style="${isAI ? 'grid-column:1/-1;' : ''}">
            <div class="card-header"><span class="card-title">${a.title || 'Result ' + (i+1)}</span><span class="card-source">${a.source}</span></div>
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;"><span style="font-size:12px;color:var(--text-muted);">Trust: ${a.trust_score || 5}/10</span>${a.date ? `<span style="font-size:12px;color:var(--text-muted);">${a.date}</span>` : ''}</div>
            <div class="confidence-bar"><div class="confidence-fill ${cls}" style="width:${conf}%;"></div></div>
            <div style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">Confidence: ${conf}%</div>
            <div class="card-body" id="${answerId}-body">
                <span id="${answerId}-short">${shortBody}${isLong ? '...' : ''}</span>
                <span id="${answerId}-full" style="display:none;white-space:pre-wrap;">${fullBody}</span>
            </div>
            ${isLong ? `<button onclick="toggleAnswer('${answerId}')" style="font-size:12px;padding:6px 14px;background:transparent;border:1px solid var(--border);color:var(--accent);border-radius:4px;cursor:pointer;margin-bottom:12px;"><span id="${answerId}-btn">Read More</span></button>` : ''}
            <div class="card-actions">${a.url ? `<button onclick="window.open('${a.url}','_blank')">View Source</button>` : ''}${a.url ? `<button onclick="copyAnswer('${a.url}')">Copy Link</button>` : ''}${isAI ? `<button onclick="copyAnswer('${escapeHtml(fullBody)}')">Copy Answer</button>` : ''}<button onclick="saveAnswer('${allResults.query_id}','${a.source}','${escapeHtml(fullBody)}','${a.url}',${a.confidence || 0.5})">Save</button></div>
        </div>`;
    }).join('') + `</div>`;
}

function toggleAnswer(id) {
    const shortEl = document.getElementById(`${id}-short`);
    const fullEl = document.getElementById(`${id}-full`);
    const btn = document.getElementById(`${id}-btn`);
    if (shortEl && fullEl && btn) {
        if (fullEl.style.display === 'none') {
            shortEl.style.display = 'none';
            fullEl.style.display = 'inline';
            btn.textContent = 'Show Less';
        } else {
            shortEl.style.display = 'inline';
            fullEl.style.display = 'none';
            btn.textContent = 'Read More';
        }
    }
}

function filterResults(source) {
    if (!allResults || !allResults.answers) return;
    if (source === 'all') { renderResults(allResults.answers); return; }
    const filtered = allResults.answers.filter(a => a.source === source);
    if (filtered.length > 0) renderResults(filtered);
    else { const c = document.getElementById('results-container'); if (c) c.innerHTML = `<p style="color:var(--text-secondary);text-align:center;padding:40px;">No results from ${source}.</p>`; }
}

function copyAnswer(text) { if (!text) return; navigator.clipboard.writeText(text).then(() => showToast('Copied!')); }

function copyAllResults() {
    if (!allResults || !allResults.answers) return;
    let t = `TechHub Results\nQuery: ${allResults.query}\nTopic: ${allResults.topic}\n\n`;
    allResults.answers.forEach((a, i) => { t += `${i+1}. [${a.source}] ${a.title}\n${a.body}\n${a.url ? 'Source: ' + a.url + '\n' : ''}Confidence: ${Math.round(a.confidence*100)}%\n\n`; });
    navigator.clipboard.writeText(t).then(() => showToast('All results copied!'));
}

async function loadRelatedQuestions(query) {
    const c = document.getElementById('related-container');
    if (!c) return;
    try {
        const r = await fetch(`${API_BASE}/api/related`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query }) });
        const d = await r.json();
        if (d.success && d.questions && d.questions.length > 0) {
            c.innerHTML = `<h3 style="margin-bottom:16px;font-size:18px;">Related Questions</h3><div class="suggestions" style="justify-content:flex-start;">${d.questions.map(q => `<span class="chip" onclick="quickSearch('${q.replace(/'/g, "\\'")}')">${q}</span>`).join('')}</div>`;
        }
    } catch {}
}

async function saveAnswer(queryId, source, answer, url, confidence) {
    if (!isLoggedIn()) { showToast('Please login to save', 'error'); return; }
    try {
        const r = await fetch(`${API_BASE}/api/history/save`, { method: 'POST', headers: getHeaders(), body: JSON.stringify({ query_id: queryId, source, answer, url, confidence }) });
        const d = await r.json();
        if (d.success) showToast('Saved!'); else showToast('Failed to save', 'error');
    } catch { showToast('Server error', 'error'); }
}

async function loadHistory() {
    if (!isLoggedIn()) { redirect('login.html'); return; }
    const c = document.getElementById('history-container');
    if (!c) return;
    try {
        const r = await fetch(`${API_BASE}/api/history`, { headers: getHeaders() });
        const d = await r.json();
        if (d.success && d.history.length > 0) {
            c.innerHTML = d.history.map(h => `<div class="history-item"><div><div class="history-query">${h.query}</div><div class="history-meta">${h.topic || 'N/A'} | ${formatDate(h.created_at)}</div></div></div>`).join('');
        } else c.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:40px;">No history yet.</p>';
    } catch {}
}

async function loadSaved() {
    if (!isLoggedIn()) { redirect('login.html'); return; }
    const c = document.getElementById('saved-container');
    if (!c) return;
    try {
        const r = await fetch(`${API_BASE}/api/saved`, { headers: getHeaders() });
        const d = await r.json();
        if (d.success && d.saved.length > 0) {
            c.innerHTML = `<div class="grid-2">` + d.saved.map(s => `<div class="card"><div class="card-header"><span class="card-title">${s.source}</span><span class="card-source">${formatDate(s.saved_at)}</span></div><div class="card-body">${(s.answer || '').substring(0, 200)}</div>${s.url ? `<a href="${s.url}" target="_blank">View Source</a>` : ''}</div>`).join('') + `</div>`;
        } else c.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:40px;">No saved answers.</p>';
    } catch {}
}

async function loadProfile() {
    if (!isLoggedIn()) { redirect('login.html'); return; }
    const c = document.getElementById('profile-container');
    if (!c) return;
    try {
        const r = await fetch(`${API_BASE}/api/profile`, { headers: getHeaders() });
        const d = await r.json();
        if (d.success) {
            const u = d.user;
            c.innerHTML = `<div class="card" style="max-width:500px;margin:0 auto;"><div class="card-header"><span class="card-title">${u.name}</span><span class="card-source">${u.role || 'User'}</span></div><div class="card-body"><p>Email: ${u.email}</p><p>Member since: ${formatDate(u.created_at)}</p></div></div>`;
        }
    } catch {}
}

document.addEventListener('DOMContentLoaded', function() {
    initTheme();
    const page = window.location.pathname.split('/').pop();
    if (page === 'results.html') displayResults();
    else if (page === 'history.html') loadHistory();
    else if (page === 'saved.html') loadSaved();
    else if (page === 'profile.html') loadProfile();
    const si = document.getElementById('search-input');
    if (si) si.addEventListener('keypress', function(e) { if (e.key === 'Enter') performSearch(); });
});