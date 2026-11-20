// Disclosure menus: [data-menu-toggle][aria-controls] flips aria-expanded; CSS shows the menu
// (peer-aria-expanded). Closes on Escape or a click outside the toggle and its menu.
(() => {
  const toggles = [...document.querySelectorAll("[data-menu-toggle]")];

  const isOpen = (toggle) => toggle.getAttribute("aria-expanded") === "true";
  const setOpen = (toggle, open) => toggle.setAttribute("aria-expanded", String(open));
  const isInside = (toggle, target) =>
    toggle.contains(target) || document.getElementById(toggle.getAttribute("aria-controls"))?.contains(target);

  toggles.forEach((toggle) => toggle.addEventListener("click", () => setOpen(toggle, !isOpen(toggle))));

  document.addEventListener("click", (e) => {
    toggles.forEach((t) => isInside(t, e.target) || setOpen(t, false));
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    toggles.filter(isOpen).forEach((t) => {
      setOpen(t, false);
      t.focus();
    });
  });
})();
