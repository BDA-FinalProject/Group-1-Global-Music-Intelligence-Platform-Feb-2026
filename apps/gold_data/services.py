"""
Real-data equivalents of apps.dashboard.services' dummy get_kpis()/
get_chart_data() — same output shapes (KPI card list, Chart.js payload),
sourced from the 'gold' Postgres database instead of hardcoded values.
"""
from .models import CountryPerformance, DashboardSummary, MonthlyTrends


def get_kpis():
    """KPI cards from the most recent two months in dashboard_summary (for deltas)."""
    rows = list(
        DashboardSummary.objects.using('gold').order_by('-year', '-month')[:2]
    )
    if not rows:
        return []
    latest = rows[0]
    prev = rows[1] if len(rows) > 1 else None

    def delta(curr, prev_val):
        if not prev_val:
            return None
        pct = (curr - prev_val) / prev_val * 100
        return f"{pct:+.1f}%", 'up' if pct >= 0 else 'down'

    streams_delta = delta(latest.total_streams, prev.total_streams if prev else None)
    artists_delta = delta(latest.active_artists, prev.active_artists if prev else None)

    return [
        {
            'id': 'total-streams',
            'label': f'Total Streams ({latest.year_month})',
            'value': f'{latest.total_streams / 1e9:.2f}B',
            'delta': streams_delta[0] if streams_delta else '—',
            'trend': streams_delta[1] if streams_delta else 'up',
            'icon': 'bi-soundwave',
        },
        {
            'id': 'active-artists',
            'label': 'Active Artists',
            'value': f'{latest.active_artists:,}',
            'delta': artists_delta[0] if artists_delta else '—',
            'trend': artists_delta[1] if artists_delta else 'up',
            'icon': 'bi-mic',
        },
        {
            'id': 'countries-covered',
            'label': 'Countries Covered',
            'value': str(latest.countries_covered),
            'delta': '—',
            'trend': 'up',
            'icon': 'bi-globe',
        },
        {
            'id': 'catalog-hit-rate',
            'label': 'Catalog Hit Rate',
            'value': f'{latest.catalog_hit_rate:.1f}%',
            'delta': '—',
            'trend': 'up',
            'icon': 'bi-graph-up-arrow',
        },
    ]


def _streams_over_time_chart():
    rows = MonthlyTrends.objects.using('gold').order_by('year', 'month')
    return {
        'type': 'line',
        'labels': [r.year_month for r in rows],
        'datasets': [{
            'label': 'Total Streams',
            'data': [r.total_streams for r in rows],
        }],
    }


def _top_countries_chart():
    """Sum streams per country within the latest year — country_performance
    is still monthly grain, so a naive top-N query returns the same country
    multiple times (once per month) instead of one bar per country."""
    from django.db.models import Sum

    latest_year = (
        CountryPerformance.objects.using('gold').order_by('-year').values_list('year', flat=True).first()
    )
    rows = (
        CountryPerformance.objects.using('gold')
        .filter(year=latest_year)
        .values('country_name')
        .annotate(yearly_streams=Sum('total_streams'))
        .order_by('-yearly_streams')[:8]
    )
    return {
        'type': 'bar',
        'labels': [r['country_name'] for r in rows],
        'datasets': [{
            'label': f'Total Streams ({latest_year})',
            'data': [r['yearly_streams'] for r in rows],
        }],
    }


_CHART_BUILDERS = {
    'streams-over-time': _streams_over_time_chart,
    'top-countries': _top_countries_chart,
}


def get_chart_data(chart_key):
    builder = _CHART_BUILDERS.get(chart_key)
    return builder() if builder else None
