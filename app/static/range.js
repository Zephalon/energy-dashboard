// Month range form: keeps "from" <= "to" by disabling options beyond the other bound.
// Option values are YYYY-MM, so string comparison is chronological. The server also swaps as fallback.
(() => {
  const form = document.querySelector("[data-range-form]");
  if (!form) return;
  const { from, to } = form.elements;

  const sync = () => {
    [...from.options].forEach((o) => (o.disabled = o.value > to.value));
    [...to.options].forEach((o) => (o.disabled = o.value < from.value));
  };

  form.addEventListener("change", sync);
  sync();
})();
