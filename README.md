# StreamPulse — Global Music Intelligence Platform

Django app: Gold-layer Spotify analytics dashboard + a RAG chatbot that answers questions from the real data.

CDAC Big Data Engineering group project.

---

## System architecture

```
┌─────────────┐     ┌──────────────────┐     ┌───────────────────────────┐
│   AWS S3     │────▶│  PostgreSQL 17     │────▶│   Django (EC2, Nginx +     │
│  Gold layer  │     │  + pgvector        │     │   Gunicorn)                 │
│  (Parquet)   │     │                    │     │                              │
└─────────────┘     │  ├─ country_performance│  │  ┌─────────┐  ┌───────────┐ │
                     │  ├─ kpi_artist         │  │  │Dashboard │  │  Chatbot   │ │
                     │  ├─ kpi_song           │  │  └─────────┘  └───────────┘ │
                     │  ├─ label_performance_ │  └──────────┬──────────────────┘
                     │  │   enhanced          │             │
                     │  ├─ monthly_trends     │             │
                     │  └─ gold_chunks (RAG)  │             ▼
                     └────────────────────────┘      Groq LLM API
                                                    (llama-3.3-70b)
```

Source bucket: `s3://spotify-lake-dev-data/gold/` — country/artist/song/label/monthly-trend
tables, all country-grain. `kpi_artist` is a country×artist×month presence table with no metric
columns (no artist-level streams/active-songs exist in this source), so it's used only for
entity-count SQL queries, never for RAG chunks or superlative/trend queries.

```
scripts/load_gold_to_postgres.py   S3 Parquet ──▶ Postgres Gold tables
scripts/build_gold_chunks.py       Gold tables ──▶ yearly chunks ──▶ MiniLM embeddings ──▶ gold_chunks
```

### Stack

| Layer | Choice |
|---|---|
| Data lake | AWS S3, Parquet |
| DB | PostgreSQL 17 |
| Vector search | pgvector, `ivfflat` index |
| Embeddings | `all-MiniLM-L6-v2` (local) |
| LLM | Groq `llama-3.3-70b-versatile` (falls back to local Ollama) |
| Backend | Django 6 + DRF |
| Hosting | AWS EC2 `m5.large`, Nginx + Gunicorn |

More detail: [`RAG_ARCHITECTURE.md`](./RAG_ARCHITECTURE.md) · [`GOLD_LAYER_REPORT.md`](./GOLD_LAYER_REPORT.md) · [`GOLD_LAYER_LIVE_REPORT.md`](./GOLD_LAYER_LIVE_REPORT.md)

---

## RAG pipeline — request flow

```
                              User question
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │  keyword match?                 │
                    │  "highest/most/how many/grew"   │
                    └───────┬─────────────────┬───────┘
                        yes │                 │ no
                            ▼                 ▼
                ┌───────────────────┐   ┌─────────────────────────┐
                │   SQL router        │   │  2+ known countries       │
                │   (parameterized     │   │  named in question?       │
                │   query on Gold      │   └──────┬─────────────┬────┘
                │   tables)            │      yes  │             │ no
                └─────────┬───────────┘            ▼             ▼
                          │              ┌──────────────────┐ ┌─────────────────┐
                          │              │ per-country        │ │ embed_query()     │
                          │              │ scoped retrieval    │ │ classify_query()  │
                          │              │ (one query each,    │ │ retrieve_chunks() │
                          │              │  merged)             │ └────────┬─────────┘
                          │              └─────────┬────────┘          │
                          │                        │           ┌───────┴────────┐
                          │                        │           │ no table match  │
                          │                        │           │ + distance too   │
                          │                        │           │ far?             │
                          │                        │           └───┬─────────┬───┘
                          │                        │            yes│         │no
                          │                        │               ▼         │
                          │                        │        "I don't have    │
                          │                        │         data for that"  │
                          │                        │        (no LLM call)    │
                          │                        │                        │
                          └────────────┬───────────┴────────────────────────┘
                                       ▼
                              build_prompt(context)
                                       │
                                       ▼
                              Groq / Ollama LLM
                                       │
                                       ▼
                                    Answer
```

### Where `gold_chunks` comes from

```
Gold tables (monthly)
      │  groupby(entity, year)   sum / max / mean per column
      ▼
yearly rows
      │  one text sentence per (entity, year)
      ▼
chunk text  ──▶  all-MiniLM-L6-v2  ──▶  384-dim vector  ──▶  gold_chunks (pgvector)
```

~408,849 chunks total (344,323 track · 63,864 label · 662 country). No artist-level chunks —
the source data has no artist metric columns (see architecture diagram above).

---

## Gold-layer tables — what data actually exists

