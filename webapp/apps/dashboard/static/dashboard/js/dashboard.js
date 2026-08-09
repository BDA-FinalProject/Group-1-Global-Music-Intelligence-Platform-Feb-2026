/**
 * Dashboard charts + filters.
 *
 * Charts and KPIs are fetched from the real Gold-layer API
 * (apps.gold_data.api). The filter bar (Year/Country) re-fetches
 * everything with query params on submit — currentFilters holds the
 * active selection so a filter change re-renders charts AND KPIs
 * consistently, without a full page reload.
 */
(function () {
  const CHART_DATA_URL = (chartKey, params) => {
    const query = new URLSearchParams();
    if (params.year) query.set('year', params.year);
    if (params.country) query.set('country', params.country);
    const qs = query.toString();
    return `/api/v1/dashboard/charts/${chartKey}/${qs ? `?${qs}` : ''}`;
  };
  const KPI_URL = (params) => {
    const query = new URLSearchParams();
    if (params.year) query.set('year', params.year);
    if (params.country) query.set('country', params.country);
    const qs = query.toString();
    return `/api/v1/dashboard/kpis/${qs ? `?${qs}` : ''}`;
  };
  // Brand green first (the chart-highlight context where green is allowed
  // as an accent), then a small harmonized set for additional series.
  const CHART_COLORS = ['#1ED760', '#38bdf8', '#a78bfa', '#fb923c', '#f87171'];

  const currentFilters = { year: '', country: '' };
  // chartKey -> live Chart.js instance, so a filter change updates data
  // in place instead of stacking duplicate canvases.
  const chartInstances = {};

  function buildDatasets(payload) {
    return payload.datasets.map((dataset, index) => ({
      ...dataset,
      backgroundColor: payload.type === 'line' ? 'rgba(30, 215, 96, 0.12)' : CHART_COLORS[index % CHART_COLORS.length],
      borderColor: CHART_COLORS[index % CHART_COLORS.length],
      borderWidth: payload.type === 'line' ? 2 : 0,
      tension: 0.35,
      fill: payload.type === 'line',
      spanGaps: true,
    }));
  }

  function renderChart(canvas) {
    const chartKey = canvas.dataset.chartKey;
    // top-countries deliberately ignores the country filter server-side
    // (see gold_data/services.py) — only year is sent for it here too, so
    // the request matches what the API actually uses.
    const params = chartKey === 'top-countries'
      ? { year: currentFilters.year }
      : currentFilters;
    fetch(CHART_DATA_URL(chartKey, params))
      .then((response) => response.json())
      .then((payload) => {
        const config = {
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
        };
        const existing = chartInstances[chartKey];
        if (existing) {
          existing.data = config.data;
          existing.update();
        } else {
          chartInstances[chartKey] = new Chart(canvas, config);
        }
      })
      .catch((error) => console.error(`Failed to load chart "${chartKey}":`, error));
  }

  function renderAllCharts() {
    document.querySelectorAll('canvas[data-chart-key]').forEach(renderChart);
  }

  // Mirrors dashboard/partials/kpi_card.html's markup — KPI cards are
  // server-rendered on first paint (see DashboardView), but a filter
  // change needs to rebuild them client-side from the same JSON shape.
  function buildKpiCard(kpi) {
    const wrapper = document.createElement('div');
    wrapper.className = 'app-card kpi-card h-100';
    wrapper.innerHTML = `
      <div class="kpi-card-icon"><i class="bi ${kpi.icon}"></i></div>
      <p class="kpi-card-label">${kpi.label}</p>
      <p class="kpi-card-value">${kpi.value}</p>
      <span class="kpi-card-delta kpi-card-delta-${kpi.trend}">
        <i class="bi ${kpi.trend === 'up' ? 'bi-arrow-up-short' : 'bi-arrow-down-short'}"></i>
        ${kpi.delta}
      </span>
    `;
    return wrapper;
  }

  function renderKpis() {
    const grid = document.getElementById('kpiGrid');
    if (!grid) return;
    fetch(KPI_URL(currentFilters))
      .then((response) => response.json())
      .then((kpis) => {
        grid.innerHTML = '';
        kpis.forEach((kpi) => {
          const col = document.createElement('div');
          col.className = 'col-sm-6 col-lg-3';
          col.appendChild(buildKpiCard(kpi));
          grid.appendChild(col);
        });
      })
      .catch((error) => console.error('Failed to load KPIs:', error));
  }

  document.addEventListener('DOMContentLoaded', () => {
    renderAllCharts();

    const filterForm = document.getElementById('dashboardFilters');
    if (filterForm) {
      filterForm.addEventListener('submit', (event) => {
        event.preventDefault();
        currentFilters.year = document.getElementById('filterYear').value;
        currentFilters.country = document.getElementById('filterCountry').value;
        renderAllCharts();
        renderKpis();
      });
    }
  });
})();
