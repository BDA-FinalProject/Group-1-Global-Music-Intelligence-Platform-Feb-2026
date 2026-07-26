"""
Read-only models over the Gold-layer Postgres tables (see schema.sql).

managed=False: Django does not own these tables' schema. schema.sql and
scripts/load_gold_to_postgres.py are the source of truth — the ETL job is a
truncate-and-reload batch process, not something Django migrations should
track. These models exist purely for querying via the 'gold' database alias.
"""
from django.db import models


class ArtistPerformance(models.Model):
    year = models.IntegerField()
    month = models.IntegerField()
    year_month = models.CharField(max_length=16)
    artist_uri = models.CharField(max_length=64, primary_key=True)
    artist_name = models.CharField(max_length=255, null=True)
    total_streams = models.BigIntegerField(null=True)
    active_songs = models.BigIntegerField(null=True)
    countries_reached = models.BigIntegerField(null=True)
    catalog_hit_rate = models.FloatField(null=True)
    avg_chart_strength = models.FloatField(null=True)

    class Meta:
        managed = False
        db_table = 'artist_performance'


class CountryPerformance(models.Model):
    year = models.IntegerField()
    month = models.IntegerField()
    year_month = models.CharField(max_length=16)
    country_name = models.CharField(max_length=128, primary_key=True)
    total_streams = models.BigIntegerField(null=True)
    market_share = models.FloatField(null=True)
    growth_percentage = models.FloatField(null=True)
    catalog_hit_rate = models.FloatField(null=True)
    active_songs = models.BigIntegerField(null=True)
    active_artists = models.BigIntegerField(null=True)
    active_labels = models.BigIntegerField(null=True)
    top_artist = models.CharField(max_length=255, null=True)
    top_label = models.CharField(max_length=255, null=True)

    class Meta:
        managed = False
        db_table = 'country_performance'


class LabelPerformance(models.Model):
    year = models.IntegerField()
    month = models.IntegerField()
    year_month = models.CharField(max_length=16)
    standardized_label = models.CharField(max_length=255, primary_key=True)
    total_streams = models.BigIntegerField(null=True)
    market_share = models.FloatField(null=True)
    catalog_hit_rate = models.FloatField(null=True)
    active_songs = models.BigIntegerField(null=True)
    active_artists = models.BigIntegerField(null=True)

    class Meta:
        managed = False
        db_table = 'label_performance'


class DashboardSummary(models.Model):
    year = models.IntegerField()
    month = models.IntegerField()
    year_month = models.CharField(max_length=16, primary_key=True)
    total_streams = models.BigIntegerField(null=True)
    active_songs = models.BigIntegerField(null=True)
    active_artists = models.BigIntegerField(null=True)
    active_labels = models.BigIntegerField(null=True)
    countries_covered = models.BigIntegerField(null=True)
    hit_songs = models.BigIntegerField(null=True)
    catalog_hit_rate = models.FloatField(null=True)

    class Meta:
        managed = False
        db_table = 'dashboard_summary'


class MonthlyTrends(models.Model):
    year = models.IntegerField()
    month = models.IntegerField()
    year_month = models.CharField(max_length=16, primary_key=True)
    total_streams = models.BigIntegerField(null=True)
    active_songs = models.BigIntegerField(null=True)
    active_artists = models.BigIntegerField(null=True)
    active_labels = models.BigIntegerField(null=True)

    class Meta:
        managed = False
        db_table = 'monthly_trends'