Source: `s3://spotify-lake-dev-data/gold/`, Parquet, Hive-partitioned. Loaded into Postgres by
`scripts/load_gold_to_postgres.py`, schema owned by `schema.sql`.

| Table | S3 partitioning | Grain | Columns | Rows loaded |
|---|---|---|---|---|
| `country_performance` | `year=YYYY/` (month is a column) | country × month | `year, month, year_month, country_name, total_streams, active_songs, hit_songs, avg_chart_strength, active_artists, monthly_total_streams, top_song_name, top_artist_name, growth_percentage` | 7,383 |
| `kpi_artist` | `year=YYYY/month=M/` | country × artist × month | `year, month, year_month, country_name, artist_uri` — **no metric columns** | 1,894,035 |
| `kpi_song` | `year=YYYY/month=M/` | country × track × month | `year, month, year_month, country_name, uri, standardized_label, total_streams, is_hit` | 2,462,557 |
| `label_performance_enhanced` | `year=YYYY/` (month is a column) | country × label × month | `year, month, year_month, country_name, standardized_label, total_streams, active_songs, active_artists` | 929,858 |
| `monthly_trends` | `year=YYYY/` (month is a column) | country × month | `year, month, year_month, country_name, total_streams, active_songs, active_labels, hit_songs, avg_chart_strength, active_artists, growth_percentage` | 7,313 |
| `gold_chunks` | — (Postgres-only, RAG store) | entity × year | `chunk_id, source_table, source_key, chunk_text, embedding vector(384)` | 408,849 |

**Why `kpi_artist` can't answer "how much did artist X stream"**: it's a pure presence table
(which artist appeared in which country, in which month) with zero numeric columns. `kpi_song`
has real streaming numbers, but only at the *track* level (`uri`, a `spotify:track:...` id) — and
there is no artist↔track mapping anywhere in these 5 tables (`kpi_artist.artist_uri` values and
`kpi_song.uri` values were checked directly against each other: zero overlap). So artist-level
totals genuinely cannot be computed from this Gold source, not just "not implemented yet."

---

## What the chatbot can and can't answer

The RAG pipeline (`apps/chatbot/rag.py`, `get_rag_reply()`) routes every question through, in order:

1. **SQL router** (`detect_sql_intent()`) — deterministic answers for count/superlative/growth
   questions, computed straight from Postgres, no LLM guessing involved for the number itself.
2. **Artist-keyword hard block** — a non-count question mentioning "artist"/"singer"/"musician"
   returns `"I don't have data to answer that."` immediately (see table above for why).
3. **Multi-country comparison** — 2+ real country names in one question get separate, merged
   retrievals so one country can't crowd the other out of a shared top-k.
4. **Vector retrieval + confidence gate** — embeds the question, searches `gold_chunks` via
   pgvector, and refuses to answer (rather than guess) if no table/keyword matched *and* the
   closest chunk is still farther than `NO_MATCH_DISTANCE_THRESHOLD` (0.95).

| Can answer | Can't answer (and why) |
|---|---|
| Country lookups/comparisons (`country_performance`) | Artist-level anything — no metrics exist for artists in this source |
| Label lookups (`label_performance_enhanced`, global-aggregated across countries) | Country-scoped label questions ("top label **in India**") — label chunks are global totals, not per-country |
| Track lookups (`kpi_song`, cited by raw `spotify:track:...` URI) | Track names — `kpi_song` has no title column, only URIs |
| Counts: artists, labels, tracks, countries (`COUNT(DISTINCT ...)`) | `catalog_hit_rate` — this column existed in the old source, doesn't exist in the new one |
| Superlatives: highest/lowest streams by country/label/track | Global year-over-year trend narratives — `monthly_trends` isn't chunked (see below), so a vague trend question can occasionally land on a coincidentally-named label chunk instead of refusing |
| Growth/trend questions with an explicit year ("grew in 2023") | |
| Out-of-scope questions (weather, jokes, etc.) — refuses cleanly | |

**Why `monthly_trends` isn't in `gold_chunks`**: it's used only to power the dashboard's
cross-country "streams over time" chart (`apps/gold_data/services.py`), not as RAG narrative
material — same reasoning the original `dashboard_summary`/`monthly_trends` exclusion used before
this source's schema changed.

---

## Try these on the chatbot

