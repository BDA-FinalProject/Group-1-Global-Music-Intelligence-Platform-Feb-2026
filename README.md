# StreamPulse — Global Music Intelligence Platform

A Django web application built on top of a medallion-architecture (Bronze → Silver → **Gold**) data pipeline for Spotify streaming analytics, featuring a live KPI dashboard and a Retrieval-Augmented Generation (RAG) chatbot that answers natural-language questions grounded in the real Gold-layer data.

Built as a CDAC Big Data Engineering group project.

---

## What this project does

- Ingests and aggregates streaming data (artist, country, and label performance) through a Bronze/Silver/Gold pipeline, landed in **AWS S3** and loaded into **PostgreSQL**.
- Serves a **dashboard** with live KPI cards and charts (streams over time, top countries) sourced directly from the Gold layer — no dummy/hardcoded data.
- Serves a **RAG chatbot** that answers questions like *"How did Kendrick Lamar perform in 2024?"*, *"Which country had the strongest streaming numbers?"*, or *"How many labels are there in total?"* — grounded in the actual Gold data, not the LLM's training knowledge.

---

## Architecture

```
S3 (Gold layer, Hive-partitioned Parquet)
        │  scripts/load_gold_to_postgres.py  (pyarrow.dataset, truncate+reload)
        ▼
PostgreSQL — 5 Gold tables
(artist_performance, country_performance, label_performance,
 dashboard_summary, monthly_trends)
        │
        ├──────────────────────────────┐
        │                               │
        ▼                               ▼
apps/gold_data (dashboard)     scripts/build_gold_chunks.py
  real KPIs/charts via ORM       (yearly rollup → text chunk per
                                   entity-year → MiniLM embedding)
        │                               │
        ▼                               ▼
   Django dashboard              gold_chunks (pgvector, ivfflat index)
   /dashboard/                          │
                                         ▼
                              apps/chatbot/rag.py — RAG pipeline:
                              embed → route (SQL vs. vector) → retrieve
                              → confidence gate → prompt → LLM (Groq)
                                         │
                                         ▼
                                Django chatbot  /chatbot/
```

### Tech stack

| Layer | Choice |
|---|---|
| Data lake | AWS S3, Hive-partitioned Parquet |
| Warehouse | PostgreSQL 17 |
| Vector search | pgvector (`ivfflat` index) — no separate vector DB needed |
| Embeddings | `all-MiniLM-L6-v2` (local, free, 384-dim) |
| LLM | Groq (`llama-3.3-70b-versatile`), local Ollama as fallback if no API key is set |
| Backend | Django 6 + Django REST Framework, versioned API (`/api/v1/`) |
| Frontend | Django templates, Chart.js |
| Deployment | AWS EC2 (`t3.small`), Nginx + Gunicorn |

Full technology-choice rationale (why pgvector over a dedicated vector DB, why MiniLM over a hosted embedding API, chunking-strategy tradeoffs) is in [`RAG_ARCHITECTURE.md`](./RAG_ARCHITECTURE.md). Gold-layer schema/inventory is in [`GOLD_LAYER_REPORT.md`](./GOLD_LAYER_REPORT.md) and [`GOLD_LAYER_LIVE_REPORT.md`](./GOLD_LAYER_LIVE_REPORT.md).

---

## What we improved (this round of work)

The chatbot was already retrieving and answering from real data, but a full audit of the live system — actual `EXPLAIN ANALYZE` query plans, actual retrieved chunks, actual distance scores, actual LLM outputs, not just code review — surfaced concrete, evidenced problems. All findings and the fixes below are fully documented with file:line citations and before/after evidence in **[`RAG_AUDIT.md`](./RAG_AUDIT.md)**, **[`RAG_ENGINEERING_AUDIT.md`](./RAG_ENGINEERING_AUDIT.md)**, **[`RAG_IMPLEMENTATION_ROADMAP.md`](./RAG_IMPLEMENTATION_ROADMAP.md)**, and **[`IMPLEMENTATION_LOG.md`](./IMPLEMENTATION_LOG.md)**.

