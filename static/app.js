/* ============================================================
   app.js — AI News Aggregator frontend
   Talks to FastAPI at :8000, rendered by Flask at :5000
   ============================================================ */

const API_BASE = 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Auth utilities
// ---------------------------------------------------------------------------
const Auth = {
    getToken: ()  => localStorage.getItem('token'),
    setToken: (t) => localStorage.setItem('token', t),
    getUser:  ()  => { try { return JSON.parse(localStorage.getItem('user')); } catch { return null; } },
    setUser:  (u) => localStorage.setItem('user', JSON.stringify(u)),
    clear:    ()  => { localStorage.removeItem('token'); localStorage.removeItem('user'); },
};

// ---------------------------------------------------------------------------
// Generic API call
// ---------------------------------------------------------------------------
async function apiCall(endpoint, method = 'GET', body = null, auth = true) {
    const headers = { 'Content-Type': 'application/json' };
    if (auth && Auth.getToken()) headers['Authorization'] = `Bearer ${Auth.getToken()}`;

    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(API_BASE + endpoint, opts);
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
        const msg = data.detail || `Request failed (${res.status})`;
        throw new Error(msg);
    }
    return data;
}

// ---------------------------------------------------------------------------
// HTML escape
// ---------------------------------------------------------------------------
function esc(str) {
    const d = document.createElement('div');
    d.appendChild(document.createTextNode(str ?? ''));
    return d.innerHTML;
}

// ---------------------------------------------------------------------------
// Time helper
// ---------------------------------------------------------------------------
function timeAgo(iso) {
    if (!iso) return '';
    // Append Z only if the timestamp has no timezone info
    const ts = /Z|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + 'Z';
    const diff = Date.now() - new Date(ts).getTime();
    const m = Math.floor(diff / 60_000);
    if (m < 1)  return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
}

// ---------------------------------------------------------------------------
// Toast notifications
// ---------------------------------------------------------------------------
function showToast(msg, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = msg;
    toast.addEventListener('click', () => toast.remove());
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.transition = 'opacity 0.4s, transform 0.4s';
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 400);
    }, 4500);
}

// ===========================================================================
// AUTH PAGE
// ===========================================================================
function initAuthPage() {
    // Already logged in — go to feed
    if (Auth.getToken()) { window.location.href = '/feed'; return; }

    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
            });
            document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
            btn.classList.add('active');
            btn.setAttribute('aria-selected', 'true');
            document.getElementById(`${btn.dataset.tab}-form`).classList.add('active');
            clearAuthError();
        });
    });

    // Login
    document.getElementById('login-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn   = document.getElementById('login-btn');
        const email = document.getElementById('login-email').value.trim();
        const pass  = document.getElementById('login-password').value;

        setAuthBtnLoading(btn, 'Signing in…');
        clearAuthError();
        try {
            const data = await apiCall('/auth/login', 'POST', { email, password: pass }, false);
            Auth.setToken(data.token);
            Auth.setUser(data.user);
            window.location.href = '/feed';
        } catch (err) {
            showAuthError(err.message);
        } finally {
            resetAuthBtn(btn, 'Sign In');
        }
    });

    // Register
    document.getElementById('register-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn      = document.getElementById('register-btn');
        const username = document.getElementById('reg-username').value.trim();
        const email    = document.getElementById('reg-email').value.trim();
        const pass     = document.getElementById('reg-password').value;

        setAuthBtnLoading(btn, 'Creating account…');
        clearAuthError();
        try {
            const data = await apiCall('/auth/register', 'POST', { username, email, password: pass }, false);
            Auth.setToken(data.token);
            Auth.setUser(data.user);
            window.location.href = '/feed';
        } catch (err) {
            showAuthError(err.message);
        } finally {
            resetAuthBtn(btn, 'Create Account');
        }
    });
}

function setAuthBtnLoading(btn, text) { btn.disabled = true; btn.textContent = text; }
function resetAuthBtn(btn, text)      { btn.disabled = false; btn.textContent = text; }
function showAuthError(msg)  { const el = document.getElementById('error-msg'); el.textContent = msg; el.classList.add('visible'); }
function clearAuthError()    { const el = document.getElementById('error-msg'); if (el) el.classList.remove('visible'); }

