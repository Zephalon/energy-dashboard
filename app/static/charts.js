(() => {
  const source = document.getElementById("chart-data");
  if (!source || !window.Chart) return;

  const { labels, charts } = JSON.parse(source.textContent);
  const COLORS = {
    pv: "#f59e0b",
    grid_import: "#ef4444",
    house: "#475569",
    hp_el: "#0ea5e9",
    hp_share: "#0ea5e9",
    autarky: "#10b981",
    self_use: "#f59e0b",
    cop: "#0ea5e9",
  };
  const FORMATS = {
    kwh: { scale: 1, digits: 0 },
    pct: { scale: 100, digits: 0 },
    ratio: { scale: 1, digits: 1 },
  };

  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = "#64748b";
  Chart.defaults.borderColor = "#e2e8f0";

  document.querySelectorAll("canvas[data-chart]").forEach((canvas) => {
    const chart = charts[Number(canvas.dataset.chart)];
    const { scale, digits } = FORMATS[chart.kind];
    const format = (v) =>
      v.toLocaleString("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits });

    new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: chart.series.map((s) => ({
          label: s.label,
          data: s.values.map((v) => (v === null ? null : v * scale)),
          backgroundColor: COLORS[s.key],
          borderColor: COLORS[s.key],
          tension: 0.3,
          pointRadius: 4,
          spanGaps: false,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: chart.series.length > 1, position: "top", align: "end" },
          tooltip: {
            callbacks: {
              label: (ctx) =>
                ctx.parsed.y === null ? null : `${ctx.dataset.label}: ${format(ctx.parsed.y)} ${chart.unit}`.trim(),
            },
          },
        },
        scales: {
          x: { grid: { display: false } },
          y: {
            beginAtZero: true,
            suggestedMax: chart.kind === "pct" ? 100 : undefined,
            ticks: { callback: (v) => format(v) },
          },
        },
      },
    });
  });
})();
