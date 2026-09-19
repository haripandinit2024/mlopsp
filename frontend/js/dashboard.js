/**
 * Dashboard - role-based access control with per-role navigation.
 * student  -> Student Dashboard
 * faculty  -> Faculty Dashboard + Interventions
 * admin    -> Admin Dashboard + Interventions
 */

const VIEW_CONF = {
    student: ['view.student', 'view.studentSub'],
    faculty: ['view.faculty', 'view.facultySub'],
    admin: ['view.admin', 'view.adminSub'],
    interventions: ['view.interventions', 'view.interventionsSub'],
    settings: ['view.settings', 'view.settingsSub'],
};

const VIEW_LABEL = (view, i) => {
    const key = VIEW_CONF[view][i];
    return (window.I18N && window.I18N.t) ? window.I18N.t(key) : key;
};

const NAV_ITEMS = {
    student: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle;"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>',
    faculty: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle;"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    admin: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
    interventions: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle;"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
    settings: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle;"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
};

const ROLE_MENUS = {
    student: ['student', 'settings'],
    faculty: ['faculty', 'interventions', 'settings'],
    admin: ['admin', 'interventions', 'settings'],
};

async function initDashboard() {
    document.getElementById('logoutBtn').addEventListener('click', async () => {
        // Clears both the Firebase client session and the server session cookie.
        if (window.AppAuth) {
            await window.AppAuth.logout().catch(() => {});
        } else {
            try { await fetch('/api/auth/logout', { method: 'POST' }); } catch (e) { /* ignore */ }
        }
        window.location.href = '/login';
    });

    // The server session is authoritative for this page (it is what shows the
    // HTML), but it can expire while the Firebase client session is still
    // valid. Re-establish it ONLY when making API calls, not on a heartbeat.
    // This prevents unnecessary redirects when the session is still valid.
    // Heartbeat is disabled - we'll re-auth on 401 responses instead.

    let user = null;
    try {
        const meRes = await fetch('/api/auth/me');
        if (meRes.ok) {
            const data = await meRes.json();
            user = data.user;
        } else if (meRes.status === 401) {
            // Session expired - try to re-establish it once.
            if (window.AppAuth && window.AppAuth.configured && window.AppAuth.currentUser) {
                try {
                    await window.AppAuth.establishSession();
                    const retryRes = await fetch('/api/auth/me');
                    if (retryRes.ok) {
                        const retryData = await retryRes.json();
                        user = retryData.user;
                    }
                } catch (reAuthError) {
                    console.warn('[dashboard] Re-auth failed:', reAuthError);
                }
            }
        }
    } catch (e) { /* ignore, handled below */ }

    // Leave /login when there is genuinely no authenticated identity. Only a
    // real 401 (expired/absent session that could not be re-established) or a
    // failed boot path reaches this — no heartbeat is running, so a healthy
    // session never bounces through here on its own.
    if (!user) {
        window.location.href = '/login';
        return;
    }

    // Safe rendering: an identity with a role we don't know must not crash the
    // shell (user.name / role lookups below). Redirect instead of throwing.
    if (!ROLE_MENUS[user.role]) {
        console.warn('[dashboard] Unsupported role:', user.role);
        window.location.href = '/login';
        return;
    }

    document.getElementById('userName').textContent = user.name || 'User';
    document.getElementById('userRole').textContent = user.role;

    // Build the nav from the role menu
    const nav = document.getElementById('navMenu');
    const renderNav = () => {
        nav.innerHTML = ROLE_MENUS[user.role].map((view, i) => `
            <li class="nav-item ${i === 0 ? 'active' : ''}" data-view="${view}">
                <span class="nav-icon">${NAV_ITEMS[view]}</span>
                <span data-i18n="${VIEW_CONF[view][0]}">${VIEW_LABEL(view, 0)}</span>
            </li>
        `).join('');
    };
    renderNav();

    // Delegate nav clicks
    nav.addEventListener('click', (e) => {
        const item = e.target.closest('.nav-item');
        if (!item) return;
        switchView(item.dataset.view);
    });

    document.addEventListener('i18n:change', renderActiveTitles);
    function renderActiveTitles() {
        const active = document.querySelector('.nav-item.active');
        if (active) {
            const view = active.dataset.view;
            document.getElementById('viewTitle').textContent = VIEW_LABEL(view, 0);
            document.getElementById('viewSubtitle').textContent = VIEW_LABEL(view, 1);
            initSettingsPanelContents();
        }
        renderNav();
    }

    switchView(ROLE_MENUS[user.role][0], user.role);
    renderActiveTitles();
    window.__currentRole = user.role;
}

