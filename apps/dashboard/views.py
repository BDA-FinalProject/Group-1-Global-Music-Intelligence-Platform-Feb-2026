"""
Views for the dashboard app.

KPI cards now come from apps.gold_data.services (real Gold-layer Postgres
data). Filter options remain from apps.dashboard.services — the filter bar
is still a non-functional stub (see static/dashboard/js/dashboard.js), not
in scope for this pass.
"""
from django.views.generic import TemplateView

from apps.gold_data import services as gold_services

from . import services


class DashboardView(TemplateView):
    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # KPI cards are rendered server-side for a fast first paint. Charts
        # are fetched client-side from the API (see
        # static/dashboard/js/dashboard.js) since Chart.js needs JS anyway.
        context['kpis'] = gold_services.get_kpis()
        context['filters'] = services.get_filter_options()
        return context
