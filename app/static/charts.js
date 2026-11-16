(() => {
  const source = document.getElementById("chart-data");
  if (!source || !window.Chart) return;

  const { labels, charts } = JSON.parse(source.textContent);
  const FORMATS = {
    kwh: { scale: 1, digits: 0 },
    pct: { scale: 100, digits: 0 },
    ratio: { scale: 1, digits: 1 },
  };
  const canvases = document.querySelectorAll("canvas[data-chart]");
  let instances = [];

  // Colors and effects come from CSS tokens in theme.css, so every theme is defined in one place.
  const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const alpha = (hex, opacity) => (opacity >= 1 ? hex : hex + Math.round(opacity * 255).toString(16).padStart(2, "0"));

  // Neon glow around lines and bars when --chart-glow > 0
  const glow = {
    id: "glow",
    beforeDatasetDraw(chart, { index }) {
      const blur = Number(token("--chart-glow"));
      chart.ctx.save();
      if (!blur) return;
      chart.ctx.shadowBlur = blur;
      chart.ctx.shadowColor = chart.data.datasets[index].borderColor;
    },
    afterDatasetDraw(chart) {
      chart.ctx.restore();
    },
  };

  const render = () => {
    instances.forEach((c) => c.destroy());
    const fill = Number(token("--chart-fill-opacity"));

    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.color = token("--chart-text");
    Chart.defaults.borderColor = token("--chart-grid");

    instances = [...canvases].map((canvas) => {
      const chart = charts[Number(canvas.dataset.chart)];
      const { scale, digits } = FORMATS[chart.kind];
      const format = (v) =>
        v.toLocaleString("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits });

      const sum = (items) => items.reduce((total, item) => total + (item.parsed.y ?? 0), 0);

      return new Chart(canvas, {
        type: chart.stacked ? "bar" : "line",
        plugins: [glow],
        data: {
          labels,
          datasets: chart.series.map((s) => {
            const color = token(`--series-${s.key}`);
            return {
              label: s.label,
              data: s.values.map((v) => (v === null ? null : v * scale)),
              backgroundColor: alpha(color, fill),
              borderColor: color,
              borderWidth: chart.stacked ? Number(fill < 1) : 3, // outline translucent bars only
              tension: 0.3,
              pointRadius: 4,
              spanGaps: false,
            };
          }),
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: { display: chart.series.length > 1, position: "top", align: "end" },
            tooltip: {
              backgroundColor: token("--chart-tooltip-bg"),
              borderColor: token("--chart-tooltip-border"),
              borderWidth: 1,
              callbacks: {
                label: (ctx) =>
                  ctx.parsed.y === null ? null : `${ctx.dataset.label}: ${format(ctx.parsed.y)} ${chart.unit}`.trim(),
                footer: (items) => (chart.stacked ? `Summe: ${format(sum(items))} ${chart.unit}`.trim() : ""),
              },
            },
          },
          scales: {
            x: { grid: { display: false }, stacked: chart.stacked },
            y: {
              stacked: chart.stacked,
              beginAtZero: true,
              suggestedMax: chart.kind === "pct" ? 100 : undefined,
              ticks: { callback: (v) => format(v) },
            },
          },
        },
      });
    });
  };

  // A theme's web font may still be loading; canvas text needs it before drawing
  const renderWhenFontReady = () =>
    document.fonts.load(`1em ${getComputedStyle(document.body).fontFamily}`).finally(render);

  renderWhenFontReady();
  document.addEventListener("themechange", renderWhenFontReady);
})();