// ===========================================================================
// FEED PAGE
// ===========================================================================
function initFeedPage() {
    if (!Auth.getToken()) { window.location.href = '/'; return; }

    // Populate user badge
    const user = Auth.getUser();
    if (user) {
        const badge = document.getElementById('user-badge');
        if (badge) badge.textContent = `👤 ${user.username}`;
    }

    // Logout
    document.getElementById('logout-btn').addEventListener('click', () => {
        Auth.clear();
        window.location.href = '/';
    });

    // Search form
    document.getElementById('search-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const topic = document.getElementById('search-input').value.trim();
        if (topic) fetchNews(topic);
    });

    loadHistory();
    initDigestDrawer();  // wire the daily digest drawer
}

// ---------------------------------------------------------------------------
// Fetch news — invokes the LangGraph pipeline via FastAPI
// ---------------------------------------------------------------------------
async function fetchNews(topic) {
    const btn       = document.getElementById('search-btn');
    const loading   = document.getElementById('loading-container');
    const results   = document.getElementById('results-section');
    const noResults = document.getElementById('no-results');

    // Reset UI
    btn.disabled = true; btn.textContent = '⏳ Fetching…';
    results.classList.remove('visible');
    noResults.classList.remove('visible');
    loading.classList.add('visible');
    startStepAnimation();

    try {
        const data = await apiCall('/news/fetch', 'POST', { topic });
        stopStepAnimation();
        loading.classList.remove('visible');

        if (!data.articles || data.articles.length === 0) {
            noResults.classList.add('visible');
            return;
        }

        renderResults(topic, data);
        loadHistory();
        showToast(
            data.cache_hit
                ? '⚡ Instant result from cache!'
                : `✅ Pipeline complete — ${data.count} story cluster${data.count !== 1 ? 's' : ''} found`,
            'success'
        );
    } catch (err) {
        stopStepAnimation();
        loading.classList.remove('visible');
        showToast(`❌ ${err.message}`, 'error');
        // If token expired, redirect to login
        if (err.message.toLowerCase().includes('token') || err.message.includes('401')) {
            Auth.clear(); window.location.href = '/';
        }
    } finally {
        btn.disabled = false; btn.textContent = '🔍 Search';
    }
}

// ---------------------------------------------------------------------------
// Render results
// ---------------------------------------------------------------------------
function renderResults(topic, data) {
    document.getElementById('results-topic').textContent = `Results for "${topic}"`;

    const countBadge = document.getElementById('results-count');
    const cacheBadge = document.getElementById('results-cache');

    countBadge.textContent = `${data.count} cluster${data.count !== 1 ? 's' : ''}`;
    cacheBadge.textContent  = data.cache_hit ? '⚡ Cached' : '🆕 Fresh';
    cacheBadge.className    = `badge ${data.cache_hit ? 'badge-cache' : 'badge-fresh'}`;

    const grid = document.getElementById('news-grid');
    grid.innerHTML = '';
    data.articles.forEach((article, i) => grid.appendChild(createCard(article, i)));

    document.getElementById('results-section').classList.add('visible');
}

