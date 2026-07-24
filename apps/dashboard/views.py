"""
Views for the dashboard app.

The page view stays deliberately thin: all KPI/chart/filter data comes
from apps/dashboard/services.py, which currently returns dummy data and
is the single place to swap in real pipeline data later.
"""
from django.views.generic import TemplateView

from . import services


class DashboardView(TemplateView):
    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # KPI cards and filter options are rendered server-side for a fast
        # first paint. Charts are fetched client-side from the API (see
        # static/dashboard/js/dashboard.js) since Chart.js needs JS anyway.
        context['kpis'] = services.get_kpis()
        context['filters'] = services.get_filter_options()
        return context
