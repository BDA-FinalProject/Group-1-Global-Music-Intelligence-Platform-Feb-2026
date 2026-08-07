"""
Views for the dashboard app.

KPI cards and filter options now come from apps.gold_data.services (real
Gold-layer Postgres data) — the filter bar (Year/Country) is fully wired,
both for the initial server-rendered paint here and for client-side
re-fetches on filter change (see static/dashboard/js/dashboard.js).
"""
from django.views.generic import TemplateView

from apps.gold_data import services as gold_services


class DashboardView(TemplateView):
    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # KPI cards are rendered server-side for a fast first paint. Charts
        # are fetched client-side from the API (see
        # static/dashboard/js/dashboard.js) since Chart.js needs JS anyway.
        context['kpis'] = gold_services.get_kpis()
        context['filters'] = gold_services.get_filter_options()
        return context