| Category | Example |
|---|---|
| Basic lookup | How is India performing in music streaming? |
| Basic lookup | How did Brazil perform in 2024? |
| SQL-routed | Which country had the strongest streaming numbers? |
| SQL-routed | Which label has the most streams? |
| SQL-routed | How many artists are in the data? *(kpi_artist, count-only)* |
| SQL-routed | How many tracks are there? |
| Comparison | Compare India and Brazil's streaming performance. |
| Comparison | Compare United States and Mexico's market share. |
| Should refuse cleanly | What is the weather like today? |
| Should refuse cleanly | Tell me a joke. |
| Known limitation | Who is the top artist by streams? *(no artist metrics in this source — degrades to "I don't have data")* |

---

## What we found and fixed

| Problem (found by testing, not code review) | Fix |
|---|---|
| No way to tell a good retrieval from a bad one — an out-of-scope question could score *closer* than a correct answer | Distance-based confidence gate before calling the LLM |
| Comparing two countries sometimes returned all context for one, none for the other | Per-entity scoped retrieval, merged |
| "Which is highest" / "how many" can't be answered from 5 similar chunks | SQL router for MAX/COUNT/AVG/growth questions |
| `country_chunk()` silently dropped two computed fields | Added the fields back, re-embedded just those 672 chunks |
| No index on `embedding` — every query was a full table scan | Built the `ivfflat` index, tuned `probes` for full recall |
| — | Wired up Groq as the LLM, Ollama still works as fallback |
| (post gold-source-migration) "who is the top artist by streams" fell through to unfiltered vector search and answered from a label chunk whose name read like an artist's (e.g. "Martin Arteta") | Artist-keyword hard block before vector retrieval (see "What the chatbot can and can't answer") |
| Vague trend questions ("global streaming trend...") coincidentally matched a label chunk (e.g. a label literally named "Trending Now") | `NO_MATCH_DISTANCE_THRESHOLD` re-measured and tightened 1.10 → 0.95 against the current `gold_chunks`; some coincidental matches (e.g. a query containing "years" matching a label called "17 Earth Years", distance ~0.87) remain a known, documented gap — indistinguishable from a real match by distance alone |

Tested on the same 15 questions before/after every change. **7/15 flipped from wrong to correct, 0 regressions.**

Full details: [`IMPLEMENTATION_LOG.md`](./IMPLEMENTATION_LOG.md) · [`RAG_AUDIT.md`](./RAG_AUDIT.md) · [`RAG_ENGINEERING_AUDIT.md`](./RAG_ENGINEERING_AUDIT.md)

---

## Gold-layer source migration (`group-1-dbda` → `spotify-lake-dev-data`)

The Gold source moved to a different S3 bucket with a materially different schema: no
`artist_performance`, `label_performance`, or `dashboard_summary` tables, and no artist-level
metric columns anywhere in the new source. Every layer that assumed the old schema was rewritten:
`schema.sql`, `scripts/load_gold_to_postgres.py`, `scripts/build_gold_chunks.py`,
`apps/gold_data/models.py` + `services.py`, `apps/chatbot/rag.py`'s table routing. See the
architecture diagram and "Where `gold_chunks` comes from" above for the resulting shape.
`kpi_artist` (country×artist×month presence, no metrics) only supports `COUNT(DISTINCT
artist_uri)` — it's excluded from the RAG chunk build and from superlative/trend SQL routing,
which would otherwise error on the missing `total_streams` column. The dashboard's KPI cards and
"streams over time" chart, which used to read a pre-aggregated global `dashboard_summary`/
`monthly_trends` table, are now computed as cross-country sums grouped by `(year, month)` — an
approximation, since summing per-country `active_artists`/`active_songs` double-counts anyone
active in more than one country that month.

---

## AWS deployment

```
┌────────────────────────────── EC2 (m5.large, us-east-1) ────────────────────────────────┐
│                                                                                             │
│   Internet ──▶ Nginx :80 ──▶ Gunicorn :8000 ──▶ Django ──▶ Postgres 17 + pgvector :5432   │
│                                                       │                                     │
│                                                       └──▶ Groq API (external)              │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

**Setup steps**: launch EC2 → install Postgres 17 + pgvector (PGDG apt repo) → `aws s3 sync` Gold
parquet onto the instance → deploy code via `rsync` → venv + `.env` (Groq key, DB URL) → apply
`schema.sql` → `load_gold_to_postgres.py` → `build_gold_chunks.py` (embeddings) → Gunicorn as a
systemd service → Nginx reverse proxy.

### Full walkthrough

1. **Provisioning** — new key pair, a security group scoped to SSH (22) + Postgres (5432) from
   the deploying machine's own IP only, HTTP (80) open publicly. Ubuntu 22.04 AMI, default VPC/
   subnet. An IAM instance profile was attached after launch (`associate-iam-instance-profile`) so
   the instance could pull from S3 using its own role instead of long-lived credentials.
2. **Base packages** — `python3.12` (+ `-venv`/`-dev`) via the deadsnakes PPA (Ubuntu 22.04 ships
   3.10, Django 6 needs 3.12), `build-essential`/`libpq-dev` (native deps for `psycopg2`), `nginx`,
   `rsync`, `unzip`, then AWS CLI v2 (official installer — not in `apt`).
3. **PostgreSQL 17 + pgvector** — added the official PGDG apt repo (Ubuntu's own repo only ships
   an older Postgres major version) and installed `postgresql-17`, `postgresql-server-dev-17`,
   `postgresql-17-pgvector`. Created a dedicated `streampulse` role + `gold` database, enabled
   `CREATE EXTENSION vector`, applied `schema.sql`.
4. **Data sync + code deploy** — `aws s3 sync s3://spotify-lake-dev-data/gold/` run directly on
   the instance (using its IAM role, no data transits the deploying machine); application code
   pushed via `rsync` (excludes `venv/`, `.env`, `db.sqlite3`, local-only report docs).
