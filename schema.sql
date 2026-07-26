-- Gold layer schema, generated from actual s3://group-1-dbda/gold/ contents
-- inspected on 2026-07-26. NOT yet applied to any database.
--
-- IMPORTANT: track_summary, track_similarity, cluster_definitions,
-- artist_summary, country_summary, daily_timeseries (the originally designed
-- tables) DO NOT EXIST in the real Gold layer. The actual tables are:
-- artist_performance, country_performance, label_performance,
-- dashboard_summary, monthly_trends. There is no track-level grain anywhere
-- in Gold -- these are pre-aggregated marts (monthly, by artist/country/
-- label). `year` is only present as an S3 partition (year=YYYY/) for the
-- three partitioned tables below; it is NOT a column inside those parquet
-- files, so the ETL script must derive it from the object key.

CREATE EXTENSION IF NOT EXISTS vector;

-- Partitioned in S3 by year=YYYY/. ~2001 part-files, ~664K rows (estimated
-- from byte-size sampling across 6 partition-years, not an exact count).
CREATE TABLE artist_performance (
    year                INTEGER NOT NULL,   -- derived from S3 partition path
    month               INTEGER NOT NULL,
    year_month          TEXT NOT NULL,
    artist_uri          TEXT NOT NULL,
    artist_name         TEXT,
    total_streams       BIGINT,
    active_songs        BIGINT,
    countries_reached   BIGINT,
    catalog_hit_rate    DOUBLE PRECISION,
    avg_chart_strength  DOUBLE PRECISION,
    PRIMARY KEY (artist_uri, year_month)
);
CREATE INDEX idx_artist_performance_year_month ON artist_performance (year_month);

-- Partitioned in S3 by year=YYYY/. ~1920 part-files, ~6.8K rows (estimated).
CREATE TABLE country_performance (
    year                INTEGER NOT NULL,   -- derived from S3 partition path
    month               INTEGER NOT NULL,
    year_month          TEXT NOT NULL,
    country_name        TEXT NOT NULL,
    total_streams       BIGINT,
    market_share        DOUBLE PRECISION,
    growth_percentage   DOUBLE PRECISION,
    catalog_hit_rate    DOUBLE PRECISION,
    active_songs        BIGINT,
    active_artists      BIGINT,
    active_labels       BIGINT,
    top_artist          TEXT,
    top_label           TEXT,
    PRIMARY KEY (country_name, year_month)
);
CREATE INDEX idx_country_performance_year_month ON country_performance (year_month);

-- Partitioned in S3 by year=YYYY/. ~2001 part-files, ~301K rows (estimated).
CREATE TABLE label_performance (
    year                INTEGER NOT NULL,   -- derived from S3 partition path
    month               INTEGER NOT NULL,
    year_month          TEXT NOT NULL,
    standardized_label  TEXT NOT NULL,
    total_streams       BIGINT,
    market_share        DOUBLE PRECISION,
    catalog_hit_rate    DOUBLE PRECISION,
    active_songs        BIGINT,
    active_artists      BIGINT,
    PRIMARY KEY (standardized_label, year_month)
);
CREATE INDEX idx_label_performance_year_month ON label_performance (year_month);

-- Single file, not partitioned. 113 rows (exact -- whole table read).
CREATE TABLE dashboard_summary (
    year                INTEGER NOT NULL,
    month               INTEGER NOT NULL,
    year_month          TEXT NOT NULL,
    total_streams       BIGINT,
    active_songs        BIGINT,
    active_artists      BIGINT,
    active_labels       BIGINT,
    countries_covered   BIGINT,
    hit_songs           BIGINT,
    catalog_hit_rate    DOUBLE PRECISION,
    PRIMARY KEY (year_month)
);

-- Single file, not partitioned. 113 rows (exact -- whole table read).
CREATE TABLE monthly_trends (
    year                INTEGER NOT NULL,
    month               INTEGER NOT NULL,
    year_month          TEXT NOT NULL,
    total_streams       BIGINT,
    active_songs        BIGINT,
    active_artists      BIGINT,
    active_labels       BIGINT,
    PRIMARY KEY (year_month)
);

-- RAG chunk store. embedding dimension N pinned after Step 4's local
-- embedding-model test (all-MiniLM-L6-v2 -> 384-dim). Update N here if a
-- different model is chosen.
CREATE TABLE gold_chunks (
    chunk_id      SERIAL PRIMARY KEY,
    source_table  TEXT NOT NULL,   -- e.g. 'artist_performance'
    source_key    TEXT NOT NULL,   -- e.g. artist_uri + '|' + year_month
    chunk_text    TEXT NOT NULL,
    embedding     vector(384),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_gold_chunks_source ON gold_chunks (source_table, source_key);
-- ANN index -- build only after chunks are loaded, on the real row count.
-- CREATE INDEX idx_gold_chunks_embedding ON gold_chunks
--   USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
