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
    # allow_null: the hit-rate-trend chart can have a gap (a period with
    # zero active_songs, so the ratio is undefined) — Chart.js handles a
    # null data point fine (a break in the line), it just needs to survive
    # serialization instead of erroring on a non-float value.
    data = serializers.ListField(child=serializers.FloatField(allow_null=True))


class ChartDataSerializer(serializers.Serializer):
    type = serializers.CharField()
    labels = serializers.ListField(child=serializers.CharField())
    datasets = ChartDatasetSerializer(many=True)


class FilterOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class FilterOptionsSerializer(serializers.Serializer):
    years = FilterOptionSerializer(many=True)
    countries = FilterOptionSerializer(many=True)
