// ============ CONFIG ============
const API_BASE = 'http://127.0.0.1:5000';
let currentToken = localStorage.getItem('token') || null;
let currentUser = JSON.parse(localStorage.getItem('user') || 'null');
let allResults = null;

// ============ AUTH GUARD ============
const PROTECTED_PAGES = ['dashboard.html', 'results.html', 'history.html', 'saved.html', 'profile.html'];

function requireLogin() {
    const page = window.location.pathname.split('/').pop() || 'index.html';
    if (PROTECTED_PAGES.includes(page)) {
        if (!localStorage.getItem('token')) {
            window.location.href = 'login.html';
            return false;
        }
    }
    return true;
}

// ============ THEME ============
function initTheme() {
    const t = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', t);
    updateThemeIcon();
}
function toggleTheme() {
    const cur = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    updateThemeIcon();
}
function updateThemeIcon() {
    const t = document.documentElement.getAttribute('data-theme') || 'dark';
    const icon = document.getElementById('theme-icon');
    if (icon) {
        icon.innerHTML = t === 'dark'
            ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
            : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    }
}

// ============ UTILS ============
function showToast(msg, type = 'success') {
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
}
function showLoading(text = 'Searching multiple sources...') {
    const o = document.createElement('div');
    o.id = 'loading-overlay';
    o.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);backdrop-filter:blur(8px);z-index:9999;display:flex;align-items:center;justify-content:center;';
    const c = document.createElement('div');
    c.style.cssText = 'background:var(--bg-primary);padding:40px 50px;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,0.4);border:1px solid var(--border);text-align:center;min-width:300px;max-width:90%;';
    c.innerHTML = `<div class="spinner"></div><p style="margin-top:20px;color:var(--text-primary);font-size:16px;font-weight:500;">${escapeHtml(text)}</p><p style="margin-top:8px;color:var(--text-muted);font-size:13px;">This may take 10-20 seconds</p>`;
    o.appendChild(c);
    document.body.appendChild(o);
}
function hideLoading() { const l = document.getElementById('loading-overlay'); if (l) l.remove(); }
function redirect(p) { window.location.href = p; }
function isLoggedIn() { return currentToken !== null; }
function getHeaders() { return { 'Content-Type': 'application/json', 'Authorization': `Bearer ${currentToken}` }; }
function formatDate(d) {
    if (!d) return '';
    const dt = new Date(d);
    if (isNaN(dt.getTime())) return '';
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
function escapeHtml(v) {
    if (v === null || v === undefined) return '';
    return String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function escapeAttr(v) { return escapeHtml(v); }
function safeUrl(u) {
    if (!u) return '';
    const t = String(u).trim();
    if (/^https?:\/\//i.test(t) || t.startsWith('/')) return t;
    return '';
}

// ============ AUTH ============
async function register() {
    const name = document.getElementById('register-name').value.trim();
    const email = document.getElementById('register-email').value.trim();
    const password = document.getElementById('register-password').value;
    if (!name || !email || !password) { showToast('Please fill all fields', 'error'); return; }
    if (password.length < 6) { showToast('Password must be at least 6 characters', 'error'); return; }
    try {
        const r = await fetch(`${API_BASE}/api/auth/register`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, password })
        });
        const d = await r.json();
        if (d.success) { showToast('Registration successful!'); setTimeout(() => redirect('login.html'), 1000); }
        else showToast(d.error || 'Registration failed', 'error');
    } catch { showToast('Server error', 'error'); }
}

