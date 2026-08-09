# StreamPulse — Global Music Intelligence Platform

Django app: Gold-layer Spotify analytics dashboard + a RAG chatbot that answers questions from the real data.

CDAC Big Data Engineering group project.

---

## System architecture

```
┌──────────────┐     ┌──────────────────┐     ┌───────────────────────────┐
│   AWS S3      │────▶│  PostgreSQL 17     │────▶│   Django (EC2, Nginx +     │
│  Gold layer   │     │  + pgvector        │     │   Gunicorn)                 │
│  (Parquet)    │     │                    │     │                              │
└──────────────┘     │  ├─ country_performance│  │  ┌─────────┐  ┌───────────┐ │
       ▲              │  ├─ kpi_artist         │  │  │Dashboard │  │  Chatbot   │ │
       │              │  ├─ kpi_song           │  │  └─────────┘  └─────┬─────┘ │
┌──────┴──────┐       │  ├─ label_performance_ │  └────────────────────┼───────┘
│   AWS S3     │       │  │   enhanced          │                       │
│  Silver layer│       │  ├─ monthly_trends     │             ┌─────────┴─────────┐
│ (song_charts)│       │  ├─ artist_performance │             │  Redis (response     │
└─────────────┘       │  ├─ track_catalog      │             │  cache + per-provider │
                       │  └─ gold_chunks (RAG)  │             │  rate-limit tracking) │
                       └────────────────────────┘             └─────────┬─────────┘
                                                                          ▼
                                                        Gemini → Groq → local Ollama
                                                        (automatic fallback chain)
```

Source: `s3://spotify-lake-dev-data/gold/` — country/song/label/monthly-trend tables, all
country-grain. `kpi_artist` is a country×artist×month presence table with no metric columns (no
artist-level streams in the original Gold source), so on its own it's only useful for
entity-count SQL queries. `artist_performance` and `track_catalog` fill that gap — they're built
separately, from the **Silver** layer (`s3://spotify-lake-dev-data/silver/song_charts/`), which
has real per-(country, track, day) streams plus artist name/URI (something Gold's `kpi_artist`/
`kpi_song` never had), then landed in Gold as first-class tables so they flow through the same
pipeline as the rest — see [`scripts/build_artist_gold.py`](./scripts/build_artist_gold.py).

```
scripts/load_gold_to_postgres.py   S3 Parquet ──▶ Postgres Gold tables
scripts/build_artist_gold.py       S3 Silver ──▶ artist_performance / track_catalog Parquet ──▶ S3 Gold
scripts/build_gold_chunks.py       Gold tables ──▶ yearly chunks ──▶ MiniLM embeddings ──▶ gold_chunks
```

### Stack

| Layer | Choice |
|---|---|
| Data lake | AWS S3, Parquet |
| DB | PostgreSQL 17 |
| Vector search | pgvector, `ivfflat` index |
| Embeddings | `all-MiniLM-L6-v2` (local) |
| LLM | Gemini `gemini-flash-latest` (falls back to Groq `llama-3.3-70b-versatile`, then local Ollama) |
| Backend | Django 6 + DRF |
| Hosting | AWS EC2 `m5.large`, Nginx + Gunicorn |

More detail: [`docs/RAG_ARCHITECTURE.md`](./docs/RAG_ARCHITECTURE.md) · [`docs/GOLD_LAYER_REPORT.md`](./docs/GOLD_LAYER_REPORT.md) · [`docs/GOLD_LAYER_LIVE_REPORT.md`](./docs/GOLD_LAYER_LIVE_REPORT.md)

---

## RAG pipeline — request flow