// ---------------------------------------------------------------------------
// News card
// ---------------------------------------------------------------------------
function createCard(article, index) {
    const card = document.createElement('div');
    card.className = 'news-card';
    card.style.animationDelay = `${Math.min(index * 0.06, 0.5)}s`;

    const sources = (article.sources || [])
        .slice(0, 4)
        .map(s => `<span class="source-badge">${esc(s)}</span>`)
        .join('');

    const links = (article.urls || [])
        .slice(0, 3)
        .map((url, i) => `<a href="${esc(url)}" target="_blank" rel="noopener" class="article-link">Read ${i + 1} ↗</a>`)
        .join('');

    const date = article.published_at
        ? new Date(article.published_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
        : '';

    card.innerHTML = `
        <h3 class="card-headline">${esc(article.headline || 'News Update')}</h3>
        <p class="card-description">${esc(article.description || '')}</p>
        ${sources ? `<div class="card-sources">${sources}</div>` : ''}
        <div class="card-footer">
            <div class="card-links">${links}</div>
            <div class="card-meta">
                ${date ? `<span class="card-date">${date}</span>` : ''}
                <span class="card-count">${article.article_count || 1} article${(article.article_count || 1) > 1 ? 's' : ''}</span>
            </div>
        </div>
    `;
    return card;
}

// ---------------------------------------------------------------------------
// Search history sidebar
// ---------------------------------------------------------------------------
async function loadHistory() {
    const list = document.getElementById('history-list');
    if (!list) return;
    try {
        const data = await apiCall('/news/history');
        const items = data.history || [];
        if (!items.length) {
            list.innerHTML = '<p class="sidebar-empty">No searches yet.<br/>Try a topic above!</p>';
            return;
        }
        list.innerHTML = items.map(item => `
            <div class="history-item" onclick="searchFromHistory('${esc(item.topic)}')">
                <div class="topic-icon">🔍</div>
                <div>
                    <div class="topic-name">${esc(item.topic)}</div>
                    <div class="topic-time">${timeAgo(item.searched_at)}</div>
                </div>
            </div>
        `).join('');
    } catch { /* non-critical */ }
}

function searchFromHistory(topic) {
    const input = document.getElementById('search-input');
    if (input) { input.value = topic; fetchNews(topic); }
}

// ---------------------------------------------------------------------------
// Loading step animation (cycles through pipeline steps while waiting)
// ---------------------------------------------------------------------------
const STEPS = ['step-fetch', 'step-scrape', 'step-cluster', 'step-title'];
const STEP_DURATIONS = [2000, 30000, 8000, 12000]; // rough ms per step
let _stepTimer = null;
let _stepIndex = 0;

function startStepAnimation() {
    _stepIndex = 0;
    STEPS.forEach(id => document.getElementById(id)?.classList.remove('active'));
    activateStep(0);
}

function activateStep(idx) {
    if (idx >= STEPS.length) return;
    STEPS.forEach(id => document.getElementById(id)?.classList.remove('active'));
    document.getElementById(STEPS[idx])?.classList.add('active');
    _stepTimer = setTimeout(() => activateStep(idx + 1), STEP_DURATIONS[idx]);
}

function stopStepAnimation() {
    clearTimeout(_stepTimer);
    STEPS.forEach(id => document.getElementById(id)?.classList.remove('active'));
}

// ===========================================================================
// Page router (reads current path to decide which page to init)
// ===========================================================================
document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname;
    if (path === '/' || path === '/login') {
        initAuthPage();
    } else if (path === '/feed') {
        initFeedPage();
    }
});

// ===========================================================================
// DAILY DIGEST DRAWER
// ===========================================================================

// State
let _allTopics   = [];   // [{ topic, emoji }]
let _selectedSet = new Set(); // currently toggled topics

// ---------------------------------------------------------------------------
// Open / close drawer
// ---------------------------------------------------------------------------
function openDigestDrawer() {
    document.getElementById('digest-drawer').classList.add('open');
    document.getElementById('digest-overlay').classList.add('open');
    document.body.style.overflow = 'hidden';
    loadTopicsIntoDrawer();
}

function closeDigestDrawer() {
    document.getElementById('digest-drawer').classList.remove('open');
    document.getElementById('digest-overlay').classList.remove('open');
    document.body.style.overflow = '';
}

// ---------------------------------------------------------------------------
// Load topics and current subscriptions
// ---------------------------------------------------------------------------
async function loadTopicsIntoDrawer() {
    const grid = document.getElementById('topic-grid');
    grid.innerHTML = '<p class="topic-loading">Loading…</p>';

    try {
        // Parallel: fetch topic list + user's subscriptions
        const [topicsRes, subRes] = await Promise.all([
            apiCall('/daily/topics', 'GET', null, false),   // public endpoint
            apiCall('/daily/subscriptions'),
        ]);

        _allTopics   = topicsRes.topics || [];
        _selectedSet = new Set(subRes.subscriptions || []);

        renderTopicPills();
        updateSubSummary();
        updateSubCountBadge();
    } catch (err) {
        grid.innerHTML = `<p class="topic-loading" style="color:#ff6b6b">Failed to load topics: ${esc(err.message)}</p>`;
    }
}

// ---------------------------------------------------------------------------
// Render topic pills
// ---------------------------------------------------------------------------
function renderTopicPills() {
    const grid = document.getElementById('topic-grid');
    grid.innerHTML = _allTopics.map(({ topic, emoji }) => {
        const selected = _selectedSet.has(topic);
        return `
            <button
                class="topic-pill ${selected ? 'selected' : ''}"
                data-topic="${esc(topic)}"
                onclick="toggleTopic('${esc(topic)}')"
                aria-pressed="${selected}"
            >
                <span class="pill-emoji">${emoji}</span>
                <span class="pill-name">${esc(topic)}</span>
                <span class="pill-check">✓</span>
            </button>
        `;
    }).join('');
}

