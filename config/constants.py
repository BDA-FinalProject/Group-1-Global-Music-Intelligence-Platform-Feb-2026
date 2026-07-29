"""
Project Constants
"""

GOLD_TABLES = {
    "artist_performance": {
        "primary_key": "artist_uri"
    },
    "country_performance": {
        "primary_key": "country"
    },
    "label_performance": {
        "primary_key": "label"
    },
    "dashboard_summary": {
        "primary_key": None
    },
    "monthly_trends": {
        "primary_key": "year_month"
    }
}

BATCH_SIZE = 10000