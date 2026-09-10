// Loaded in the shared head so every page starts with this account's saved appearance.
window.AxiodyAppearance = (() => {
  'use strict';
  const root = document.documentElement;
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let preferences = { theme: root.dataset.themePreference, fontSize: root.dataset.fontSize };
  let queue = Promise.resolve();
  function apply(next) {
    preferences = { ...next };
    root.dataset.themePreference = preferences.theme;
    root.dataset.theme = preferences.theme === 'system' ? (system.matches ? 'dark' : 'light') : preferences.theme;
    root.dataset.fontSize = preferences.fontSize;
  }
  function save(next) {
    const snapshot = { theme: next.theme, fontSize: next.fontSize };
    apply(snapshot);
    // Serialize rapid clicks so the last selection is also the last database write.
    queue = queue.catch(() => {}).then(async () => {
      const response = await fetch(root.dataset.appearanceUrl, {
        method: 'POST', credentials: 'same-origin', keepalive: true,
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(snapshot), redirect: 'error'
      });
      if (!response.ok) throw new Error('Appearance could not be saved');
      return response.json();
    });
    return queue;
  }
  system.addEventListener('change', () => apply(preferences));
  // A back/forward cache restore must load the latest saved account preferences.
  window.addEventListener('pageshow', event => { if (event.persisted) window.location.reload(); });
  apply(preferences);
  return { apply, save, get: () => ({ ...preferences }) };
})();