function toggleTopic(topic) {
    if (_selectedSet.has(topic)) {
        _selectedSet.delete(topic);
    } else {
        _selectedSet.add(topic);
    }
    // Update just the clicked pill
    const pill = document.querySelector(`.topic-pill[data-topic="${topic}"]`);
    if (pill) {
        pill.classList.toggle('selected', _selectedSet.has(topic));
        pill.setAttribute('aria-pressed', _selectedSet.has(topic));
    }
    updateSubSummary();
}

function updateSubSummary() {
    const n = _selectedSet.size;
    const el = document.getElementById('sub-summary');
    if (el) el.textContent = n === 0 ? 'No topics selected' : `${n} topic${n !== 1 ? 's' : ''} selected`;
}

function updateSubCountBadge() {
    const badge = document.getElementById('sub-count-badge');
    if (!badge) return;
    const n = _selectedSet.size;
    if (n > 0) {
        badge.textContent = n;
        badge.style.display = 'flex';
    } else {
        badge.style.display = 'none';
    }
}

// ---------------------------------------------------------------------------
// Save subscriptions
// ---------------------------------------------------------------------------
async function saveSubscriptions() {
    const btn = document.getElementById('save-subs-btn');
    btn.disabled = true;
    btn.textContent = '💾 Saving…';
    try {
        const topics = [..._selectedSet];
        await apiCall('/daily/subscriptions', 'PUT', { topics });
        updateSubCountBadge();
        showToast(`✅ Subscribed to ${topics.length} topic${topics.length !== 1 ? 's' : ''}`, 'success');
        closeDigestDrawer();
    } catch (err) {
        showToast(`❌ ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Save Subscriptions';
    }
}

// ---------------------------------------------------------------------------
// Trigger daily digest (prints to server terminal)
// ---------------------------------------------------------------------------
async function runDigest() {
    const btn = document.getElementById('run-digest-btn');
    btn.disabled = true;
    btn.textContent = '⏳ Running pipeline…';

    // Update loading UI
    const loadingTitle    = document.getElementById('loading-title');
    const loadingSubtitle = document.getElementById('loading-subtitle');
    const loading         = document.getElementById('loading-container');

    const prevTitle    = loadingTitle?.textContent;
    const prevSubtitle = loadingSubtitle?.textContent;

    if (loadingTitle)    loadingTitle.textContent    = 'Running Daily Digest Pipeline…';
    if (loadingSubtitle) loadingSubtitle.textContent = 'Fetching all subscribed topics — check server terminal';
    loading?.classList.add('visible');
    startStepAnimation();

    closeDigestDrawer();

    try {
        await apiCall('/daily/run', 'POST');
        showToast('📬 Digest complete! Check the FastAPI terminal window.', 'success');
    } catch (err) {
        showToast(`❌ ${err.message}`, 'error');
    } finally {
        stopStepAnimation();
        loading?.classList.remove('visible');
        if (loadingTitle)    loadingTitle.textContent    = prevTitle;
        if (loadingSubtitle) loadingSubtitle.textContent = prevSubtitle;
        btn.disabled = false;
        btn.textContent = '▶ Run Digest Now (Terminal)';
    }
}

// ---------------------------------------------------------------------------
// Wire drawer events (called from initFeedPage)
// ---------------------------------------------------------------------------
function initDigestDrawer() {
    document.getElementById('digest-toggle-btn')?.addEventListener('click', openDigestDrawer);
    document.getElementById('drawer-close-btn')?.addEventListener('click', closeDigestDrawer);
    document.getElementById('digest-overlay')?.addEventListener('click', closeDigestDrawer);
    document.getElementById('save-subs-btn')?.addEventListener('click', saveSubscriptions);
    document.getElementById('run-digest-btn')?.addEventListener('click', runDigest);

    // Eager-load subscription count badge
    apiCall('/daily/subscriptions').then(data => {
        _selectedSet = new Set(data.subscriptions || []);
        updateSubCountBadge();
    }).catch(() => {});
}