```
                              User question
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │  Redis: cached reply for this    │
                    │  (question, history) hash?        │
                    └───────┬─────────────────┬───────┘
                        yes │                 │ no
                            ▼                 ▼
                    Cached answer   ┌───────────────────────────────┐
                    (no LLM call)   │  History present AND question    │
                                    │  looks like a follow-up?          │
                                    │  ("what about X?", "which grew    │
                                    │   faster?", pronouns, ...)        │
                                    └───────┬─────────────────┬───────┘
                                        yes │                 │ no
                                            ▼                 │
                              Rewrite into a standalone        │
                              question — deterministic          │
                              substitution first (never drops   │
                              the entity name), falls back to   │
                              an LLM call only if that doesn't   │
                              apply                              │
                                            │                    │
                                            └─────────┬──────────┘
                                                      ▼
                                    ┌───────────────────────────────┐
                                    │  Small talk? ("hi", "thanks",    │
                                    │  "what can you do")               │
                                    └───────┬─────────────────┬───────┘
                                        yes │                 │ no
                                            ▼                 ▼
                                    Warm reply      ┌───────────────────────────────┐
                                    (no retrieval)   │  SQL router — count /            │
                                                      │  sum_streams / count_hits /       │
                                                      │  trend / superlative keyword?     │
                                                      │  (named country/artist scopes      │
                                                      │   the SQL filter when present;     │
                                                      │   no filter = global result)       │
                                                      └───────┬─────────────────┬───────┘
                                                          yes │                 │ no
                                                              ▼                 ▼
                                          Deterministic SQL result   ┌───────────────────────────────┐
                                          → reply (count/sum/hits     │  Named entity match — real       │
                                          skip the LLM entirely;       │  country or artist name(s) in     │
                                          trend/superlative still      │  the question? (exact match,      │
                                          phrase the answer via LLM)   │  fuzzy typo-tolerant fallback)     │
                                                                        └───────┬─────────────────┬───────┘
                                                                            yes │                 │ no
                                                                                ▼                 ▼
                                                                  Entity-scoped retrieval   classify_query() —
                                                                  (one query per named       keyword/fuzzy table
                                                                  entity, merged for          guess, or no filter
                                                                  comparisons)                        │
                                                                                │                      │
                                                                                └──────────┬───────────┘
                                                                                           ▼
                                                                          ┌───────────────────────────────┐
                                                                          │  Hybrid retrieval: vector          │
                                                                          │  search (pgvector) + full-text     │
                                                                          │  search, merged via Reciprocal      │
                                                                          │  Rank Fusion → cross-encoder        │
                                                                          │  rerank → top 5 chunks               │
                                                                          └──────────────────┬───────────────┘
                                                                                             ▼
                                                                          ┌───────────────────────────────┐
                                                                          │  Confidence gate — only when        │
                                                                          │  the match wasn't a confident        │
                                                                          │  exact one (no entity/keyword         │
                                                                          │  match, or a fuzzy one): is the       │
                                                                          │  closest chunk still too far?         │
                                                                          └───────┬─────────────────┬───────┘
                                                                              yes │                 │ no
                                                                                  ▼                 │
                                                                        "I don't have data           │
                                                                         to answer that"              │
                                                                        (no LLM call)                  │
                                                                                                        │
                    ┌───────────────────────────────────────────────────────────────────────────────┴───┐
                    ▼
        build_prompt(retrieved context + recent conversation history)
                    │
                    ▼
        Gemini → Groq → local Ollama (automatic fallback; each provider's
        usage is budget-checked against Redis before it's called)
                    │
                    ▼
                 Answer
                    │
                    ▼
        Cache the reply in Redis, keyed on (question, history)
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

~560,359 chunks total (344,323 track · 151,510 artist · 63,864 label · 662 country).

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
| `artist_performance` | `year=YYYY/` (month is a column) | country × artist × month | `year, month, year_month, country_name, artist_uri, artist_name, total_streams, track_count, hit_track_count, best_rank` | 1,894,035 |
| `track_catalog` | unpartitioned | one row per track | `uri, track_name` — lookup only, no metrics | 242,572 |
| `gold_chunks` | — (Postgres-only, RAG store) | entity × year | `chunk_id, source_table, source_key, chunk_text, embedding vector(384)` | 560,359 |

**Why `kpi_artist`/`kpi_song` alone couldn't answer "how much did artist X stream"**: `kpi_artist`
is a pure presence table (which artist appeared in which country, in which month) with zero
numeric columns; `kpi_song` has real streaming numbers but only at the *track* level, with no
artist↔track mapping (`kpi_artist.artist_uri` and `kpi_song.uri` were checked directly against
each other: zero overlap). That link doesn't exist anywhere in the original Gold source.

**Where `artist_performance`/`track_catalog` come from instead**: the **Silver** layer
(`s3://spotify-lake-dev-data/silver/song_charts/`, ~47M day-level rows) has exactly what Gold was
missing — real `streams` per `(country, track, day)`, plus `artist_names`/`artist_uris` (pipe
`|`-delimited for collabs) and the real `track_name`. `scripts/build_artist_gold.py` explodes the
collab-delimited columns (one row per credited artist — a collab track's streams are attributed
in *full* to each artist, not split) and aggregates down to `(country, artist, month)`, processing
one Silver month-file at a time to stay within a laptop's RAM (47M raw rows is too much for one
pandas DataFrame — the aggregated result per file is much smaller and is all that's kept across
files). One edge case handled explicitly: a small number of rows have an artist name that itself
contains a literal `|` (e.g. a bilingual name like "Nizr | نايزر"), which would otherwise be
mis-split as two artists — detected by comparing the `artist_names`/`artist_uris` split counts per
row and falling back to the whole name when they disagree.

