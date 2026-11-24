// Shared Chart.js theming. Colors and effects come from CSS tokens in theme.css, so every theme is defined in one place.
window.chartTheme = (() => {
  const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const alpha = (hex, opacity) => (opacity >= 1 ? hex : hex + Math.round(opacity * 255).toString(16).padStart(2, "0"));
  const format = (v, digits = 0) =>
    v.toLocaleString("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits });

  // Neon glow when --chart-glow > 0, read once per render instead of on every draw.
  // Lines only: canvas shadows are blurred per drawn shape, so glowing bars or scatter points would cost
  // one blur each on every frame of a hover or tooltip animation.
  let glowBlur = 0;
  const glow = {
    id: "glow",
    beforeDatasetDraw(chart, { index, meta }) {
      chart.ctx.save();
      if (!glowBlur || meta.type !== "line") return;
      chart.ctx.shadowBlur = glowBlur;
      chart.ctx.shadowColor = chart.data.datasets[index].borderColor;
    },
    afterDatasetDraw(chart) {
      chart.ctx.restore();
    },
  };

  const tooltip = () => ({
    backgroundColor: token("--chart-tooltip-bg"),
    borderColor: token("--chart-tooltip-border"),
    borderWidth: 1,
  });

  // Calls build() (returns chart instances) once the theme's web font is loaded and again on every theme change.
  // Returns render() so page scripts can redraw on their own state changes.
  const mount = (build) => {
    let instances = [];
    const render = () => {
      instances.forEach((c) => c.destroy());
      Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
      Chart.defaults.color = token("--chart-text");
      Chart.defaults.borderColor = token("--chart-grid");
      glowBlur = Number(token("--chart-glow"));
      instances = build();
    };
    const renderWhenFontReady = () =>
      document.fonts.load(`1em ${getComputedStyle(document.body).fontFamily}`).finally(render);

    renderWhenFontReady();
    document.addEventListener("themechange", renderWhenFontReady);
    return render;
  };

  return { token, alpha, format, glow, tooltip, mount };
})();
