// Disclosure menus: [data-menu-toggle][aria-controls] flips aria-expanded; CSS shows the menu
// (peer-aria-expanded). Closes on Escape, outside click, or once the toggle is hidden (desktop).
(() => {
  const toggles = [...document.querySelectorAll("[data-menu-toggle]")];

  const setOpen = (toggle, open) => toggle.setAttribute("aria-expanded", String(open));
  const menuOf = (toggle) => document.getElementById(toggle.getAttribute("aria-controls"));
  const closeAll = (except) => toggles.forEach((t) => t !== except && setOpen(t, false));

  toggles.forEach((toggle) =>
    toggle.addEventListener("click", () => setOpen(toggle, toggle.getAttribute("aria-expanded") !== "true")),
  );

  document.addEventListener("click", (e) => {
    closeAll(toggles.find((t) => t.contains(e.target) || menuOf(t)?.contains(e.target)));
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const open = toggles.find((t) => t.getAttribute("aria-expanded") === "true");
    if (!open) return;
    setOpen(open, false);
    open.focus();
  });

  // Reset when growing past the breakpoint, so the menu isn't unexpectedly open on shrinking back
  window.addEventListener("resize", () => toggles.forEach((t) => t.offsetParent || setOpen(t, false)));
})();
