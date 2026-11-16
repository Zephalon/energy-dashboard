// Loaded synchronously in <head>: applies the stored theme before first paint
// and wires [data-theme-toggle] buttons. Fires "themechange" on document after a switch.
// Cyberpunk is the default (also set server-side on <html>); opting out stores "classic".
(() => {
  const KEY = "theme";
  const THEME = "cyberpunk";
  const CLASSIC = "classic";
  const BOOT_MS = 700;
  const root = document.documentElement;

  const stored = () => {
    try {
      return localStorage.getItem(KEY);
    } catch {
      return null;
    }
  };
  const store = (theme) => {
    try {
      theme ? localStorage.setItem(KEY, theme) : localStorage.removeItem(KEY);
    } catch {
      // Private mode or blocked storage: theme just won't persist
    }
  };
  const syncButtons = () =>
    document
      .querySelectorAll("[data-theme-toggle]")
      .forEach((b) => b.setAttribute("aria-pressed", String(root.dataset.theme === THEME)));

  const apply = (theme) => {
    if (theme === CLASSIC) delete root.dataset.theme;
    else root.dataset.theme = THEME;
  };

  apply(stored());

  document.addEventListener("DOMContentLoaded", () => {
    syncButtons();
    document.querySelectorAll("[data-theme-toggle]").forEach((button) =>
      button.addEventListener("click", () => {
        const next = root.dataset.theme === THEME ? CLASSIC : null;
        apply(next);
        store(next);
        syncButtons();
        if (!next) {
          root.classList.add("theme-boot");
          setTimeout(() => root.classList.remove("theme-boot"), BOOT_MS);
        }
        document.dispatchEvent(new CustomEvent("themechange"));
      }),
    );
  });
})();
