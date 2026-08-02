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
└─────────────┘     │  ├─ artist_performance │  │  ┌─────────┐  ┌───────────┐ │
                     │  ├─ country_performance│  │  │Dashboard │  │  Chatbot   │ │
                     │  ├─ label_performance  │  │  └─────────┘  └───────────┘ │
                     │  ├─ dashboard_summary  │  └──────────┬──────────────────┘
                     │  ├─ monthly_trends     │             │
                     │  └─ gold_chunks (RAG)  │             ▼
                     └────────────────────────┘      Groq LLM API
                                                    (llama-3.3-70b)
```

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
| Hosting | AWS EC2 `t3.small`, Nginx + Gunicorn |

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

~215,725 chunks total (151,264 artist · 63,789 label · 672 country).

---

## Try these on the chatbot

| Category | Example |
|---|---|
| Basic lookup | How did Kendrick Lamar perform in 2024? |
| Basic lookup | How is India performing in music streaming? |
| SQL-routed | Which country had the strongest streaming numbers? |
| SQL-routed | Which artist grew the most in 2023? |
| SQL-routed | How many countries are covered in the data? |
| SQL-routed | How many labels are there in total? |
| Comparison | Compare India and Brazil's streaming performance. |
| Comparison | Compare United States and Mexico's market share. |
| Should refuse cleanly | What is the weather like today? |
| Should refuse cleanly | Tell me a joke. |
| Known rough edge | Compare Kendrick Lamar and Drake's streaming performance. |
| Known rough edge | Tell me about Columbia Records. |

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

## AWS deployment

```
┌────────────────────────────── EC2 (t3.small, ap-south-1) ───────────────────────────────┐
│                                                                                             │
│   Internet ──▶ Nginx :80 ──▶ Gunicorn :8000 ──▶ Django ──▶ Postgres 17 + pgvector :5432   │
│                                                       │                                     │
│                                                       └──▶ Groq API (external)              │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

**Setup steps**: launch EC2 → install Postgres 17 + pgvector (compiled from source) → `pg_dump`/`pg_restore` Gold data from dev → deploy code via `rsync` → venv + `.env` (Groq key, DB URL) → Gunicorn as a systemd service → Nginx reverse proxy.

**Issues hit along the way:**

| Issue | Fix |
|---|---|
| Django 6 needs Python 3.12, Ubuntu 22.04 ships 3.10 | Installed 3.12 via deadsnakes PPA |
| Ran out of disk installing PyTorch/sentence-transformers | EBS 8GB → 20GB, grew filesystem |
| `t3.micro` ran out of CPU credits mid-setup, instance stopped responding | Resized to `t3.small` |
| Dev Postgres was v17, server shipped an older version | Added official PGDG apt repo, installed Postgres 17 to match |
| `ivfflat` index rebuilds with different clustering each time — dev-tuned `probes` didn't give full recall on the server's rebuild | Re-swept `probes` against the deployed index directly, compared against exact brute-force search |

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
