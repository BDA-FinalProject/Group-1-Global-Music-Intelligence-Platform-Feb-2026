"""
DRF views serving real Gold-layer data in place of apps.dashboard.services'
dummy data. Response shapes match apps/dashboard/serializers.py's
KPI/ChartData contracts exactly, so static/dashboard/js/dashboard.js and
apps/dashboard/templates/dashboard/dashboard.html need no changes beyond
the chart_key values used.
"""
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dashboard.serializers import ChartDataSerializer, KPISerializer

from . import services


class GoldKPIListView(APIView):
    """GET /api/v1/gold/kpis/ — real KPI cards from dashboard_summary."""

    @extend_schema(responses=KPISerializer(many=True))
    def get(self, request):
        serializer = KPISerializer(services.get_kpis(), many=True)
        return Response(serializer.data)


class GoldChartDataView(APIView):
    """GET /api/v1/gold/charts/<chart_key>/ — real chart datasets.

    chart_key: 'streams-over-time' | 'top-countries'
    """

    @extend_schema(responses=ChartDataSerializer)
    def get(self, request, chart_key):
        data = services.get_chart_data(chart_key)
        if data is None:
            return Response({'detail': 'Unknown chart_key.'}, status=404)
        serializer = ChartDataSerializer(data)
        return Response(serializer.data)