### Problems found (with live evidence)
- **No confidence signal**: out-of-scope questions had *lower* (more "confident") vector-distance scores than genuinely correct answers — the system had no way to know when it didn't know.
- **Comparison questions silently dropped an entity**: "Compare Kendrick Lamar and Drake" retrieved 5 Kendrick chunks and 0 Drake chunks; the LLM then fabricated fake statistics and a fake citation for Drake.
- **No path for aggregate questions**: "Which country had the strongest streaming numbers?" and "How many labels are there?" have no correct answer via top-k vector similarity — it can't compute a `MAX()` or `COUNT()`.
- **A real chunk-generation bug**: `active_songs` and `catalog_hit_rate` were computed for every country but never written into the chunk text, making them permanently unanswerable.
- **No vector index**: every retrieval query was a full sequential scan (~250–375ms) — the `ivfflat` index was written in `schema.sql` but commented out and never built.

### Fixes implemented (P0)
1. **Confidence gate** — when retrieval finds no entity/keyword match and the closest chunk is still far away, the chatbot returns a clean "I don't have data to answer that" instead of guessing.
2. **Per-entity scoped retrieval** — comparison questions naming 2+ countries now retrieve each country's chunks separately and merge them, so one entity can no longer crowd out another.
3. **SQL router** — questions shaped like MAX/MIN/COUNT/AVG/year-over-year growth ("strongest", "how many", "grew the most") are routed to a deterministic, parameterized SQL query against the Gold tables instead of vector search.
4. **Chunk fix** — `country_chunk()` now includes `active_songs` and `catalog_hit_rate`.
5. **Vector index** — built the `ivfflat` index with the correct opclass (`vector_l2_ops`, matching the actual query operator) and tuned `probes` for full retrieval recall.
6. **Groq integration** — the chatbot now calls Groq (`llama-3.3-70b-versatile`) when `GROQ_API_KEY` is set, falling back to local Ollama otherwise — no code change needed to switch providers, just an environment variable.

### Verification
Every change was checked against a fixed 15-question test set, run through the real pipeline **before and after** each change (`baseline_before.json`, `baseline_after.json`, `baseline_groq.json`) — not just spot-checked. **7 of 15 test questions flipped from a wrong/unhelpful answer to a correct one, with zero regressions.** One real regression *was* found mid-implementation (the vector index's default settings briefly broke a previously-correct answer) — it's documented in full in `IMPLEMENTATION_LOG.md`, including how it was diagnosed and fixed.

---

## Deployment

Live-deployed on **AWS EC2** (`t3.small`, `ap-south-1`) running PostgreSQL 17 + pgvector, Gunicorn, and Nginx. The Gold database was migrated from local development via `pg_dump`/`pg_restore`, with row counts verified to match exactly post-migration.

---

## Running locally

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GOLD_DATABASE_URL and (optionally) GROQ_API_KEY
python3 manage.py migrate
python3 manage.py runserver
```

Without `GROQ_API_KEY` set, the chatbot falls back to a local Ollama server (`OLLAMA_URL`, default `http://localhost:11434`, model `llama3.2:3b`).

To rebuild the RAG chunk store from the Gold tables:
```bash
python3 scripts/load_gold_to_postgres.py   # Gold Parquet -> Postgres
python3 scripts/build_gold_chunks.py       # Postgres -> embedded gold_chunks
```

To re-run the 15-question retrieval/answer test set against the live pipeline:
```bash
python3 scripts/rag_baseline_probe.py output.json
```

---

## Project structure

```
apps/
  core/          landing pages
  dashboard/     KPI + chart UI
  gold_data/     real Gold-layer queries backing the dashboard
  chatbot/       RAG pipeline + chat UI  (apps/chatbot/rag.py is the core logic)
  api/           versioned DRF API root
scripts/
  load_gold_to_postgres.py   S3 Gold Parquet -> Postgres
  build_gold_chunks.py       Postgres -> yearly chunks -> embeddings -> gold_chunks
  rag_baseline_probe.py      15-question retrieval/answer test harness
schema.sql       Gold + gold_chunks table definitions, pgvector index
```
