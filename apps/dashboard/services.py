"""
Dummy data service for the dashboard.

This module is the dashboard's single integration point: every function
here returns realistic placeholder data today and is the only place that
needs to change when real Gold-layer data becomes available — the view,
API layer, and frontend JS all stay exactly the same.
"""


def get_kpis():
    """Top-line KPI cards shown at the top of the dashboard."""
    return [
        {
            'id': 'records-processed',
            'label': 'Records Processed',
            'value': '4.82M',
            'delta': '+12.4%',
            'trend': 'up',
            'icon': 'bi-database-check',
        },
        {
            'id': 'pipeline-uptime',
            'label': 'Pipeline Uptime',
            'value': '99.6%',
            'delta': '+0.3%',
            'trend': 'up',
            'icon': 'bi-activity',
        },
        {
            'id': 'avg-latency',
            'label': 'Avg. Ingestion Latency',
            'value': '2.1 min',
            'delta': '-8.5%',
            'trend': 'down',
            'icon': 'bi-stopwatch',
        },
        {
            'id': 'active-sources',
            'label': 'Active Data Sources',
            'value': '18',
            'delta': '+2',
            'trend': 'up',
            'icon': 'bi-hdd-network',
        },
    ]


_CHART_LIBRARY = {
    'processed-over-time': {
        'type': 'line',
        'labels': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        'datasets': [{'label': 'Records Processed (K)', 'data': [412, 480, 398, 512, 610, 356, 289]}],
    },
    'layer-distribution': {
        'type': 'doughnut',
        'labels': ['Bronze', 'Silver', 'Gold'],
        'datasets': [{'label': 'Records by Layer', 'data': [52, 33, 15]}],
    },
    'pipeline-status': {
        'type': 'bar',
        'labels': ['Ingestion', 'Bronze', 'Silver', 'Gold', 'Serving'],
        'datasets': [{'label': 'Successful Runs (Last 7 Days)', 'data': [42, 40, 38, 36, 35]}],
    },
}


def get_chart_data(chart_key):
    """Return the dataset for one chart, or None if chart_key is unknown."""
    return _CHART_LIBRARY.get(chart_key)


def get_filter_options():
    """Dropdown options for the dashboard's filter bar — offline fallback
    shape only, kept in sync with apps.gold_data.services.get_filter_options()'s
    real years/countries shape (see apps/dashboard/serializers.py's
    FilterOptionsSerializer) even though this module returns placeholder
    values, not real years/country names, since it's never routed today."""
    return {
        'years': [{'value': '', 'label': 'All Years'}],
        'countries': [{'value': '', 'label': 'All Countries'}],
    }