---

## What the chatbot can and can't answer

The RAG pipeline (`apps/chatbot/rag.py`, `get_rag_reply()`) routes every question through, in order:

1. **SQL router** (`detect_sql_intent()`) — deterministic answers for count/superlative/growth
   questions, computed straight from Postgres, no LLM guessing involved for the number itself.
   `artist_performance` is a full entry here (not count-only) — real metrics mean artist
   count/superlative/trend all work through the same generic code path as country/label/track.
2. **Multi-country comparison** — 2+ real country names in one question get separate, merged
   retrievals so one country can't crowd the other out of a shared top-k.
3. **Vector retrieval + confidence gate** — embeds the question, searches `gold_chunks` via
   pgvector, and refuses to answer (rather than guess) if no table/keyword matched *and* the
   closest chunk is still farther than `NO_MATCH_DISTANCE_THRESHOLD` (0.95).

| Can answer | Can't answer (and why) |
|---|---|
| Country lookups/comparisons (`country_performance`) | Country-scoped label questions ("top label **in India**") — label chunks are global totals, not per-country |
| Label lookups (`label_performance_enhanced`, global-aggregated across countries) | `catalog_hit_rate` — this column existed in the old source, doesn't exist in the new one |
| Track lookups (`kpi_song` + `track_catalog`, real track names when available, raw URI fallback otherwise) | Global year-over-year trend narratives — `monthly_trends` isn't chunked (see below), so a vague trend question can occasionally land on a coincidentally-named label chunk instead of refusing |
| **Artist lookups/counts/superlatives/trends** (`artist_performance`, built from Silver — see "Gold-layer tables" above) | "How did \[artist name\] perform" phrased *without* a trigger keyword ("artist", "singer", etc.) — `classify_query()` only does exact-name matching for **countries**, not artists (59,776 of them), so it can fall through to an unfiltered search and retrieve individual track chunks instead of the artist's own yearly rollup. Still answers with real data, just not always the ideal chunk. |
| Counts: artists, labels, tracks, countries (`COUNT(DISTINCT ...)`) | |
| Superlatives: highest/lowest streams by country/label/track/**artist** | |
| Growth/trend questions with an explicit year ("grew in 2023"), including by artist | |
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
| SQL-routed | Who is the top artist by streams? |
| SQL-routed | Which artist grew the most in 2023? |
| SQL-routed | How many artists are in the data? |
| SQL-routed | How many tracks are there? |
| Comparison | Compare India and Brazil's streaming performance. |
| Comparison | Compare United States and Mexico's market share. |
| Should refuse cleanly | What is the weather like today? |
| Should refuse cleanly | Tell me a joke. |
| Known rough edge | How did Taylor Swift perform in 2025? *(no "artist" keyword to route on — answers from individual track chunks with real numbers, not the artist's own yearly rollup; see "What the chatbot can and can't answer")* |

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
| Vague trend questions ("global streaming trend...") coincidentally matched a label chunk (e.g. a label literally named "Trending Now") | `NO_MATCH_DISTANCE_THRESHOLD` re-measured and tightened 1.10 → 0.95 against the current `gold_chunks`; some coincidental matches (e.g. a query containing "years" matching a label called "17 Earth Years", distance ~0.87) remain a known, documented gap — indistinguishable from a real match by distance alone |
| Gold source had no artist-level metrics at all — "who is the top artist by streams" landed on unrelated label chunks and gave misleading answers (temporarily hard-blocked to an honest refusal instead) | Built real `artist_performance`/`track_catalog` tables from the **Silver** layer (which has the artist↔streams link Gold never had — see "Gold-layer tables"), removed the hard block, wired the new table into the SQL router and chunk builder like any other entity |
| A comparison question ("which country grew fastest, India or Brazil?") silently returned a global top-N answer, ignoring the named entities entirely | Trend/superlative/`sum_streams` SQL intents now check for named countries/artists and add an `= ANY(...)` filter when present; unfiltered behavior is unchanged when no entity is named |
| "Between 2023 and 2024" computed growth for the wrong year pair (treated the first-mentioned year as the target, not necessarily the later one) | Trend intent now uses `max()`/`min()` of the two mentioned years instead of assuming order |
| A fuzzy (non-exact) entity match could still bypass the confidence gate, so a typo/coincidental match (e.g. "today" fuzzy-matching an unrelated artist literally named "TOODAY") produced a confidently wrong answer instead of an honest refusal | `classify_query()` now reports whether a match was exact or fuzzy; the confidence gate applies whenever it's not a confident exact match |
| An exact-substring entity check let a short artist name match inside an unrelated word (e.g. an artist named "Tream" matching inside "streams") | Switched entity-name matching to word-boundary regex everywhere, same approach already used for country aliases |
| The LLM-based follow-up condenser occasionally dropped or corrupted the named entity ("What about Brazil?" was rewritten into a vague "a particular country", or a bare "which grew faster?" hallucinated an unrelated real artist as the answer) | Added two deterministic (non-LLM) rewrite paths for the common "What about X?" and bare-comparison shapes — the entity name is copied verbatim from the question/history, never regenerated — falling back to the LLM condenser only for shapes those don't cover |
| Retrieval was vector-similarity only — an exact keyword/name hit could be outranked by a semantically-similar-but-wrong chunk | Added full-text search (Postgres `tsvector`/GIN) alongside vector search, merged via Reciprocal Rank Fusion, then a cross-encoder reranking pass over the merged candidates |

Tested on the same 15 questions before/after every change. **7/15 flipped from wrong to correct, 0 regressions.** (Later fixes above were verified against their own live multi-turn regression scenarios rather than re-running that original 15-question set.)

Full details: [`docs/IMPLEMENTATION_LOG.md`](./docs/IMPLEMENTATION_LOG.md) · [`docs/RAG_AUDIT.md`](./docs/RAG_AUDIT.md) · [`docs/RAG_ENGINEERING_AUDIT.md`](./docs/RAG_ENGINEERING_AUDIT.md)

---

## AWS deployment

```
┌────────────────────────────── EC2 (m5.large, us-east-1) ────────────────────────────────┐
│                                                                                             │
│   Internet ──▶ Nginx :80 ──▶ Gunicorn :8000 ──▶ Django ──▶ Postgres 17 + pgvector :5432   │
│                                                       │                                     │
│                                                       ├──▶ Redis (local, cache + rate-limit) │
│                                                       └──▶ Gemini / Groq / Ollama (LLM)      │
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
| Adding `artist_performance`/`track_catalog` meant re-embedding 560,359 chunks (up from 408,849) — same local-vs-server tradeoff as before, plus the second local run's `executemany()` insert took noticeably longer than the row-count increase alone would suggest | Ran locally again (embedding: 12.5 min); redeployed via a **full** `pg_dump`/`pg_restore` of the whole local `gold` database this time (not just `gold_chunks`), since the two new tables also needed to reach the server |
| Restoring the larger (1.23GB) full-DB dump needed disk headroom again | EBS was already grown to 40GB from the prior round — confirmed free space before restoring rather than re-growing blind |

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
# optional: rebuild artist_performance/track_catalog from Silver first
# (aws s3 sync s3://spotify-lake-dev-data/silver/song_charts/ .silver_local/)
python3 scripts/build_artist_gold.py --dry-run   # sanity-check on 1 file first
python3 scripts/build_artist_gold.py             # full run, ~113 Silver files
# then aws s3 sync the output up to s3://spotify-lake-dev-data/gold/{artist_performance,track_catalog}/

# rebuild the chunk store from scratch
python3 scripts/load_gold_to_postgres.py
python3 scripts/build_gold_chunks.py

# re-run the 15-question test set
python3 scripts/rag_baseline_probe.py output.json
```

Provider priority: `GEMINI_API_KEY` set → Gemini; else `GROQ_API_KEY` set → Groq; else local Ollama (`OLLAMA_URL`, default `http://localhost:11434`, model `llama3.2:3b`). Gemini was added after Groq's free-tier 100K-tokens/day cap was repeatedly exhausted during testing — see `.env.example` for the `gemini-flash-latest` note about its "thinking" tokens needing a higher `max_tokens` budget.

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
  build_artist_gold.py      Silver -> artist_performance/track_catalog
  rag_baseline_probe.py
schema.sql
```
