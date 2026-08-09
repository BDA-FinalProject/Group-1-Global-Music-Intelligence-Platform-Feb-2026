"""
Views for the core app: Home, About, Architecture, Pipeline Overview.

These pages are informational/static today. If a page later needs dummy
or live data, give it a get_context_data() override backed by a small
service module — see apps/dashboard/services.py for the pattern this
project follows once real data enters the picture.
"""
from django.views.generic import TemplateView

from . import services


class HomeView(TemplateView):
    template_name = 'core/home.html'


class AboutView(TemplateView):
    template_name = 'core/about.html'


class ArchitectureView(TemplateView):
    template_name = 'core/architecture.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['flow'] = services.get_architecture_flow()
        context['layers'] = services.get_layer_details()
        context['rag_pipeline'] = services.get_rag_pipeline_steps()
        return context


class PipelineOverviewView(TemplateView):
    template_name = 'core/pipeline_overview.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['steps'] = services.get_pipeline_steps()
        return context
