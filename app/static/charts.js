(() => {
  const source = document.getElementById("chart-data");
  if (!source || !window.Chart || !window.chartTheme) return;

  const { token, alpha, format, glow, tooltip, mount } = window.chartTheme;
  const { labels, charts } = JSON.parse(source.textContent);
  const FORMATS = {
    kwh: { scale: 1, digits: 0 },
    pct: { scale: 100, digits: 0 },
    ratio: { scale: 1, digits: 1 },
  };
  const canvases = document.querySelectorAll("canvas[data-chart]");

  mount(() => {
    const fill = Number(token("--chart-fill-opacity"));

    return [...canvases].map((canvas) => {
      const chart = charts[Number(canvas.dataset.chart)];
      const { scale, digits } = FORMATS[chart.kind];
      const fmt = (v) => format(v, digits);

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
              ...tooltip(),
              callbacks: {
                label: (ctx) =>
                  ctx.parsed.y === null ? null : `${ctx.dataset.label}: ${fmt(ctx.parsed.y)} ${chart.unit}`.trim(),
                footer: (items) => (chart.stacked ? `Summe: ${fmt(sum(items))} ${chart.unit}`.trim() : ""),
              },
            },
          },
          scales: {
            x: { grid: { display: false }, stacked: chart.stacked },
            y: {
              stacked: chart.stacked,
              beginAtZero: true,
              suggestedMax: chart.kind === "pct" ? 100 : undefined,
              ticks: { callback: (v) => fmt(v) },
            },
          },
        },
      });
    });
  });
})();
