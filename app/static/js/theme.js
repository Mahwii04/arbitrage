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

  // Show preloader on navigation via links and form submissions
  document.addEventListener('click', function(e) {
    const anchor = e.target.closest('a');
    if (!anchor) return;
    const href = anchor.getAttribute('href');
    const target = anchor.getAttribute('target');
    if (href && href !== '#' && (!target || target === '_self')) {
      showPreloader();
    }
  }, true);

  document.addEventListener('submit', function() {
    showPreloader();
  }, true);

  document.addEventListener('DOMContentLoaded', init);
})();