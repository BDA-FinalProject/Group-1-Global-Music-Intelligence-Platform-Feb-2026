"""
DRF views serving real Gold-layer data in place of apps.dashboard.services'
dummy data. Response shapes match apps/dashboard/serializers.py's
KPI/ChartData/FilterOptions contracts exactly, so static/dashboard/js/
dashboard.js and apps/dashboard/templates/dashboard/dashboard.html need no
changes beyond the chart_key values and query params used.
"""
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dashboard.serializers import ChartDataSerializer, FilterOptionsSerializer, KPISerializer

from . import services

_FILTER_PARAMS = [
    OpenApiParameter('year', int, description='Restrict to this year. Omit for all years.'),
    OpenApiParameter('country', str, description='Restrict to this country. Omit for all countries.'),
]


class GoldKPIListView(APIView):
    """GET /api/v1/dashboard/kpis/?year=&country= — real KPI cards."""

    @extend_schema(parameters=_FILTER_PARAMS, responses=KPISerializer(many=True))
    def get(self, request):
        year = request.query_params.get('year')
        country = request.query_params.get('country') or None
        kpis = services.get_kpis(year=int(year) if year else None, country=country)
        serializer = KPISerializer(kpis, many=True)
        return Response(serializer.data)


class GoldChartDataView(APIView):
    """GET /api/v1/dashboard/charts/<chart_key>/?year=&country= — real chart datasets.

    chart_key: 'streams-over-time' | 'top-countries' | 'top-artists' | 'hit-rate-trend'
    top-countries ignores `country` (see services._top_countries_chart()'s docstring).
    """

    @extend_schema(parameters=_FILTER_PARAMS, responses=ChartDataSerializer)
    def get(self, request, chart_key):
        year = request.query_params.get('year')
        country = request.query_params.get('country') or None
        data = services.get_chart_data(chart_key, year=int(year) if year else None, country=country)
        if data is None:
            return Response({'detail': 'Unknown chart_key.'}, status=404)
        serializer = ChartDataSerializer(data)
        return Response(serializer.data)


class GoldFilterOptionsView(APIView):
    """GET /api/v1/dashboard/filters/ — real Year/Country dropdown options."""

    @extend_schema(responses=FilterOptionsSerializer)
    def get(self, request):
        serializer = FilterOptionsSerializer(services.get_filter_options())
        return Response(serializer.data)