5. **App setup** — `venv` + `pip install -r requirements.txt` (+ `gunicorn`, not in
   `requirements.txt`), `.env` with `DJANGO_ALLOWED_HOSTS` set to the instance's public IP,
   `GOLD_DATABASE_URL` pointing at the local `streampulse`/`gold` role, the same `GROQ_API_KEY`
   used locally. `DJANGO_ENV=dev` is used in production here deliberately — there's no domain/TLS
   cert for `prod.py`'s forced `SECURE_SSL_REDIRECT`, so `dev.py`'s plain-HTTP-friendly settings
   are the practical choice for an IP-only demo deployment.
6. **Load Gold data + build RAG chunks** — `scripts/load_gold_to_postgres.py` against the synced
   parquet, then `scripts/build_gold_chunks.py` for the embeddings (see the CPU-credit issue below
   for why this step ended up running locally instead).
7. **Serve it** — Gunicorn bound to `127.0.0.1:8000` as a `systemd` service (`Restart=always`),
   Nginx reverse-proxying `:80` → Gunicorn and serving `/static/` directly from
   `STATIC_ROOT` after `collectstatic`.
8. **Verify** — `curl` from both the instance itself and an external machine to confirm the
   security group and Nginx binding are actually reachable, then exercised the chatbot with one
   question per SQL-router/vector-retrieval/confidence-gate code path before calling it done.

**Issues hit along the way:**

| Issue | Fix |
|---|---|
| Django 6 needs Python 3.12, Ubuntu 22.04 ships 3.10 | Installed 3.12 via deadsnakes PPA |
| `t3.small` (2GB RAM, no swap) OOM-killed `load_gold_to_postgres.py` loading the two largest tables (`kpi_artist` 1.9M rows, `kpi_song` 2.5M rows) into pandas | Added a 4GB swapfile as an immediate fix |
| Resized to `t3.medium` for the embedding step (`build_gold_chunks.py`) — burstable CPU credits still throttled a sustained ~9-minute CPU-bound job to an estimated 3+ hour completion | Resized again to `m5.large` (non-burstable, consistent 2 vCPU) |
| Embedding 408,849 chunks on the server was still slow even on `m5.large` (CPU-only, x86) | Ran `build_gold_chunks.py` locally instead (Apple M1, 8 cores) — 9 minutes vs 1.5+ hours — then `pg_dump`/`pg_restore` just the `gold_chunks` table onto the server |
| Restoring the 750MB `gold_chunks` dump filled the 20GB root EBS volume | Grew the EBS volume to 40GB online (`modify-volume` + `growpart` + `resize2fs`, no downtime) |
| `ivfflat` index built on an empty table (before data load) warned of low recall | Dropped and rebuilt it after loading, with `lists` sized to the real row count |

---

## Running it locally

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set GOLD_DATABASE_URL, and GROQ_API_KEY if you have one
python3 manage.py migrate
python3 manage.py runserver
```

```bash
# rebuild the chunk store from scratch
python3 scripts/load_gold_to_postgres.py
python3 scripts/build_gold_chunks.py

# re-run the 15-question test set
python3 scripts/rag_baseline_probe.py output.json
```

No `GROQ_API_KEY` → falls back to local Ollama (`OLLAMA_URL`, default `http://localhost:11434`, model `llama3.2:3b`).

---

## Project layout

```
apps/
  core/          landing pages
  dashboard/     KPI + chart UI
  gold_data/     real Gold-layer queries for the dashboard
  chatbot/       RAG pipeline + chat UI  →  apps/chatbot/rag.py
  api/           versioned DRF API root
scripts/
  load_gold_to_postgres.py
  build_gold_chunks.py
  rag_baseline_probe.py
schema.sql
```
