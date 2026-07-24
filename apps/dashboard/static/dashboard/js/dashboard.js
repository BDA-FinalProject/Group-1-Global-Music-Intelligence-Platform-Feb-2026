/**
 * Dashboard charts.
 *
 * Charts are rendered from JSON served by the dashboard API endpoints
 * (currently backed by dummy data in apps/dashboard/services.py). Once
 * real pipeline data is available, only the API's response contents
 * change — this fetch/render logic stays the same.
 */
(function () {
  const CHART_DATA_URL = (chartKey) => `/api/v1/dashboard/charts/${chartKey}/`;
  // Brand green first (the chart-highlight context where green is allowed
  // as an accent), then a small harmonized set for additional series.
  const CHART_COLORS = ['#1ED760', '#38bdf8', '#a78bfa', '#fb923c', '#f87171'];

  function buildDatasets(payload) {
    return payload.datasets.map((dataset, index) => ({
      ...dataset,
      backgroundColor: payload.type === 'line' ? 'rgba(30, 215, 96, 0.12)' : CHART_COLORS[index % CHART_COLORS.length],
      borderColor: CHART_COLORS[index % CHART_COLORS.length],
      borderWidth: payload.type === 'line' ? 2 : 0,
      tension: 0.35,
      fill: payload.type === 'line',
    }));
  }

  function renderChart(canvas) {
    const chartKey = canvas.dataset.chartKey;
    fetch(CHART_DATA_URL(chartKey))
      .then((response) => response.json())
      .then((payload) => {
        new Chart(canvas, {
          type: payload.type,
          data: {
            labels: payload.labels,
            datasets: buildDatasets(payload),
          },
          options: {
            responsive: true,
            plugins: { legend: { display: payload.type !== 'line' } },
            scales: payload.type === 'doughnut' ? {} : { y: { beginAtZero: true } },
          },
        });
      })
      .catch((error) => console.error(`Failed to load chart "${chartKey}":`, error));
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('canvas[data-chart-key]').forEach(renderChart);

    const filterForm = document.getElementById('dashboardFilters');
    if (filterForm) {
      filterForm.addEventListener('submit', (event) => {
        event.preventDefault();
        // STUB: dummy data doesn't vary by filter yet. Once the API
        // supports query params (range/layer/source), read them from the
        // form here and re-fetch KPIs/charts instead of leaving canned data.
      });
    }
  });
})();
