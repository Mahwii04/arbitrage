// Theme toggler with persistence
(function() {
  const root = document.documentElement;
  let preloaderStart = null;
  function applyTheme(theme) {
    root.setAttribute('data-theme', theme);
    const btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.textContent = theme === 'dark' ? 'Light Mode' : 'Dark Mode';
    }
  }

  function init() {
    const saved = localStorage.getItem('theme') || 'light';
    applyTheme(saved);
    // Show preloader on initial load
    showPreloader();
  }

  window.toggleTheme = function() {
    const current = root.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    localStorage.setItem('theme', next);
    applyTheme(next);
  };

  function showPreloader() {
    const overlay = document.getElementById('preloader-overlay');
    if (!overlay) return;
    preloaderStart = Date.now();
    overlay.classList.add('show');
  }

  function hidePreloader(minMs = 2000) {
    const overlay = document.getElementById('preloader-overlay');
    if (!overlay) return;
    const elapsed = preloaderStart ? Date.now() - preloaderStart : 0;
    const remaining = Math.max(0, minMs - elapsed);
    setTimeout(() => {
      overlay.classList.remove('show');
      preloaderStart = null;
    }, remaining);
  }

  // Ensure preloader remains visible for at least 2s or until load completes
  window.addEventListener('load', function() {
    hidePreloader(2000);
  });

  // We avoid showing the preloader on clicks/submits to prevent it on
  // same-page actions (e.g., notification dropdown, modals, tabs).
  // The preloader shows on actual page loads/reloads via DOMContentLoaded.

  document.addEventListener('DOMContentLoaded', init);
})();