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
