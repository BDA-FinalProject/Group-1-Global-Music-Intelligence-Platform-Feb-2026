"""
Serializers for the dashboard API.

Used even though the current data source is a plain dict (see
services.py) — this keeps the response contract explicit and consistent
with every other endpoint in this project, so nothing here needs to
change when the data source becomes a real queryset.
"""
from rest_framework import serializers


class KPISerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    value = serializers.CharField()
    delta = serializers.CharField()
    trend = serializers.ChoiceField(choices=['up', 'down'])
    icon = serializers.CharField()


class ChartDatasetSerializer(serializers.Serializer):
    label = serializers.CharField()
    data = serializers.ListField(child=serializers.FloatField())


class ChartDataSerializer(serializers.Serializer):
    type = serializers.CharField()
    labels = serializers.ListField(child=serializers.CharField())
    datasets = ChartDatasetSerializer(many=True)


class FilterOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class FilterOptionsSerializer(serializers.Serializer):
    date_ranges = FilterOptionSerializer(many=True)
    layers = FilterOptionSerializer(many=True)
    sources = FilterOptionSerializer(many=True)
