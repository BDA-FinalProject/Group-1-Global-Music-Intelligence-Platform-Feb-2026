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

## How the RAG pipeline actually works

`apps/chatbot/rag.py` is the whole thing, end to end. When a question comes in from the chat widget, here's what happens to it:

**1. Routing first, before anything expensive runs.** Not every question should go through vector search. A question like "how many labels are there" or "which country had the strongest streaming numbers" has one correct, deterministic answer sitting in the Gold tables — it doesn't need 5 semantically-similar text chunks, it needs `COUNT(DISTINCT ...)` or `ORDER BY total_streams DESC`. So the first thing `get_rag_reply()` does is check the question against a set of trigger keywords (`highest`, `strongest`, `how many`, `grew the most`, etc.). If it matches, the question skips embedding and retrieval entirely and goes straight to a parameterized SQL query against `artist_performance` / `country_performance` / `label_performance`. For a pure count question, that SQL result *is* the answer — no LLM call needed at all. For a superlative or growth question, the SQL result gets formatted into the context and handed to the LLM to phrase into a sentence.

**2. Multi-country comparisons get special handling too.** If the question names two or more real countries (checked against the actual distinct `country_name` values in the data, longest name first so "United States" matches before something shorter would), each country gets its own scoped retrieval call instead of one shared query. This matters because a single top-5 vector search naturally favors whichever entity is semantically closer overall — asking it to compare two countries in one query could quietly return five chunks about one of them and nothing about the other.

**3. Everything else goes through embedding + vector search.** The question gets embedded with the same `all-MiniLM-L6-v2` model used to embed the data, then `classify_query()` checks if it can narrow the search to one table (an exact country name match, or keywords like "label"/"records" for the label table). If it can, the search is scoped to that table's chunks; if not, it searches all ~215K chunks in `gold_chunks` at once. Either way it's a nearest-neighbor search over pgvector using the `<->` (L2 distance) operator, backed by an `ivfflat` index so it doesn't have to scan the whole table every time.

**4. Before handing anything to the LLM, there's a confidence check.** If the question didn't match a known table or entity and even the closest chunk that came back is still far away (distance-wise), the pipeline doesn't bother generating an answer — it just says it doesn't have data for that. This exists because we found that an out-of-scope question could sometimes score *closer* than a real, correct match. Without some kind of check, the system had no way to tell the difference between "found it" and "found five vaguely-related chunks," so it would just confidently answer either way.

**5. The LLM only ever sees the retrieved chunks (or the SQL result) plus the question.** It's told explicitly to answer only from what's in front of it and to say so if the answer isn't there. Right now that's Groq (`llama-3.3-70b-versatile`), but the code checks for `GROQ_API_KEY` at request time and falls back to a local Ollama model if it's not set, so the same pipeline runs either way.

### Where the chunks come from

Before any of the above can happen, the data actually has to be embedded. `scripts/build_gold_chunks.py` takes the Gold tables (which are monthly grain) and rolls them up to one row per entity per year — an artist's 2024, a country's 2024, a label's 2024 — using `sum` for things that are additive across months (total streams), `max` for catalog-size type metrics, and `mean` for anything that's already a rate or percentage. Each of those rows gets turned into a plain-English sentence and embedded. That's where the ~215,725 rows in `gold_chunks` come from.

### What we actually found wrong with it, and fixed

We didn't just read the code — we ran real questions through the live pipeline and looked at exactly what came back for each one. That turned up a few concrete problems, and each one got a specific fix:

