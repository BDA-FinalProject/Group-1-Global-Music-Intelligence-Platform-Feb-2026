"""
Content for the core informational pages (Architecture, Pipeline Overview).

This is hand-authored project description, not pipeline output — so unlike
apps/dashboard/services.py it isn't a "swap for a real API" integration
point. It's centralized here anyway so the content is easy to find and
edit without touching template markup.
"""


def get_architecture_flow():
    """Ordered stages shown as connected cards on the Architecture page."""
    return [
        {
            'icon': 'bi-hdd-network',
            'title': 'Raw Data',
            'text': 'Source systems and files land in their native formats before any processing.',
        },
        {
            'icon': 'bi-cloud-arrow-up',
            'title': 'Amazon S3',
            'text': 'Durable object storage acts as the single landing zone for every stage of the pipeline.',
        },
        {
            'icon': 'bi-layers',
            'title': 'Bronze Layer',
            'text': 'Raw data is captured as-is, with minimal validation, for full auditability.',
        },
        {
            'icon': 'bi-funnel',
            'title': 'Silver Layer',
            'text': 'Cleaned, deduplicated, and conformed data ready for analysis.',
        },
        {
            'icon': 'bi-gem',
            'title': 'Gold Layer',
            'text': 'Business-ready, aggregated datasets optimized for consumption.',
        },
        {
            'icon': 'bi-bar-chart-line',
            'title': 'Dashboard',
            'text': 'KPIs and visualizations built directly on top of Gold tables.',
        },
        {
            'icon': 'bi-chat-dots',
            'title': 'RAG Chatbot',
            'text': 'A retrieval-augmented assistant answers questions grounded in the Gold layer.',
        },
        {
            'icon': 'bi-people',
            'title': 'Users',
            'text': 'Analysts and stakeholders consume insights through the dashboard and chatbot.',
        },
    ]


def get_layer_details():
    """Bronze/Silver/Gold medallion-architecture summaries."""
    return [
        {
            'badge': 'Raw',
            'title': 'Bronze',
            'text': 'Immutable copy of source data, minimally transformed, partitioned by ingestion date.',
        },
        {
            'badge': 'Cleaned',
            'title': 'Silver',
            'text': 'Schema-enforced, deduplicated, and joined data used for downstream modeling.',
        },
        {
            'badge': 'Curated',
            'title': 'Gold',
            'text': 'Aggregated, business-level tables that power the dashboard and chatbot directly.',
        },
    ]


def get_pipeline_steps():
    """Numbered steps shown on the Pipeline Overview page."""
    return [
        {
            'step': 1,
            'title': 'Ingestion',
            'text': 'Source data is collected from files, APIs, and batch exports and written to S3.',
        },
        {
            'step': 2,
            'title': 'Bronze Landing',
            'text': 'Raw files are registered as Bronze tables with lineage metadata, unchanged from source.',
        },
        {
            'step': 3,
            'title': 'Silver Transformation',
            'text': 'Cleaning, validation, and schema enforcement produce conformed Silver tables.',
        },
        {
            'step': 4,
            'title': 'Gold Aggregation',
            'text': 'Silver tables are joined and aggregated into Gold tables tailored to reporting needs.',
        },
        {
            'step': 5,
            'title': 'Serving',
            'text': "The dashboard and chatbot read from Gold tables through a dedicated service layer.",
        },
    ]
