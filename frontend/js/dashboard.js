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
    student: '&#x1F393;',
    faculty: '&#x1F468;&#x200D;&#x1F3EB;',
    admin: '&#x1F4E1;',
    interventions: '&#x1FA9E;',
    settings: '&#x2699;&#xFE0F;',
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
    // valid. Re-establish it in the background so the next navigation works.
    if (window.AppAuth && window.AppAuth.configured && window.AppAuth.currentUser) {
        window.AppAuth.establishSession().catch(() => {});
        window.AppAuth.startSessionHeartbeat();
    }

    let user = null;
    try {
        const res = await fetch('/api/auth/me');
        if (res.ok) {
            const data = await res.json();
            user = data.user;
        }
    } catch (e) { /* ignore, handled below */ }

    if (!user || !ROLE_MENUS[user.role]) {
        window.location.href = '/login';
        return;
    }

    document.getElementById('userName').textContent = user.name;
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

    if (view === 'faculty') loadFacultyStudents();
    if (view === 'admin') loadAdminOverview();
    if (view === 'settings') initSettingsPanelContents();
    if (view === 'interventions' && typeof initInterventions === 'function') {
        initInterventions(role || window.__currentRole);
    }
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
    if (window.Theme) window.Theme.set(window.Theme.get());

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
    i18n.apply();
};

initDashboard();