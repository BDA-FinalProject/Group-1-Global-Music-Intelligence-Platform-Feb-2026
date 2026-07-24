"""
Dummy documentation catalog.

get_documentation_cards() currently returns a hardcoded list. Swap its
implementation to read from markdown files or a docs CMS later — the
template only expects a list of dicts with the keys used below, so no
template changes are needed when that swap happens.
"""


def get_documentation_cards():
    return [
        {
            'icon': 'bi-rocket-takeoff',
            'category': 'Getting Started',
            'title': 'Project Setup Guide',
            'text': 'Clone the repo, configure environment variables, and run the site locally.',
            'code': {
                'language': 'bash',
                'snippet': 'python -m venv venv\nsource venv/bin/activate\npip install -r requirements.txt\npython manage.py runserver',
            },
        },
        {
            'icon': 'bi-diagram-3',
            'category': 'Architecture',
            'title': 'Pipeline Architecture',
            'text': 'How data flows from raw ingestion through Bronze, Silver, and Gold layers.',
        },
        {
            'icon': 'bi-code-slash',
            'category': 'API Reference',
            'title': 'REST API Reference',
            'text': 'Versioned endpoints for dashboard, chatbot, and pipeline metadata.',
            'code': {
                'language': 'http',
                'snippet': 'GET /api/v1/dashboard/kpis/\nAccept: application/json',
            },
        },
        {
            'icon': 'bi-table',
            'category': 'Data',
            'title': 'Data Dictionary',
            'text': 'Field-level definitions for tables in the Silver and Gold layers.',
            'code': {
                'language': 'json',
                'snippet': '{\n  "layer": "gold",\n  "field": "stream_count",\n  "type": "integer"\n}',
            },
        },
        {
            'icon': 'bi-box-seam',
            'category': 'Deployment',
            'title': 'Deployment Guide',
            'text': 'Environment configuration and steps for deploying to production.',
        },
        {
            'icon': 'bi-people',
            'category': 'Contributing',
            'title': 'Contributing Guide',
            'text': 'Coding standards, branching strategy, and how to submit changes.',
        },
    ]