function switchView(view, role) {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.view === view));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    const target = document.getElementById(view + 'View');
    if (target) target.classList.add('active');
    document.getElementById('viewTitle').textContent = VIEW_LABEL(view, 0);
    document.getElementById('viewSubtitle').textContent = VIEW_LABEL(view, 1);

    if (view === 'student' && typeof loadStudentDashboard === 'function') loadStudentDashboard();
    if (view === 'faculty') loadFacultyStudents();
    if (view === 'admin') loadAdminOverview();
    if (view === 'settings') initSettingsPanelContents();
    if (view === 'interventions' && typeof initInterventions === 'function') {
        initInterventions(role || window.__currentRole);
    }
}

// Safe fetch wrapper that handles 401 by re-authenticating
async function safeFetch(url, options = {}) {
    let res = await fetch(url, {
        credentials: 'same-origin',
        ...options,
    });
    
    // If we get a 401, try to re-establish the session
    if (res.status === 401 && window.AppAuth && window.AppAuth.configured && window.AppAuth.currentUser) {
        try {
            await window.AppAuth.establishSession();
            res = await fetch(url, {
                credentials: 'same-origin',
                ...options,
            });
        } catch (e) {
            console.warn('[dashboard] Re-auth failed:', e);
        }
    }
    
    return res;
}

function initSettingsPanelContents() {
    const i18n = window.I18N;
    if (!i18n || !i18n.t) return;
    document.querySelectorAll('#settingsView [data-i18n]').forEach(el => {
        el.textContent = i18n.t(el.getAttribute('data-i18n'));
    });
    if (!window.enableSettingsPanel) return;
    window.enableSettingsPanel();
}

window.SwitchView = switchView;

// Settings page: bind theme + language controls, populate language grid.
window.enableSettingsPanel = function () {
    const i18n = window.I18N;
    if (!i18n) return;

    const themeButtons = document.querySelectorAll('#settingsThemeMenu [data-theme-opt]');
    themeButtons.forEach(b => {
        b.onclick = () => window.Theme.set(b.getAttribute('data-theme-opt'));
    });

    const grid = document.getElementById('settingsLangGrid');
    if (grid && grid.childElementCount === 0) {
        (i18n.languages || []).forEach(pair => {
            const b = document.createElement('button');
            b.type = 'button';
            b.setAttribute('data-lang', pair[0]);
            b.textContent = pair[1];
            b.onclick = () => i18n.set(pair[0]);
            grid.appendChild(b);
        });
    }

    function sync() {
        if (window.Theme) {
            const pref = window.Theme.get();
            themeButtons.forEach(b => b.classList.toggle('active', b.getAttribute('data-theme-opt') === pref));
        }
        const cur = i18n.get();
        document.querySelectorAll('#settingsLangGrid [data-lang]').forEach(b => {
            b.classList.toggle('active', b.getAttribute('data-lang') === cur);
        });
    }

    if (!window.__settingsEnabled) {
        window.__settingsEnabled = true;
        document.addEventListener('theme:change', sync);
        document.addEventListener('i18n:change', sync);
    }
    sync();
    i18n.apply();
};

initDashboard();