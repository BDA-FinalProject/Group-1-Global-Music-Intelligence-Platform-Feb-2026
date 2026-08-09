"""
DRF views serving the dashboard's data over HTTP.

Each view delegates to apps.dashboard.services (currently dummy data) and
serializes the result with apps.dashboard.serializers. static/dashboard/js/
dashboard.js fetches from these endpoints, so swapping services.py for a
real data source requires no changes here or in the frontend.

Views are annotated with @extend_schema so drf-spectacular can generate
accurate OpenAPI/Swagger docs — without it, response shapes can't be
inferred from a plain APIView.
"""
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import ChartDataSerializer, FilterOptionsSerializer, KPISerializer


class KPIListView(APIView):
    """GET /api/v1/dashboard/kpis/ — top-line KPI cards."""

    @extend_schema(responses=KPISerializer(many=True))
    def get(self, request):
        serializer = KPISerializer(services.get_kpis(), many=True)
        return Response(serializer.data)


class ChartDataView(APIView):
    """GET /api/v1/dashboard/charts/<chart_key>/ — one chart's dataset."""

    @extend_schema(responses=ChartDataSerializer)
    def get(self, request, chart_key):
        data = services.get_chart_data(chart_key)
        if data is None:
            return Response({'detail': 'Unknown chart_key.'}, status=404)
        serializer = ChartDataSerializer(data)
        return Response(serializer.data)


class FilterOptionsView(APIView):
    """GET /api/v1/dashboard/filters/ — dropdown options for the filter bar."""

    @extend_schema(responses=FilterOptionsSerializer)
    def get(self, request):
        serializer = FilterOptionsSerializer(services.get_filter_options())
        return Response(serializer.data)