async function login() {
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;
    if (!email || !password) { showToast('Please fill all fields', 'error'); return; }
    try {
        const r = await fetch(`${API_BASE}/api/auth/login`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        const d = await r.json();
        if (d.success) {
            currentToken = d.token; currentUser = d.user;
            localStorage.setItem('token', d.token);
            localStorage.setItem('user', JSON.stringify(d.user));
            showToast('Welcome back, ' + d.user.name + '!');
            setTimeout(() => redirect('dashboard.html'), 800);
        } else showToast(d.error || 'Login failed', 'error');
    } catch { showToast('Server error', 'error'); }
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('searchResults');
    currentToken = null; currentUser = null;
    showToast('Logged out');
    setTimeout(() => redirect('index.html'), 500);
}

// ============ SEARCH ============
async function performSearch() {
    if (!localStorage.getItem('token')) {
        showToast('Please login', 'error');
        setTimeout(() => redirect('login.html'), 800);
        return;
    }
    const input = document.getElementById('search-input');
    const query = (input?.value || '').trim();
    if (!query) { showToast('Please enter a question', 'error'); return; }
    showLoading();
    try {
        const r = await fetch(`${API_BASE}/api/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
            body: JSON.stringify({ query })
        });
        const d = await r.json();
        if (d.success) {
            localStorage.setItem('searchResults', JSON.stringify(d));
            hideLoading();
            redirect('results.html');
        } else { hideLoading(); showToast(d.error || 'Search failed', 'error'); }
    } catch (e) { console.error(e); hideLoading(); showToast('Server error', 'error'); }
}

function quickSearch(q) {
    if (!localStorage.getItem('token')) {
        showToast('Please login', 'error');
        setTimeout(() => redirect('login.html'), 800);
        return;
    }
    const input = document.getElementById('search-input');
    if (input) input.value = q;
    performSearch();
}

// ============ DISPLAY RESULTS ============
function displayResults() {
    const rd = localStorage.getItem('searchResults');
    if (!rd) { redirect('dashboard.html'); return; }
    let data;
    try { data = JSON.parse(rd); } catch { localStorage.removeItem('searchResults'); redirect('dashboard.html'); return; }
    if (!data || !data.answers) { redirect('dashboard.html'); return; }
    allResults = data;

    const qd = document.getElementById('query-display');
    const td = document.getElementById('topic-display');
    const sd = document.getElementById('sources-displayed');
    if (qd) qd.textContent = data.query || '';
    if (td) td.textContent = `Topic: ${data.topic || 'N/A'}`;
    if (sd) sd.textContent = (data.sources_searched || []).join(', ');

    renderAnalysis(data.comparison, data);
    renderResults(data.answers);
    loadRelatedQuestions(data.query);
}

// ============ ANALYSIS PANEL ============
function renderAnalysis(comparison, data) {
    const sc = document.getElementById('search-analysis-content');
    if (sc && data) {
        const sources = (data.sources_searched || []).map(
            s => `<span class="card-source">${escapeHtml(s)}</span>`
        ).join('');
        sc.innerHTML = `
            <p style="font-size:14px;margin-bottom:12px;">
                <strong>Sources searched:</strong><br>
                <span style="color:var(--accent);font-weight:600;font-size:28px;">${(data.sources_searched || []).length}</span>
            </p>
            <div style="display:flex;flex-wrap:wrap;gap:6px;">${sources}</div>
            <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border);">
                <p style="font-size:13px;color:var(--text-secondary);">Topic: <strong>${escapeHtml(data.topic)}</strong></p>
                <p style="font-size:13px;color:var(--text-secondary);">Query: <strong>${escapeHtml(data.query)}</strong></p>
            </div>`;
    }

    // Consensus panel: bar + best REAL source (Gemini excluded)
    const cc = document.getElementById('consensus-content');
    if (cc && comparison) {
        const conf = Math.round((comparison.avg_confidence || 0) * 100);
        const cls = conf > 70 ? 'confidence-high' : conf > 40 ? 'confidence-medium' : 'confidence-low';

        let bestSource = 'N/A';
        let bestConf = -1;
        (allResults?.answers || []).forEach(a => {
            if (a.source === 'Gemini') return;
            const c = a.confidence || 0;
            if (c > bestConf) { bestConf = c; bestSource = a.source; }
        });

        cc.innerHTML = `
            <p style="font-size:13px;color:var(--text-muted);margin-bottom:8px;">Overall Confidence</p>
            <div class="confidence-bar" style="margin-bottom:8px;">
                <div class="confidence-fill ${cls}" style="width:${conf}%;"></div>
            </div>
            <p style="font-size:26px;font-weight:700;color:var(--text-primary);margin-bottom:20px;">${conf}%</p>
            <p style="font-size:13px;color:var(--text-muted);margin-bottom:4px;">Best results from</p>
            <p style="font-size:20px;font-weight:600;color:var(--accent);">${escapeHtml(bestSource)}</p>`;
    }
}

// ============ BUTTON LABEL ============
function buttonLabel(source) {
    return {
        'Google': 'View on Google',
        'YouTube': 'View on YouTube',
        'Stack Overflow': 'View on Stack Overflow',
        'GitHub': 'View on GitHub',
        'Wikipedia': 'View on Wikipedia',
        'Dev.to': 'View on Dev.to',
        'Reddit': 'View on Reddit',
    }[source] || 'View Source';
}

// ============ RENDER RESULTS ============
function renderResults(answers) {
    const c = document.getElementById('results-container');
    if (!c) return;

    if (!answers || answers.length === 0) {
        c.innerHTML = `
            <div style="text-align:center;padding:60px 20px;">
                <div style="font-size:48px;margin-bottom:16px;">🔍</div>
                <h3 style="font-size:20px;margin-bottom:8px;">No results</h3>
                <p style="color:var(--text-secondary);margin-bottom:24px;">Try a different query.</p>
                <a href="dashboard.html" class="btn-primary" style="display:inline-block;">New Search</a>
            </div>`;
        return;
    }

    c.innerHTML = `<div class="grid-2">` + answers.map((a, i) => {
        const conf = Math.round((a.confidence || 0.5) * 100);
        const cls = conf > 70 ? 'confidence-high' : conf > 40 ? 'confidence-medium' : 'confidence-low';
        const isGemini = a.source === 'Gemini';
        const fullBody = a.body || '';
        const shortBody = fullBody.substring(0, 150);
        const isLong = fullBody.length > 150;
        const answerId = `ans-${i}`;
        const url = safeUrl(a.url);

        // ⬇️ View on X is now a REAL anchor link (never blocked)
        const actionsHtml = `
            <div class="card-actions">
                ${url ? `<a href="${escapeAttr(url)}" target="_blank" rel="noopener noreferrer" class="btn-link">${escapeHtml(buttonLabel(a.source))}</a>` : ''}
                ${url ? `<button data-action="copy-link" data-index="${i}">Copy Link</button>` : ''}
                ${isGemini ? `<button data-action="copy-answer" data-index="${i}">Copy Answer</button>` : ''}
                <button data-action="save" data-index="${i}">Save</button>
            </div>`;

        return `<div class="card" style="${isGemini ? 'grid-column:1/-1;border-color:var(--accent);' : ''}">
            <div class="card-header">
                <span class="card-title">${escapeHtml(a.title || 'Result ' + (i + 1))}</span>
                <span class="card-source">${escapeHtml(a.source || '')}</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:12px;color:var(--text-muted);">Trust: ${escapeHtml(a.trust_score || 5)}/10</span>
                ${a.date ? `<span style="font-size:12px;color:var(--text-muted);">${escapeHtml(a.date)}</span>` : ''}
            </div>
            <div class="confidence-bar">
                <div class="confidence-fill ${cls}" style="width:${conf}%;"></div>
            </div>
            <div style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">Confidence: ${conf}%</div>
            <div class="card-body" id="${answerId}-body">
                <span id="${answerId}-short">${escapeHtml(shortBody)}${isLong ? '...' : ''}</span>
                <span id="${answerId}-full" style="display:none;white-space:pre-wrap;">${escapeHtml(fullBody)}</span>
            </div>
            ${isLong ? `<button data-action="toggle" data-answer-id="${answerId}"
                style="font-size:12px;padding:6px 14px;background:transparent;border:1px solid var(--border);color:var(--accent);border-radius:4px;cursor:pointer;margin-bottom:12px;">
                <span id="${answerId}-btn">Read More</span></button>` : ''}
            ${actionsHtml}
        </div>`;
    }).join('') + `</div>`;
}

// ============ EVENT DELEGATION ============
document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const action = btn.dataset.action;
    const index = btn.dataset.index !== undefined ? parseInt(btn.dataset.index, 10) : null;
    const answerId = btn.dataset.answerId;

    switch (action) {
        case 'copy-link': {
            const a = allResults?.answers?.[index];
            const url = safeUrl(a?.url);
            if (url) copyAnswer(url);
            break;
        }
        case 'copy-answer': {
            const a = allResults?.answers?.[index];
            if (a) copyAnswer(a.body || '');
            break;
        }
        case 'save': saveResultByIndex(index); break;
        case 'toggle': toggleAnswer(answerId); break;
        case 'quick-search': {
            const q = btn.dataset.question;
            if (q) quickSearch(q);
            break;
        }
        case 'toggle-edit-profile': toggleEditProfile(); break;
        case 'toggle-change-password': toggleChangePassword(); break;
    }
});

// ============ SAVE ============
async function saveResultByIndex(index) {
    if (!allResults?.answers?.[index]) { showToast('Result not found', 'error'); return; }
    if (!isLoggedIn()) { showToast('Please login', 'error'); return; }
    const a = allResults.answers[index];
    try {
        const r = await fetch(`${API_BASE}/api/history/save`, {
            method: 'POST', headers: getHeaders(),
            body: JSON.stringify({
                query_id: allResults.query_id,
                source: a.source,
                answer: (a.body || '').slice(0, 20000),
                url: a.url || '',
                confidence: a.confidence || 0.5
            })
        });
        const d = await r.json();
        if (d.success) showToast('Saved successfully!');
        else showToast(d.error || 'Failed to save', 'error');
    } catch { showToast('Server error', 'error'); }
}

function toggleAnswer(id) {
    const s = document.getElementById(`${id}-short`);
    const f = document.getElementById(`${id}-full`);
    const b = document.getElementById(`${id}-btn`);
    if (s && f && b) {
        if (f.style.display === 'none') {
            s.style.display = 'none';
            f.style.display = 'inline';
            b.textContent = 'Show Less';
        } else {
            s.style.display = 'inline';
            f.style.display = 'none';
            b.textContent = 'Read More';
        }
    }
}

function filterResults(source) {
    if (!allResults?.answers) return;
    if (source === 'all') { renderResults(allResults.answers); return; }
    const filtered = allResults.answers.filter(a => a.source === source);
    if (filtered.length > 0) renderResults(filtered);
    else {
        const c = document.getElementById('results-container');
        if (c) c.innerHTML = `<p style="color:var(--text-secondary);text-align:center;padding:40px;">No results from ${escapeHtml(source)}.</p>`;
    }
}

function copyAnswer(text) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(
        () => showToast('Copied!'),
        () => showToast('Copy failed', 'error')
    );
}

function copyAllResults() {
    if (!allResults?.answers) return;
    let t = `TechHub Results\nQuery: ${allResults.query}\nTopic: ${allResults.topic}\n\n`;
    allResults.answers.forEach((a, i) => {
        t += `${i + 1}. [${a.source}] ${a.title}\n${a.body}\n`;
        if (a.url) t += `Source: ${a.url}\n`;
        t += `Confidence: ${Math.round((a.confidence || 0) * 100)}%\n\n`;
    });
    navigator.clipboard.writeText(t).then(() => showToast('All results copied!'));
}

async function loadRelatedQuestions(query) {
    const c = document.getElementById('related-container');
    if (!c) return;
    try {
        const r = await fetch(`${API_BASE}/api/related`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });
        const d = await r.json();
        if (d.success && d.questions?.length > 0) {
            const chips = d.questions.map(q =>
                `<span class="chip" data-action="quick-search" data-question="${escapeAttr(q)}">${escapeHtml(q)}</span>`
            ).join('');
            c.innerHTML = `<h3 style="margin-bottom:16px;font-size:18px;">Related Questions</h3>
                <div class="suggestions" style="justify-content:flex-start;">${chips}</div>`;
        }
    } catch (e) { console.warn('Related failed:', e); }
}

// ============ HISTORY / SAVED / PROFILE ============
async function loadHistory() {
    if (!isLoggedIn()) { redirect('login.html'); return; }
    const c = document.getElementById('history-container');
    if (!c) return;
    try {
        const r = await fetch(`${API_BASE}/api/history`, { headers: getHeaders() });
        const d = await r.json();
        if (d.success && d.history?.length > 0) {
            c.innerHTML = d.history.map(h => `
                <div class="history-item">
                    <div>
                        <div class="history-query">${escapeHtml(h.query)}</div>
                        <div class="history-meta">${escapeHtml(h.topic || 'N/A')} | ${escapeHtml(formatDate(h.created_at))}</div>
                    </div>
                </div>`).join('');
        } else c.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:40px;">No history yet.</p>';
    } catch { c.innerHTML = '<p style="color:var(--danger);text-align:center;padding:40px;">Failed to load.</p>'; }
}

async function loadSaved() {
    if (!isLoggedIn()) { redirect('login.html'); return; }
    const c = document.getElementById('saved-container');
    if (!c) return;
    try {
        const r = await fetch(`${API_BASE}/api/saved`, { headers: getHeaders() });
        const d = await r.json();
        if (d.success && d.saved?.length > 0) {
            c.innerHTML = `<div class="grid-2">` + d.saved.map(s => {
                const url = safeUrl(s.url);
                return `<div class="card">
                    <div class="card-header">
                        <span class="card-title">${escapeHtml(s.source)}</span>
                        <span class="card-source">${escapeHtml(formatDate(s.saved_at))}</span>
                    </div>
                    <div class="card-body">${escapeHtml((s.answer || '').substring(0, 250))}</div>
                    ${url ? `<a href="${escapeAttr(url)}" target="_blank" rel="noopener noreferrer" style="color:var(--accent);font-size:13px;">Open →</a>` : ''}
                </div>`;
            }).join('') + `</div>`;
        } else c.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:40px;">No saved answers yet.</p>';
    } catch { c.innerHTML = '<p style="color:var(--danger);text-align:center;padding:40px;">Failed to load.</p>'; }
}

async function loadProfile() {
    if (!isLoggedIn()) { redirect('login.html'); return; }
    const c = document.getElementById('profile-container');
    if (!c) return;
    try {
        const r = await fetch(`${API_BASE}/api/profile`, { headers: getHeaders() });
        const d = await r.json();
        if (!d.success || !d.user) {
            c.innerHTML = '<p style="color:var(--danger);text-align:center;padding:40px;">Failed to load.</p>';
            return;
        }
        renderProfile(d.user);
    } catch { c.innerHTML = '<p style="color:var(--danger);text-align:center;padding:40px;">Failed to load.</p>'; }
}

function renderProfile(u) {
    const c = document.getElementById('profile-container');
    if (!c) return;
    c.innerHTML = `
        <div class="card" style="max-width:600px;margin:0 auto;cursor:default;">
            <div class="card-header">
                <span class="card-title" id="profile-name-display">${escapeHtml(u.name)}</span>
                <span class="card-source">${escapeHtml(u.role || 'User')}</span>
            </div>
            <div class="card-body">
                <p><strong>Email:</strong> <span id="profile-email-display">${escapeHtml(u.email)}</span></p>
                <p><strong>Member since:</strong> ${escapeHtml(formatDate(u.created_at))}</p>
                <p><strong>Searches:</strong> ${escapeHtml(u.search_count ?? 0)}</p>
                <p><strong>Saved answers:</strong> ${escapeHtml(u.saved_count ?? 0)}</p>
            </div>
            <div id="edit-profile-form" style="display:none;margin-top:16px;padding-top:16px;border-top:1px solid var(--border);">
                <h3 style="font-size:15px;font-weight:600;margin-bottom:14px;">Edit Profile</h3>
                <div style="margin-bottom:14px;">
                    <label style="font-size:13px;color:var(--text-secondary);display:block;margin-bottom:6px;font-weight:500;">Full Name</label>
                    <input type="text" id="edit-name" value="${escapeAttr(u.name)}" maxlength="80">
                </div>
                <div style="margin-bottom:14px;">
                    <label style="font-size:13px;color:var(--text-secondary);display:block;margin-bottom:6px;font-weight:500;">Email</label>
                    <input type="email" id="edit-email" value="${escapeAttr(u.email)}" maxlength="120">
                </div>
                <div style="display:flex;gap:8px;">
                    <button class="btn-primary" id="save-profile-btn" style="flex:1;">Save Changes</button>
                    <button class="btn-outline" id="cancel-profile-btn" style="flex:1;">Cancel</button>
                </div>
            </div>
            <div id="change-password-form" style="display:none;margin-top:16px;padding-top:16px;border-top:1px solid var(--border);">
                <h3 style="font-size:15px;font-weight:600;margin-bottom:14px;">Change Password</h3>
                <div style="margin-bottom:14px;">
                    <label style="font-size:13px;color:var(--text-secondary);display:block;margin-bottom:6px;font-weight:500;">Current Password</label>
                    <input type="password" id="current-password">
                </div>
                <div style="margin-bottom:14px;">
                    <label style="font-size:13px;color:var(--text-secondary);display:block;margin-bottom:6px;font-weight:500;">New Password</label>
                    <input type="password" id="new-password">
                </div>
                <div style="margin-bottom:14px;">
                    <label style="font-size:13px;color:var(--text-secondary);display:block;margin-bottom:6px;font-weight:500;">Confirm New Password</label>
                    <input type="password" id="confirm-password">
                </div>
                <div style="display:flex;gap:8px;">
                    <button class="btn-primary" id="save-password-btn" style="flex:1;">Change Password</button>
                    <button class="btn-outline" id="cancel-password-btn" style="flex:1;">Cancel</button>
                </div>
            </div>
            <div class="card-actions" id="profile-actions" style="margin-top:16px;">
                <button data-action="toggle-edit-profile">Edit Profile</button>
                <button data-action="toggle-change-password">Change Password</button>
            </div>
        </div>`;

    const sp = document.getElementById('save-profile-btn');
    const cp = document.getElementById('cancel-profile-btn');
    const sw = document.getElementById('save-password-btn');
    const cw = document.getElementById('cancel-password-btn');
    if (sp) sp.addEventListener('click', saveProfileChanges);
    if (cp) cp.addEventListener('click', toggleEditProfile);
    if (sw) sw.addEventListener('click', savePasswordChange);
    if (cw) cw.addEventListener('click', toggleChangePassword);
}

function toggleEditProfile() {
    const f = document.getElementById('edit-profile-form');
    const p = document.getElementById('change-password-form');
    const a = document.getElementById('profile-actions');
    if (!f) return;
    const open = f.style.display !== 'none';
    f.style.display = open ? 'none' : 'block';
    if (p) p.style.display = 'none';
    if (a) a.style.display = open ? 'flex' : 'none';
    if (open) ['current-password', 'new-password', 'confirm-password'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
}

function toggleChangePassword() {
    const f = document.getElementById('change-password-form');
    const e = document.getElementById('edit-profile-form');
    const a = document.getElementById('profile-actions');
    if (!f) return;
    const open = f.style.display !== 'none';
    f.style.display = open ? 'none' : 'block';
    if (e) e.style.display = 'none';
    if (a) a.style.display = open ? 'flex' : 'none';
    if (open) ['current-password', 'new-password', 'confirm-password'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
}

async function saveProfileChanges() {
    const n = document.getElementById('edit-name');
    const e = document.getElementById('edit-email');
    const b = document.getElementById('save-profile-btn');
    if (!n || !e || !b) return;
    const name = n.value.trim();
    const email = e.value.trim();
    if (!name || name.length < 3) { showToast('Name must be at least 3 characters', 'error'); return; }
    if (!email || !email.includes('@')) { showToast('Invalid email', 'error'); return; }
    b.disabled = true; b.textContent = 'Saving...';
    try {
        const r = await fetch(`${API_BASE}/api/profile/update`, {
            method: 'PUT', headers: getHeaders(),
            body: JSON.stringify({ name, email })
        });
        const d = await r.json();
        if (d.success) {
            currentUser = { ...currentUser, ...d.user };
            localStorage.setItem('user', JSON.stringify(currentUser));
            const nd = document.getElementById('profile-name-display');
            const ed = document.getElementById('profile-email-display');
            if (nd) nd.textContent = d.user.name;
            if (ed) ed.textContent = d.user.email;
            showToast('Profile updated!');
            toggleEditProfile();
        } else showToast(d.error || 'Failed', 'error');
    } catch { showToast('Server error', 'error'); }
    finally { b.disabled = false; b.textContent = 'Save Changes'; }
}

async function savePasswordChange() {
    const c = document.getElementById('current-password');
    const n = document.getElementById('new-password');
    const cf = document.getElementById('confirm-password');
    const b = document.getElementById('save-password-btn');
    if (!c || !n || !cf || !b) return;
    if (!c.value) { showToast('Enter current password', 'error'); return; }
    if (n.value.length < 6) { showToast('New password must be at least 6 characters', 'error'); return; }
    if (n.value !== cf.value) { showToast('Passwords do not match', 'error'); return; }
    if (n.value === c.value) { showToast('New password must be different', 'error'); return; }
    b.disabled = true; b.textContent = 'Changing...';
    try {
        const r = await fetch(`${API_BASE}/api/profile/password`, {
            method: 'PUT', headers: getHeaders(),
            body: JSON.stringify({ current_password: c.value, new_password: n.value })
        });
        const d = await r.json();
        if (d.success) { showToast('Password changed!'); toggleChangePassword(); }
        else showToast(d.error || 'Failed', 'error');
    } catch { showToast('Server error', 'error'); }
    finally { b.disabled = false; b.textContent = 'Change Password'; }
}

// ============ INIT ============
document.addEventListener('DOMContentLoaded', function () {
    if (!requireLogin()) return;
    const page = window.location.pathname.split('/').pop() || 'index.html';
    if ((page === 'login.html' || page === 'register.html') && localStorage.getItem('token')) {
        window.location.href = 'dashboard.html';
        return;
    }
    initTheme();
    if (page === 'results.html') displayResults();
    else if (page === 'history.html') loadHistory();
    else if (page === 'saved.html') loadSaved();
    else if (page === 'profile.html') loadProfile();

    const si = document.getElementById('search-input');
    if (si) si.addEventListener('keypress', e => { if (e.key === 'Enter') performSearch(); });
});