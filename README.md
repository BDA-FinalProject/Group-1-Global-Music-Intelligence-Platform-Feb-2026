# StreamPulse — Global Music Intelligence Platform

Django web app built on top of our Bronze/Silver/Gold data pipeline for Spotify streaming analytics. It has a live dashboard and a RAG chatbot that answers questions using the actual Gold-layer data instead of just guessing from the LLM's training data.

CDAC Big Data Engineering group project.

---

## What's in here

- Data pipeline: streaming data aggregated by artist, country and label, landed in **S3** and loaded into **PostgreSQL**.
- **Dashboard**: KPI cards + charts (streams over time, top countries), all pulled live from the Gold tables, nothing hardcoded.
- **RAG chatbot**: ask it things like "How did Kendrick Lamar perform in 2024?" or "Which country had the strongest streaming numbers?" and it answers from the real data, with sources.

---

## Architecture

```
S3 (Gold layer, Parquet)
        │  scripts/load_gold_to_postgres.py
        ▼
PostgreSQL — Gold tables
(artist_performance, country_performance, label_performance,
 dashboard_summary, monthly_trends)
        │
        ├───────────────────────────┐
        ▼                           ▼
  apps/gold_data              scripts/build_gold_chunks.py
  (dashboard KPIs/charts)     (yearly rollup → chunk text → embed)
        │                           │
        ▼                           ▼
  Django dashboard            gold_chunks (pgvector + ivfflat index)
                                     │
                                     ▼
                          apps/chatbot/rag.py
                          embed → route (SQL or vector) → retrieve
                          → confidence check → prompt → LLM (Groq)
                                     │
                                     ▼
                              Django chatbot
```

### Stack

| Layer | Choice |
|---|---|
| Data lake | AWS S3, Parquet |
| DB | PostgreSQL 17 |
| Vector search | pgvector, `ivfflat` index — didn't want to run a separate vector DB for this scale |
| Embeddings | `all-MiniLM-L6-v2`, runs locally, no API cost |
| LLM | Groq (`llama-3.3-70b-versatile`), falls back to local Ollama if no API key is set |
| Backend | Django 6 + DRF (`/api/v1/`) |
| Frontend | Django templates + Chart.js |
| Hosting | AWS EC2 (`t3.small`), Nginx + Gunicorn |

More detail on why we picked what we picked is in [`RAG_ARCHITECTURE.md`](./RAG_ARCHITECTURE.md). Gold layer schema/inventory notes are in [`GOLD_LAYER_REPORT.md`](./GOLD_LAYER_REPORT.md) and [`GOLD_LAYER_LIVE_REPORT.md`](./GOLD_LAYER_LIVE_REPORT.md).

---

## Try these on the chatbot

**Basic lookups**
- How did Kendrick Lamar perform in 2024?
- How is India performing in music streaming?

**Things that need a real SQL answer, not just similar text**
- Which country had the strongest streaming numbers?
- Which artist grew the most in 2023?
- How many countries are covered in the data?
- How many labels are there in total?

**Comparisons**
- Compare India and Brazil's streaming performance.
- Compare United States and Mexico's market share.

**Should get a clean "I don't have data for that" instead of a made-up answer**
- What is the weather like today?
- Tell me a joke.

**Known rough edges** (data quality issues on the label side, and artist-vs-artist comparisons aren't scoped yet):
- Compare Kendrick Lamar and Drake's streaming performance.
- Tell me about Columbia Records.

---

## What we fixed in the RAG pipeline

The chatbot already worked and answered from real data, but we ran it through a bunch of test questions and actually looked at what was being retrieved for each one, not just skimmed the code. Turned up a few real problems:

- The chatbot had no way to tell when it didn't have a good match. An out-of-scope question could score *closer* than a genuinely correct one, so it would just answer anyway instead of saying "I don't know."
- Asking it to compare two countries or artists sometimes returned all its context for one of them and none for the other — one comparison ended up with the model making up numbers for the missing side.
- Questions like "which country is the highest" or "how many labels are there" can't really be answered by pulling the 5 most similar chunks — that's a job for an actual SQL query, not vector search.
- One of the chunk templates was silently missing two fields that were already being computed, so those numbers were unanswerable even though the data existed.
- There was no index on the embedding column, so every search was a full table scan.

Fixes we made:
1. Added a distance threshold — if nothing relevant comes back, it says so instead of guessing.
2. Country comparisons now fetch each country's data separately and merge it, so one doesn't crowd out the other.
3. Added a SQL path for "highest/lowest/most/how many/grew the most" type questions instead of forcing everything through vector search.
4. Fixed the missing fields in the country chunk template.
5. Added the `ivfflat` index that was in the schema but never actually built, and tuned it properly (turns out the default settings hurt accuracy — see `IMPLEMENTATION_LOG.md` for what happened there).
6. Wired up Groq as the LLM provider, with local Ollama still working as a fallback.

We tested this with the same 15 questions before and after each change so we'd actually know if something broke. 7 of the 15 went from a wrong or unhelpful answer to a correct one, and nothing that was already working got worse. Full writeup with before/after answers is in [`IMPLEMENTATION_LOG.md`](./IMPLEMENTATION_LOG.md); the audit that found these issues in the first place is in [`RAG_AUDIT.md`](./RAG_AUDIT.md) and [`RAG_ENGINEERING_AUDIT.md`](./RAG_ENGINEERING_AUDIT.md).

---

## Deployment

Running on an AWS EC2 instance (`t3.small`, Mumbai region) with Postgres 17 + pgvector, Gunicorn and Nginx. Gold data was migrated over with `pg_dump`/`pg_restore` from the dev database and row counts were checked to match exactly after the move.

---

## Running it locally

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set GOLD_DATABASE_URL, and GROQ_API_KEY if you have one
python3 manage.py migrate
python3 manage.py runserver
```

No `GROQ_API_KEY`? It'll use local Ollama instead (`OLLAMA_URL`, default `http://localhost:11434`, model `llama3.2:3b`).

Rebuilding the chunk store from scratch:
```bash
python3 scripts/load_gold_to_postgres.py   # S3 Gold -> Postgres
python3 scripts/build_gold_chunks.py       # Postgres -> embedded gold_chunks
```

Re-running the test questions against the live pipeline:
```bash
python3 scripts/rag_baseline_probe.py output.json
```

---

## Project layout

```
apps/
  core/          landing pages
  dashboard/     KPI + chart UI
  gold_data/     real Gold-layer queries for the dashboard
  chatbot/       RAG pipeline + chat UI (apps/chatbot/rag.py is the core logic)
  api/           versioned DRF API root
scripts/
  load_gold_to_postgres.py   S3 Gold Parquet -> Postgres
  build_gold_chunks.py       Postgres -> yearly chunks -> embeddings -> gold_chunks
  rag_baseline_probe.py      test harness, runs the 15 questions end to end
schema.sql       Gold + gold_chunks table definitions, pgvector index
```
