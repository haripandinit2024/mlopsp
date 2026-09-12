/* Single stable Settings control: theme + language in one top-right panel. */
(function () {
  function build() {
    if (document.getElementById('settings-controls')) return;

    var el = document.createElement('div');
    el.id = 'settings-controls';
    el.innerHTML =
      '<button class="settings-toggle" id="settingsToggle" type="button" title="Settings">&#9881;&#65039;</button>' +
      '<div class="settings-panel hidden" id="settingsPanel">' +
      '  <div class="set-section">' +
      '    <div class="set-title" id="setTitleTheme">Theme</div>' +
      '    <div class="set-theme-menu" id="themeMenu">' +
      '      <button type="button" data-theme-opt="light">&#9728;&#65039; Light</button>' +
      '      <button type="button" data-theme-opt="dark">&#127769; Dark</button>' +
      '      <button type="button" data-theme-opt="system">&#128421;&#65039; System</button>' +
      '    </div>' +
      '  </div>' +
      '  <div class="set-section">' +
      '    <div class="set-title" id="setTitleLanguage">Language</div>' +
      '    <div class="set-lang-grid" id="langMenu"></div>' +
      '  </div>' +
      '  <a style="display:none" class="set-link" id="setLinkDashboard" href="#">Open full settings page</a>' +
      '</div>';
    document.body.appendChild(el);

    var toggle = document.getElementById('settingsToggle');
    var panel = document.getElementById('settingsPanel');

    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      panel.classList.toggle('hidden');
    });

    panel.addEventListener('click', function (e) {
      e.stopPropagation();
    });

    document.addEventListener('click', closePanel);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closePanel();
    });

    document.querySelectorAll('#themeMenu [data-theme-opt]').forEach(function (b) {
      b.addEventListener('click', function () {
        window.Theme.set(b.getAttribute('data-theme-opt'));
      });
    });

    function syncTheme() {
      document.querySelectorAll('#themeMenu [data-theme-opt]').forEach(function (b) {
        var opt = b.getAttribute('data-theme-opt');
        var active = window.Theme && window.Theme.get() === opt;
        b.classList.toggle('active', active);
        if (active && window.I18N.t) {
          b.textContent = b.dataset.themeLabel || window.I18N.t('set.' + opt);
        }
      });
    }

    document.addEventListener('theme:change', syncTheme);

    var langMenu = document.getElementById('langMenu');
    (window.I18N.languages || []).forEach(function (pair) {
      var code = pair[0], name = pair[1];
      var b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('data-lang', code);
      b.dataset.langLabel = name;
      b.textContent = name;
      b.addEventListener('click', function () {
        window.I18N.set(code);
      });
      langMenu.appendChild(b);
    });

    document.addEventListener('i18n:change', sync);
    if (window.Theme) window.Theme.set(window.Theme.get());

    var setLink = document.getElementById('setLinkDashboard');
    if (setLink) {
      setLink.addEventListener('click', function (e) {
        e.preventDefault();
        if (window.SwitchView) window.SwitchView('settings');
        else window.location.href = '/dashboard';
        closePanel();
      });
    }    function sync() {
      var cur = window.I18N.get();
      document.querySelectorAll('#langMenu [data-lang]').forEach(function (b) {
        b.classList.toggle('active', b.getAttribute('data-lang') === cur);
        if (b.classList.contains('active') && window.I18N.t) {
          b.textContent = b.dataset.langLabel;
        } else if (!b.classList.contains('active') && window.I18N.t) {
          b.textContent = window.I18N.t('set.language') || b.dataset.langLabel;
        }
      });
      var title = document.getElementById('setTitleTheme');
      if (title && window.I18N.t) title.textContent = window.I18N.t('set.theme');

      var ltitle = document.getElementById('setTitleLanguage');
      if (ltitle && window.I18N.t) ltitle.textContent = window.I18N.t('set.language');
      var link = document.getElementById('setLinkDashboard');
      if (link && window.I18N.t) link.textContent = window.I18N.t('set.linkDashboard');
      var toggle = document.getElementById('settingsToggle');
      if (toggle && window.I18N.t) toggle.title = window.I18N.t('view.settings');
    }

    function closePanel() {
      panel.classList.add('hidden');
    }

    sync();
    if (window.I18N) window.I18N.set(window.I18N.get());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }
})();