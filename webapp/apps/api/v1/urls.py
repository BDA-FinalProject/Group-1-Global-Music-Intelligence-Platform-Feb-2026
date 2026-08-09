"""
v1 API routes.

A single DRF DefaultRouter is shared across all domain apps so the full
API surface is visible in one place. Each feature app (dashboard,
chatbot, ...) owns its own serializers/views in its own module and
registers them here as that feature's dummy-data API is built out —
domain logic stays in the domain app, this file just wires it together.

/api/v1/schema/, /docs/, /redoc/ are wired up now (via drf-spectacular)
so interactive API docs are available from day one, even while every
endpoint still returns dummy data.
"""
from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter

from apps.chatbot.api import ChatMessageView
from apps.gold_data.api import GoldChartDataView, GoldFilterOptionsView, GoldKPIListView

app_name = 'v1'

router = DefaultRouter()
# ViewSet-backed resources register here, e.g.:
#   router.register('chatbot/conversations', ConversationViewSet, basename='chatbot-conversations')

urlpatterns = router.urls + [
    # Dashboard KPIs/charts/filters are now served from the real Gold-layer
    # data (apps.gold_data) rather than apps.dashboard.services' dummy data
    # — apps.dashboard.api.KPIListView/ChartDataView/FilterOptionsView are
    # kept as an offline demo-mode fallback (same pattern as apps.chatbot's
    # canned-reply stub) but are no longer routed here.
    path('dashboard/kpis/', GoldKPIListView.as_view(), name='dashboard-kpis'),
    path('dashboard/charts/<str:chart_key>/', GoldChartDataView.as_view(), name='dashboard-chart'),
    path('dashboard/filters/', GoldFilterOptionsView.as_view(), name='dashboard-filters'),
    path('chatbot/messages/', ChatMessageView.as_view(), name='chatbot-messages'),
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='api:v1:schema'), name='docs'),
    path('redoc/', SpectacularRedocView.as_view(url_name='api:v1:schema'), name='redoc'),
]
