"""
Aggregates artist_performance / country_performance / label_performance from
monthly grain to yearly grain, generates one RAG chunk per (entity, year),
embeds with all-MiniLM-L6-v2, and loads into gold_chunks.

dashboard_summary and monthly_trends are intentionally excluded — they're
single aggregate rows, not per-entity narrative material.

Usage:
    python scripts/build_gold_chunks.py
"""
import os
import time

import pandas as pd
import psycopg2
from sentence_transformers import SentenceTransformer

PG_DSN = (
    f"host={os.environ.get('PGHOST', 'localhost')} "
    f"port={os.environ.get('PGPORT', 5432)} "
    f"dbname={os.environ.get('PGDATABASE', 'gold')} "
    f"user={os.environ.get('PGUSER', os.environ.get('USER'))} "
    f"password={os.environ.get('PGPASSWORD', '')}"
)


# --- Yearly aggregation -----------------------------------------------

def aggregate_artist_performance(conn):
    df = pd.read_sql(
        "SELECT year, artist_uri, artist_name, total_streams, active_songs, "
        "countries_reached, catalog_hit_rate, avg_chart_strength "
        "FROM artist_performance",
        conn,
    )
    agg = df.groupby(['artist_uri', 'year']).agg(
        artist_name=('artist_name', 'first'),
        total_streams=('total_streams', 'sum'),      # sum: additive volume metric
        active_songs=('active_songs', 'max'),         # max: catalog size, not additive across months
        countries_reached=('countries_reached', 'max'),  # max: broadest reach seen that year
        catalog_hit_rate=('catalog_hit_rate', 'mean'),    # mean: a rate, average across months
        avg_chart_strength=('avg_chart_strength', 'mean'),  # mean: already an average metric
    ).reset_index()
    return agg


def aggregate_country_performance(conn):
    df = pd.read_sql(
        "SELECT year, country_name, total_streams, market_share, "
        "growth_percentage, catalog_hit_rate, active_songs, active_artists, "
        "active_labels, top_artist, top_label FROM country_performance",
        conn,
    )
    agg = df.groupby(['country_name', 'year']).agg(
        total_streams=('total_streams', 'sum'),        # sum: additive volume
        market_share=('market_share', 'mean'),          # mean: a share/percentage
        growth_percentage=('growth_percentage', 'mean'),  # mean: a rate
        catalog_hit_rate=('catalog_hit_rate', 'mean'),    # mean: a rate
        active_songs=('active_songs', 'max'),            # max: broadest catalog seen
        active_artists=('active_artists', 'max'),
        active_labels=('active_labels', 'max'),
        top_artist=('top_artist', 'last'),               # last: most recent month's leader
        top_label=('top_label', 'last'),
    ).reset_index()
    return agg


def aggregate_label_performance(conn):
    df = pd.read_sql(
        "SELECT year, standardized_label, total_streams, market_share, "
        "catalog_hit_rate, active_songs, active_artists FROM label_performance",
        conn,
    )
    agg = df.groupby(['standardized_label', 'year']).agg(
        total_streams=('total_streams', 'sum'),      # sum: additive volume
        market_share=('market_share', 'mean'),         # mean: a share/percentage
        catalog_hit_rate=('catalog_hit_rate', 'mean'),  # mean: a rate
        active_songs=('active_songs', 'max'),
        active_artists=('active_artists', 'max'),
    ).reset_index()
    return agg


# --- Chunk text templates (yearly framing) -----------------------------

def artist_chunk(row):
    return (
        f"In {int(row['year'])}, artist {row['artist_name']} "
        f"({row['artist_uri']}) had {int(row['total_streams']):,} total "
        f"streams across up to {int(row['active_songs'])} active song(s), "
        f"reaching up to {int(row['countries_reached'])} countries that "
        f"year. Average catalog hit rate was {row['catalog_hit_rate']:.2f}%, "
        f"average chart strength {row['avg_chart_strength']:.2f}."
    )


def country_chunk(row):
    return (
        f"In {row['country_name']} during {int(row['year'])}, Spotify "
        f"recorded {int(row['total_streams']):,} total streams "
        f"(avg {row['market_share']:.2f}% market share, avg "
        f"{row['growth_percentage']:.2f}% growth), with up to "
        f"{int(row['active_songs'])} active song(s) and an average catalog "
        f"hit rate of {row['catalog_hit_rate']:.2f}%. Up to "
        f"{int(row['active_artists'])} active artists and "
        f"{int(row['active_labels'])} active labels were represented that "
        f"year. Most recent top artist was {row['top_artist']}, top label "
        f"was {row['top_label']}."
    )


def label_chunk(row):
    return (
        f"Label {row['standardized_label']} in {int(row['year'])} had "
        f"{int(row['total_streams']):,} total streams (avg "
        f"{row['market_share']:.2f}% market share) across up to "
        f"{int(row['active_songs'])} active song(s) from up to "
        f"{int(row['active_artists'])} artist(s). Average catalog hit rate: "
        f"{row['catalog_hit_rate']:.2f}%."
    )


TABLES = [
    ('artist_performance', aggregate_artist_performance, artist_chunk, 'artist_uri'),
    ('country_performance', aggregate_country_performance, country_chunk, 'country_name'),
    ('label_performance', aggregate_label_performance, label_chunk, 'standardized_label'),
]


def main():
    conn = psycopg2.connect(PG_DSN)

    all_chunks = []  # (source_table, source_key, chunk_text)
    for table_name, agg_fn, chunk_fn, key_col in TABLES:
        df_monthly_count = pd.read_sql(f"SELECT count(*) AS n FROM {table_name}", conn)
        monthly_rows = int(df_monthly_count['n'][0])

        yearly = agg_fn(conn)
        yearly_rows = len(yearly)
        ratio = monthly_rows / yearly_rows if yearly_rows else 0
        print(f"{table_name}: monthly rows={monthly_rows:,} -> yearly rows="
              f"{yearly_rows:,} ({ratio:.1f}x reduction)")

        for _, row in yearly.iterrows():
            text = chunk_fn(row)
            key = f"{row[key_col]}|{int(row['year'])}"
            all_chunks.append((table_name, key, text))

    print(f"\nTotal chunks to embed: {len(all_chunks):,}")

    model = SentenceTransformer('all-MiniLM-L6-v2')
    texts = [c[2] for c in all_chunks]

    t0 = time.time()
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)
    elapsed = time.time() - t0
    print(f"Embedded {len(texts):,} chunks in {elapsed:.1f}s "
          f"({elapsed/60:.1f} min)")

    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE gold_chunks RESTART IDENTITY")
    rows = [
        (src, key, text, emb.tolist())
        for (src, key, text), emb in zip(all_chunks, embeddings)
    ]
    cur.executemany(
        "INSERT INTO gold_chunks (source_table, source_key, chunk_text, embedding) "
        "VALUES (%s, %s, %s, %s)",
        rows,
    )
    conn.commit()

    cur.execute("SELECT count(*) FROM gold_chunks")
    final_count = cur.fetchone()[0]
    print(f"gold_chunks final row count: {final_count:,}")
    conn.close()


if __name__ == '__main__':
    main()
