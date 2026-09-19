/* Theme system: light / dark / system / ocean / sunset / forest, persisted in localStorage. */
(function () {
  var KEY = 'eduguard-theme';
  var ICONS = { 
    light: '\u2600\ufe0f', 
    dark: '\ud83c\udf19', 
    system: '\ud83d\udda5\ufe0f',
    ocean: '\ud83d\udca7',
    sunset: '\ud83c\udf19\ud83c\udf08',
    forest: '\ud83c\udf3f'
  };

  function getPref() {
    try {
      return localStorage.getItem(KEY) || 'system';
    } catch (e) {
      return 'system';
    }
  }

  function systemDark() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  function effective() {
    var p = getPref();
    if (p === 'system') {
      return systemDark() ? 'dark' : 'light';
    }
    return p;
  }

  function apply() {
    var pref = getPref();
    var theme = effective();
    document.documentElement.setAttribute('data-theme', pref);
    document.documentElement.setAttribute('data-resolved-theme', theme);
    // For the "system" preference, surface the OS choice so CSS can differ
    // System-dark from pure Dark while still following prefers-color-scheme.
    if (pref === 'system') {
      if (theme === 'dark') {
        document.documentElement.setAttribute('data-system-dark', 'true');
      } else {
        document.documentElement.removeAttribute('data-system-dark');
      }
    } else {
      document.documentElement.removeAttribute('data-system-dark');
    }
  }

  function syncUI() {
    var theme = effective();
    var btn = document.getElementById('themeToggle');
    if (btn) {
      btn.textContent = (ICONS[theme] || '') + ' ' + theme.charAt(0).toUpperCase() + theme.slice(1);
    }
    document.querySelectorAll('#themeMenu [data-theme-opt]').forEach(function (b) {
      var active = getPref() === b.getAttribute('data-theme-opt');
      b.classList.toggle('active', active);
      if (active) {
        b.style.fontWeight = '600';
        b.style.boxShadow = '0 0 0 2px var(--primary)';
      } else {
        b.style.fontWeight = '';
        b.style.boxShadow = '';
      }
    });
  }

  window.Theme = {
    get: getPref,
    set: function (p) {
      try { localStorage.setItem(KEY, p); } catch (e) {}
      apply();
      syncUI();
      document.dispatchEvent(new CustomEvent('theme:change', { detail: { theme: effective() } }));
    },
    current: effective,
    effective: effective,
    icons: ICONS
  };

  apply();
  syncUI();

  function listen() {
    if (!window.matchMedia) return;
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var handler = function () {
      if (getPref() === 'system') {
        apply();
        syncUI();
      }
    };
    if (mq.addEventListener) {
      mq.addEventListener('change', handler);
    } else if (mq.addListener) {
      mq.addListener(handler);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { listen(); });
  } else {
    listen();
  }
})();