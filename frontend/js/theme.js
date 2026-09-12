/* Theme system: light / dark / system, persisted in localStorage. */
(function () {
  var KEY = 'drop-theme';
  var ICONS = { light: '\u2600\ufe0f', dark: '\ud83c\udf19', system: '\ud83d\udda5\ufe0f' };

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
    var theme = effective();
    document.documentElement.setAttribute('data-theme', theme);
    // Set system dark attribute for CSS
    if (theme === 'dark' && getPref() === 'system') {
      document.documentElement.setAttribute('data-system-dark', 'true');
    } else {
      document.documentElement.removeAttribute('data-system-dark');
    }
  }

  function syncUI() {
    var theme = effective();
    var btn = document.getElementById('themeToggle');
    if (btn) btn.textContent = ICONS[theme];
    document.querySelectorAll('#themeMenu [data-theme-opt]').forEach(function (b) {
      var active = getPref() === b.getAttribute('data-theme-opt');
      b.classList.toggle('active', active);
      if (active) b.style.fontWeight = '600';
      else b.style.fontWeight = '';
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
    effective: effective
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