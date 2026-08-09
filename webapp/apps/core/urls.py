"""URL routes for the core app."""
from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('about/', views.AboutView.as_view(), name='about'),
    path('architecture/', views.ArchitectureView.as_view(), name='architecture'),
    path('pipeline-overview/', views.PipelineOverviewView.as_view(), name='pipeline_overview'),
]
