// Heating forecast: measured days as points, fitted curves as lines; extrapolated curve segments are dashed.
(() => {
  const source = document.getElementById("forecast-data");
  const canvas = document.querySelector("canvas[data-forecast]");
  if (!source || !canvas || !window.Chart || !window.chartTheme) return;

  const { token, alpha, format, glow, tooltip, mount } = window.chartTheme;
  const { unit, xMax, series } = JSON.parse(source.textContent);
  const DASH = [6, 4];
  const POINT_OPACITY = 0.45;
  const temp = (v) => `${format(v, 1).replace("-", "−")} °C`;

  mount(() => {
    const datasets = series.flatMap((s) => {
      const color = token(`--series-${s.key}`);
      const extrapolated = (ctx) => s.curve[ctx.p0DataIndex].ext || s.curve[ctx.p1DataIndex].ext;
      return [
        {
          type: "line",
          label: `${s.label} Kennlinie`,
          data: s.curve,
          borderColor: color,
          backgroundColor: color,
          borderWidth: 3,
          pointRadius: 0,
          pointHitRadius: 6,
          segment: { borderDash: (ctx) => (extrapolated(ctx) ? DASH : undefined) },
          order: 0,
        },
        {
          type: "scatter",
          label: `${s.label} gemessen`,
          data: s.points,
          backgroundColor: alpha(color, POINT_OPACITY),
          borderColor: alpha(color, POINT_OPACITY),
          pointRadius: 3,
          order: 1,
        },
      ];
    });

    return [
      new Chart(canvas, {
        data: { datasets },
        plugins: [glow],
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "nearest", intersect: false },
          plugins: {
            legend: { position: "top", align: "end" },
            tooltip: {
              ...tooltip(),
              callbacks: {
                title: (items) => items[0].raw.day ?? temp(items[0].parsed.x),
                label: (ctx) => {
                  const value = `${ctx.dataset.label}: ${format(ctx.parsed.y, 1)} ${unit}`;
                  return ctx.raw.day ? `${value} bei ${temp(ctx.parsed.x)}` : value;
                },
              },
            },
          },
          scales: {
            x: {
              type: "linear",
              reverse: true, // warm left, cold right
              suggestedMin: -20,
              max: xMax,
              ticks: { stepSize: 5, callback: (v) => format(v).replace("-", "−") },
              title: { display: true, text: "Tagesmitteltemperatur °C" },
            },
            y: {
              beginAtZero: true,
              ticks: { callback: (v) => format(v) },
              title: { display: true, text: `${unit} pro Tag` },
            },
          },
        },
      }),
    ];
  });
})();
