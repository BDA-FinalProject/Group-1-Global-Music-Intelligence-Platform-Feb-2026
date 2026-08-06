"""
Real-data equivalents of apps.dashboard.services' dummy get_kpis()/
get_chart_data() — same output shapes (KPI card list, Chart.js payload),
sourced from the 'gold' Postgres database instead of hardcoded values.

get_kpis()/_streams_over_time_chart() used to read a pre-aggregated global
dashboard_summary/monthly_trends table (one row per month, whole platform).
That table no longer exists in the current Gold source — monthly_trends is
now country x month grain — so both are rebuilt here as cross-country sums
grouped by (year, month). This is an approximation: summing active_songs/
active_artists across countries double-counts any song/artist active in
more than one country that month (the old upstream table did this
aggregation once, correctly, before landing in Gold — this recomputes it
client-side from country-grain rows, which is the best available signal
now).
"""
from django.db.models import Count, Sum

from .models import CountryPerformance, MonthlyTrends


def _latest_periods(n=2):
    """Most recent (year, month) pairs present in monthly_trends, newest first."""
    return list(
        MonthlyTrends.objects.using('gold')
        .values('year', 'month').distinct()
        .order_by('-year', '-month')[:n]
    )


def _period_aggregate(year, month):
    qs = MonthlyTrends.objects.using('gold').filter(year=year, month=month)
    agg = qs.aggregate(
        total_streams=Sum('total_streams'),
        active_artists=Sum('active_artists'),
        active_songs=Sum('active_songs'),
        hit_songs=Sum('hit_songs'),
        countries_covered=Count('country_name', distinct=True),
    )
    agg['catalog_hit_rate'] = (
        agg['hit_songs'] / agg['active_songs'] * 100
        if agg['active_songs'] else None
    )
    return agg


def get_kpis():
    """KPI cards from the most recent two (year, month) periods, summed
    across countries (for deltas)."""
    periods = _latest_periods()
    if not periods:
        return []
    latest_period = periods[0]
    latest = _period_aggregate(latest_period['year'], latest_period['month'])
    prev = _period_aggregate(periods[1]['year'], periods[1]['month']) if len(periods) > 1 else None
    year_month = f"{latest_period['year']}-{latest_period['month']:02d}"

    def delta(curr, prev_val):
        if not curr or not prev_val:
            return None
        pct = (curr - prev_val) / prev_val * 100
        return f"{pct:+.1f}%", 'up' if pct >= 0 else 'down'

    streams_delta = delta(latest['total_streams'], prev['total_streams'] if prev else None)
    artists_delta = delta(latest['active_artists'], prev['active_artists'] if prev else None)

    return [
        {
            'id': 'total-streams',
            'label': f'Total Streams ({year_month})',
            'value': f"{latest['total_streams'] / 1e9:.2f}B" if latest['total_streams'] else '—',
            'delta': streams_delta[0] if streams_delta else '—',
            'trend': streams_delta[1] if streams_delta else 'up',
            'icon': 'bi-soundwave',
        },
        {
            'id': 'active-artists',
            'label': 'Active Artists',
            'value': f"{latest['active_artists']:,}" if latest['active_artists'] else '—',
            'delta': artists_delta[0] if artists_delta else '—',
            'trend': artists_delta[1] if artists_delta else 'up',
            'icon': 'bi-mic',
        },
        {
            'id': 'countries-covered',
            'label': 'Countries Covered',
            'value': str(latest['countries_covered']),
            'delta': '—',
            'trend': 'up',
            'icon': 'bi-globe',
        },
        {
            'id': 'catalog-hit-rate',
            'label': 'Catalog Hit Rate',
            'value': f"{latest['catalog_hit_rate']:.1f}%" if latest['catalog_hit_rate'] is not None else '—',
            'delta': '—',
            'trend': 'up',
            'icon': 'bi-graph-up-arrow',
        },
    ]


def _streams_over_time_chart():
    rows = (
        MonthlyTrends.objects.using('gold')
        .values('year', 'month')
        .annotate(total=Sum('total_streams'))
        .order_by('year', 'month')
    )
    return {
        'type': 'line',
        'labels': [f"{r['year']}-{r['month']:02d}" for r in rows],
        'datasets': [{
            'label': 'Total Streams',
            'data': [r['total'] for r in rows],
        }],
    }


def _top_countries_chart():
    """Sum streams per country within the latest year — country_performance
    is still monthly grain, so a naive top-N query returns the same country
    multiple times (once per month) instead of one bar per country."""
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