- **No way to tell a good retrieval from a bad one.** Fixed with the confidence check described above (item 4). Verified by comparing actual distance scores for a genuinely correct match against an out-of-scope one before deciding where to set the cutoff.
- **Comparisons could lose an entity entirely.** Asking it to compare two countries sometimes returned all five chunks about one of them and none about the other. For countries specifically, this is fixed by the per-entity retrieval in item 2 above. (Artist-vs-artist comparisons don't have this fix yet — there's no equivalent name list for artists to check against, so that's still a known gap.)
- **Aggregate questions had no correct path.** "Which country is highest" or "how many labels exist" can't be answered by finding 5 similar-sounding chunks, only by an actual `MAX()` or `COUNT()`. That's what the SQL routing in item 1 is for.
- **A chunk template was missing two fields.** `country_chunk()` was building its text from most of what gets computed for each country-year, but silently dropped `active_songs` and `catalog_hit_rate` — those questions were unanswerable even though the data existed one line away. Added them in and re-embedded just the country chunks (672 rows, not the full 215K).
- **No index on the embedding column.** Every retrieval was a full sequential scan. The `ivfflat` index was actually already written in `schema.sql`, just commented out and never built. We built it — and then found the default settings for it (`probes`) hurt retrieval accuracy on a rebuilt index, which took some digging to catch and tune properly. Full story on that one is in `IMPLEMENTATION_LOG.md` since it's a good example of why you have to actually test a "performance" change for correctness too, not just speed.

We tested all of this against the same 15 questions before and after every change, not just eyeballing a couple of examples. 7 of the 15 went from a wrong or unhelpful answer to a correct one, and nothing that already worked broke in the process. Full before/after answers are in [`IMPLEMENTATION_LOG.md`](./IMPLEMENTATION_LOG.md); the audit that surfaced these issues in the first place is in [`RAG_AUDIT.md`](./RAG_AUDIT.md) and [`RAG_ENGINEERING_AUDIT.md`](./RAG_ENGINEERING_AUDIT.md).

---

## Deploying it on AWS

The whole thing is live on an EC2 instance in `ap-south-1` (Mumbai). Rough shape of what that involved:

**Instance.** Started on a `t3.micro` to keep costs down, since the LLM calls now go out to Groq instead of running a model locally — that was the whole point of moving off Ollama for deployment, no GPU or heavy local inference needed on the server itself. Ubuntu 22.04, a security group open only on 22 (SSH, locked to our own IP), 80 and 443.

**Database.** Postgres + pgvector needed to be installed and the pgvector extension compiled against it from source, since it's not in Ubuntu's default repos in the version we needed. The Gold data itself was moved over with a straight `pg_dump` on the dev machine and `pg_restore` on the server — dumped ~420MB (mostly the embedding vectors), copied it over, restored it, and checked the row counts matched exactly on both sides before trusting it.

**App.** Code went over with `rsync`. Dependencies installed into a venv, `.env` set up with the Gold database URL and the Groq key, static files collected, and the app wired up behind Gunicorn (as a systemd service so it restarts on its own) with Nginx in front as the reverse proxy.

**What actually went wrong, and how it got sorted out:**
- Django 6 needs Python 3.12; Ubuntu 22.04 only ships 3.10 by default. Installed 3.12 via the deadsnakes PPA and rebuilt the venv with it.
- Ran out of disk space installing dependencies — `sentence-transformers` pulls in PyTorch, which is not small. Bumped the EBS volume from 8GB to 20GB and grew the filesystem to match.
- The `t3.micro` ran out of CPU credit balance during setup (compiling pgvector plus installing everything at once is a lot for a burstable instance with only 1GB of RAM) and the box became unresponsive — even SSH stopped answering. Had to stop it, resize it up to `t3.small`, and start it back up.
- Postgres itself needed to match the dev machine's major version (17) for the dump/restore to work cleanly — the version that ships by default on Ubuntu is older, so that meant adding the official PostgreSQL apt repo and installing 17 specifically, then rebuilding pgvector again against that version.
- The `ivfflat` index gets rebuilt fresh on the server when the schema is restored, and because its clustering is randomized at build time, the `probes` value that worked well in dev didn't give full recall on the server's rebuild of the same index. Caught this by comparing what the index actually returned against an exact brute-force search on a few real questions, and re-tuned `probes` specifically against the deployed index rather than assuming the dev value would carry over.

None of these were huge, but they're exactly the kind of thing that only shows up once you actually deploy something instead of just running it locally.

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
