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
            'text': 'Spotify streaming activity — per-country, per-track, per-day — lands from source exports.',
        },
        {
            'icon': 'bi-cloud-arrow-up',
            'title': 'Amazon S3',
            'text': 'Hive-partitioned Parquet in S3 is the single landing zone for every stage below, from raw ingestion through curated Gold tables.',
        },
        {
            'icon': 'bi-layers',
            'title': 'Bronze Layer',
            'text': 'Raw streaming records captured as-is, partitioned by ingestion date, for full auditability.',
        },
        {
            'icon': 'bi-funnel',
            'title': 'Silver Layer',
            'text': 'Cleaned, deduplicated per-(country, track, day) records — including artist credits for collab tracks — ready for aggregation.',
        },
        {
            'icon': 'bi-gem',
            'title': 'Gold Layer',
            'text': '7 curated tables spanning country, artist, label, and song performance across 72 countries and 2017–2026, embedded into 560K+ vector chunks for retrieval.',
        },
        {
            'icon': 'bi-bar-chart-line',
            'title': 'Dashboard',
            'text': 'KPIs and charts served live from the Gold layer via a dedicated REST API — no dummy data.',
        },
        {
            'icon': 'bi-chat-dots',
            'title': 'RAG Chatbot',
            'text': 'A hybrid SQL + vector retrieval pipeline with reranking and a confidence gate — answers are grounded in real Gold data or the bot says so.',
        },
        {
            'icon': 'bi-people',
            'title': 'Users',
            'text': 'Analysts and stakeholders explore streaming performance through the dashboard and a natural-language chatbot.',
        },
    ]


def get_layer_details():
    """Bronze/Silver/Gold medallion-architecture summaries."""
    return [
        {
            'badge': 'Raw',
            'title': 'Bronze',
            'text': 'Immutable copy of Spotify streaming exports, partitioned by ingestion date, unchanged from source.',
        },
        {
            'badge': 'Cleaned',
            'title': 'Silver',
            'text': 'Deduplicated, per-(country, track, day) streaming records with parsed artist credits — the source used to reconstruct artist-level metrics the original Gold layer lacked.',
        },
        {
            'badge': 'Curated',
            'title': 'Gold',
            'text': '7 business-ready tables (country, label, song, and monthly-trend performance, plus artist_performance and track_catalog — both rebuilt directly from Silver) power the dashboard and chatbot.',
        },
    ]


def get_pipeline_steps():
    """Numbered steps shown on the Pipeline Overview page."""
    return [
        {
            'step': 1,
            'title': 'Ingestion',
            'text': 'Spotify streaming exports are written to S3 as Hive-partitioned Parquet.',
        },
        {
            'step': 2,
            'title': 'Bronze Landing',
            'text': 'Raw files are registered as Bronze tables, unchanged from source, for full lineage.',
        },
        {
            'step': 3,
            'title': 'Silver Transformation',
            'text': 'Records are cleaned, deduplicated, and conformed to a per-(country, track, day) grain, with collab-track artist credits parsed out.',
        },
        {
            'step': 4,
            'title': 'Gold Aggregation',
            'text': 'Silver is aggregated into 7 Gold tables — country, artist, label, and song performance — then embedded into vector chunks for retrieval.',
        },
        {
            'step': 5,
            'title': 'Serving',
            'text': 'Django + DRF read Gold data through Postgres (with pgvector for retrieval) and Redis for caching, served via Gunicorn/Nginx on AWS EC2.',
        },
    ]


def get_rag_pipeline_steps():
    """Numbered steps shown on the Architecture page describing the RAG
    chatbot's own internal pipeline — a deliberately separate, more
    detailed breakdown from get_pipeline_steps() above, since this is the
    most differentiated part of the project."""
    return [
        {
            'step': 1,
            'title': 'Query Rewrite',
            'text': 'Follow-up questions ("what about Brazil?") are resolved into standalone questions using recent conversation history before anything else runs.',
        },
        {
            'step': 2,
            'title': 'Intent Routing',
            'text': 'Aggregate questions (counts, sums, trends, "top N") are routed to a deterministic SQL path; everything else goes to semantic retrieval.',
        },
        {
            'step': 3,
            'title': 'Hybrid Retrieval',
            'text': 'Dense vector search (pgvector, semantic similarity) and full-text keyword search run together, merged by Reciprocal Rank Fusion.',
        },
        {
            'step': 4,
            'title': 'Reranking',
            'text': 'A cross-encoder rescoring pass re-orders the merged candidates for precision before the top results are kept.',
        },
        {
            'step': 5,
            'title': 'Confidence Gate',
            'text': "If the best-matching data is too far from the question's meaning, the bot says it doesn't have the data instead of guessing.",
        },
        {
            'step': 6,
            'title': 'Grounded Generation',
            'text': 'An LLM (Gemini, with Groq and a local Ollama model as automatic fallbacks) answers using only the retrieved data.',
        },
        {
            'step': 7,
            'title': 'Response Caching',
            'text': 'Redis caches recent answers and tracks per-provider usage, keeping the bot fast and within free-tier rate limits.',
        },
    ]
