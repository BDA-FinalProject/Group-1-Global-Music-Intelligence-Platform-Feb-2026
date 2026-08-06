"""
RAG pipeline: embed the question, retrieve nearest gold_chunks via pgvector,
assemble a grounded prompt, generate an answer via an LLM. Uses Groq
(GROQ_API_KEY env var) when set, otherwise falls back to a local Ollama
model — see _call_llm() for the provider switch, get_rag_reply() for the
overall pipeline.
"""
import os
import re

import requests
from django.db import connections

OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'llama3.2:3b')

# If GROQ_API_KEY is set, _call_llm() uses Groq's OpenAI-compatible chat
# endpoint instead of the local Ollama server — no other code path changes.
# Unset/empty GROQ_API_KEY (the default) keeps using local Ollama, so this
# is purely additive for local dev.
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_MODEL = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')
GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'

# Named constant, not inline, so the request target swaps without touching
# call sites — deterministic output (temperature=0) is used throughout
# since every answer here is meant to summarize retrieved facts/SQL
# results, not generate creative text. num_ctx is Ollama-specific (Groq
# manages its own context window) and is only applied in the Ollama path.
GENERATION_OPTIONS = {'temperature': 0, 'num_ctx': 8192}

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model


def embed_query(text):
    return _get_model().encode([text])[0].tolist()


# Order matters: a question can contain more than one table's keywords at
# once (e.g. "which artist has the most tracks" has both "artist" and
# "tracks"), and the first dict entry whose keyword appears wins. kpi_song
# ("song"/"track") is checked LAST because those are the most generic,
# weakest signal here — "artist"/"country"/"label" are more specific and
# should win when a question mentions both.
_TABLE_KEYWORDS = {
    'country_performance': ['country', 'countries', 'market', 'nation'],
    'artist_performance': ['artist', 'artists', 'singer', 'singers', 'musician', 'musicians'],
    'label_performance_enhanced': ['label', 'records', 'recordings'],
    'kpi_song': ['song', 'track', 'songs', 'tracks'],
}

_country_names = None

# Common abbreviations/aliases for country names that appear verbatim in
# country_performance — a stakeholder asking "How is the US doing?" is a
# far more natural phrasing than the full country name, and without this
# the question falls through to unfiltered vector search entirely (see
# README's "known rough edges"). Matched via regex word boundaries, not
# plain substring, since short tokens like "US"/"UK" would otherwise match
# inside unrelated words (e.g. "US" inside "bonus").
_COUNTRY_ALIASES = {
    'us': 'United States',
    'usa': 'United States',
    'u.s.': 'United States',
    'u.s.a.': 'United States',
    'uk': 'United Kingdom',
    'u.k.': 'United Kingdom',
    'uae': 'United Arab Emirates',
}


def _get_country_names():
    """Cached list of real country names from country_performance, longest
    first so a multi-word name (e.g. "United States") matches before a
    shorter unrelated substring would."""
    global _country_names
    if _country_names is None:
        with connections['gold'].cursor() as cur:
            cur.execute("SELECT DISTINCT country_name FROM country_performance")
            names = [r[0] for r in cur.fetchall()]
        _country_names = sorted(names, key=len, reverse=True)
    return _country_names


def _alias_countries(lowered_question):
    """Real country names implied by an abbreviation/alias in the question
    (e.g. "US" -> "United States"), matched on word boundaries so short
    tokens don't match inside unrelated words. Returns real country_name
    values, not the aliases themselves, so callers never need to know
    aliases exist."""
    found = []
    for alias, real_name in _COUNTRY_ALIASES.items():
        if re.search(r'\b' + re.escape(alias) + r'\b', lowered_question):
            found.append(real_name)
    return found


_artist_catalog = None


def _get_artist_catalog():
    """Cached (artist_name, artist_uri) pairs from artist_performance,
    longest name first. gold_chunks' source_key for artist_performance is
    keyed on artist_uri (not name — see build_gold_chunks.py), so
    name-based routing needs the uri to actually filter chunks by; names
    aren't unique (e.g. 8 different artist_uris are all named "Kali" in
    this data) so each name resolves to whichever uri has the most total
    streams — the most likely real match for a bare-name question.

    Names under 5 characters are excluded entirely — 5,782 artist names in
    this data are <=4 chars (many are bare single letters, e.g. "E", "F",
    "T"), which would match as a substring inside huge numbers of unrelated
    questions. This trades a small amount of recall (short-named artists
    never get exact-match routing, only generic keyword/vector fallback)
    for not hijacking routing on ordinary text."""
    global _artist_catalog
    if _artist_catalog is None:
        with connections['gold'].cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (artist_name) artist_name, artist_uri
                FROM (
                    SELECT artist_name, artist_uri, SUM(total_streams) AS total
                    FROM artist_performance
                    WHERE artist_name IS NOT NULL AND length(artist_name) >= 5
                    GROUP BY artist_name, artist_uri
                ) ranked
                ORDER BY artist_name, total DESC
                """
            )
            pairs = cur.fetchall()
        _artist_catalog = sorted(pairs, key=lambda p: len(p[0]), reverse=True)
    return _artist_catalog


def classify_query(question):
    """Route the question to a source_table, so a small table (e.g.
    country_performance) isn't drowned out by a much larger one (e.g.
    kpi_song) in nearest-neighbor search.

    Checks real country and artist names first (e.g. "India", "Taylor
    Swift") since those are unambiguous signals a generic keyword search
    would miss — e.g. "How did Taylor Swift perform in 2025?" has no
    "artist"/"singer" keyword at all otherwise. Falls back to generic
    keywords, then to no filter (search all tables).
    """
    lowered = question.lower()

    for name in _get_country_names():
        if name.lower() in lowered:
            return 'country_performance'
    if _alias_countries(lowered):
        return 'country_performance'

    for name, _uri in _get_artist_catalog():
        if name.lower() in lowered:
            return 'artist_performance'

    for table, keywords in _TABLE_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return table
    return None


def detect_countries(question):
    """Returns every real country name mentioned in the question (including
    via an alias like "US" -> "United States"), longest full-name match
    first (reuses the same name list/ordering as classify_query()), alias
    matches appended after. Used only to detect multi-country comparison
    questions ("Compare India and Brazil", "Compare US and India") —
    classify_query() itself still returns a single table."""
    lowered = question.lower()
    found = []
    for name in _get_country_names():
        if name.lower() in lowered:
            found.append(name)
    for name in _alias_countries(lowered):
        if name not in found:
            found.append(name)
    return found


def detect_artists(question):
    """Same idea as detect_countries(), for artist_performance's
    artist_name (see _get_artist_catalog() for why short names are
    excluded and how name collisions are resolved). Used for multi-artist
    comparison ("Compare Bad Bunny and Drake") and single-artist
    exact-chunk routing. Returns (name, artist_uri) pairs — gold_chunks'
    source_key for artist_performance is keyed on artist_uri, not name, so
    callers need the uri to actually filter chunks."""
    lowered = question.lower()
    found = []
    for name, uri in _get_artist_catalog():
        if name.lower() in lowered:
            found.append((name, uri))
    return found


# ivfflat (schema.sql, idx_gold_chunks_embedding) is an APPROXIMATE nearest-
# neighbor index — pgvector's default ivfflat.probes=1 only searches 1 of
# the index's 216 lists, which measurably hurt recall once the index went
# live: a live regression check (single-entity "How did Kendrick Lamar
# perform in 2024?", previously correct in baseline_before.json) came back
# with 0/5 correct chunks at the default probes=1 (top result was an
# unrelated "Lamar Entertainment" label chunk).
#
# ivfflat's list clustering is randomized at CREATE INDEX time, so the
# right probes value is NOT portable across deployments/rebuilds — a probes
# value tuned against one CREATE INDEX run does not necessarily hit the
# same recall against a different run's clusters (confirmed: probes=8 (dev)
# and probes=32 (first AWS rebuild) both still missed the correct top-5 on
# an unfiltered 215K-row search on a second AWS deployment; compared
# against an exact/brute-force search — which did return all 5 correct
# chunks — and swept probes=32/60/100/150/216 directly against the live
# index: probes=60 was the first value to reach 5/5 correct, at ~1s per
# unfiltered query, and higher probes added query time without any further
# recall gain up to the exhaustive probes=216 case. 60 is used here as a
# recall-first choice — this is deployment-specific data, not a universal
# constant, so if the index is ever rebuilt again, re-sweep rather than
# assuming this value still holds.
IVFFLAT_PROBES = 60


def _set_probes(cur):
    cur.execute('SELECT 1')  # ensures the vector extension is loaded in this
                              # backend before SET, which a truly first-statement
                              # SET can otherwise reject as an unrecognized GUC
    cur.execute('SET ivfflat.probes = %s', [IVFFLAT_PROBES])


def retrieve_chunks(query_embedding, source_table=None, top_k=5):
    """Nearest-neighbor search against gold_chunks via pgvector's <-> operator.
    When source_table is given, restricts the search to that table."""
    with connections['gold'].cursor() as cur:
        _set_probes(cur)
        if source_table:
            cur.execute(
                """
                SELECT source_table, source_key, chunk_text
                FROM gold_chunks
                WHERE source_table = %s
                ORDER BY embedding <-> %s::vector
                LIMIT %s
                """,
                [source_table, query_embedding, top_k],
            )
        else:
            cur.execute(
                """
                SELECT source_table, source_key, chunk_text
                FROM gold_chunks
                ORDER BY embedding <-> %s::vector
                LIMIT %s
                """,
                [query_embedding, top_k],
            )
        return [
            {'source_table': r[0], 'source_key': r[1], 'chunk_text': r[2]}
            for r in cur.fetchall()
        ]


def retrieve_chunks_for_entity(query_embedding, source_table, entity_name, top_k=5):
    """Nearest-neighbor search restricted to one named entity's own chunks
    (source_key LIKE 'EntityName|%'). Used for multi-entity comparison
    questions so one entity's chunks can't crowd out another's in a single
    shared top-k (see get_rag_reply())."""
    with connections['gold'].cursor() as cur:
        _set_probes(cur)
        cur.execute(
            """
            SELECT source_table, source_key, chunk_text
            FROM gold_chunks
            WHERE source_table = %s AND source_key LIKE %s
            ORDER BY embedding <-> %s::vector
            LIMIT %s
            """,
            [source_table, f"{entity_name}|%", query_embedding, top_k],
        )
        return [
            {'source_table': r[0], 'source_key': r[1], 'chunk_text': r[2]}
            for r in cur.fetchall()
        ]


def _top1_distance(query_embedding, chunks):
    """L2 distance from query_embedding to the single nearest already-
    retrieved chunk (chunks[0], since retrieve_chunks() orders by
    distance). Returns None if chunks is empty. Used only by the
    confidence gate in get_rag_reply() — a second small query rather than
    changing retrieve_chunks()'s return shape everywhere it's called."""
    if not chunks:
        return None
    with connections['gold'].cursor() as cur:
        _set_probes(cur)
        cur.execute(
            "SELECT embedding <-> %s::vector FROM gold_chunks "
            "WHERE source_table = %s AND source_key = %s",
            [query_embedding, chunks[0]['source_table'], chunks[0]['source_key']],
        )
        row = cur.fetchone()
        return float(row[0]) if row else None


# Confidence gate (see get_rag_reply()): if classify_query() found no exact
# entity-name match (source_table is None, meaning the search fell back to
# an unfiltered scan across all 215K chunks) AND the closest result is
# still this far away, the retrieved context is treated as unreliable and
# generation is skipped entirely rather than risking a confidently-wrong
# answer.
#
# Threshold re-measured against the current (spotify-lake-dev-data-sourced)
# gold_chunks: a confirmed out-of-scope query ("what is the weather like
# today?", "tell me a joke") sits ~1.21-1.26. Vague/no-entity-keyword
# questions that coincidentally match a label whose name shares words with
# the query (e.g. "tell me about the global streaming trend" nearest-
# matching a label called "Trending Now") sit ~0.98-1.0 — tightened from
# 1.10 to 0.95 to catch this class without the confidence gate ever
# applying to a real entity-routed match (classify_query() sets
# source_table for those, so the gate is skipped entirely; see below).
#
# NOT fully solved by this threshold: some coincidental label-name matches
# sit as low as ~0.87 (e.g. "total streams of all years??" nearest-matching
# a label literally named "17 Earth Years") — indistinguishable by distance
# alone from a legitimate match (a correctly-routed India query sits at
# ~0.88). Fixing that class would need an entity-plausibility check beyond
# distance, not attempted here.
#
# Deliberately scoped to source_table is None only, not applied globally:
# baseline_before.json showed an exact-name-routed case ("how is india
# doing", lowercase, routed to country_performance via classify_query()'s
# country-name match, top-1 distance 1.1856) that is CORRECT despite
# exceeding this threshold — informal phrasing measurably increases
# embedding distance even for a right answer. Gating on distance alone for
# that case would suppress a good answer, so the gate only fires when
# classify_query() also failed to find an entity-name/keyword match — i.e.
# when there is no other signal of relevance to fall back on.
NO_MATCH_DISTANCE_THRESHOLD = 0.95
NO_DATA_REPLY = "I don't have data to answer that."


SYSTEM_PROMPT = (
    "You are a data analyst assistant for a Spotify streaming analytics "
    "platform. Answer the user's question using ONLY the context provided "
    "below. If the context doesn't contain the answer, say so — do not "
    "make up numbers. When you cite a fact, name the artist/country/label "
    "and time period it came from. "
    "Format your response in markdown: bold key numbers and entity names "
    "with **asterisks**, use a bullet list when presenting 2 or more facts "
    "or a comparison, keep paragraphs to 2-3 lines, and use a markdown "
    "table when comparing multiple entities across the same metrics."
)


def build_prompt(question, chunks):
    context = "\n".join(f"- {c['chunk_text']}" for c in chunks)
    return f"Context:\n{context}\n\nQuestion: {question}"


# --- SQL router -------------------------------------------------------
#
# Vector similarity can only ever return the top-k chunks nearest to the
# question text — it cannot compute a MAX/COUNT/AVG or a year-over-year
# delta across rows it never retrieves together. Questions shaped like
# that are routed here instead, straight to the real gold tables, so the
# answer is a deterministic SQL result rather than a plausible-looking
# guess assembled from 5 semantically-similar-but-not-necessarily-correct
# chunks. Falls through to the normal vector-retrieval path (further down
# in get_rag_reply()) whenever no trigger keyword matches — this is
# additive, it never removes the pre-existing behavior.
#
# (table, entity_key_column, entity_display_column)
# artist_performance (built from Silver, see schema.sql) has real metrics,
# unlike kpi_artist -- so unlike the old kpi_artist-only setup, artist
# questions now support the full count/superlative/trend range through this
# generic dict, same as every other entity.
# Same ordering rationale as _TABLE_KEYWORDS above — kpi_song's generic
# "song"/"track" keywords checked last so a more specific co-occurring
# keyword (e.g. "artist") wins.
_SQL_TABLE_KEYWORDS = {
    'country_performance': ('country_name', 'country_name', ['country', 'countries', 'market', 'nation']),
    'artist_performance': ('artist_uri', 'artist_name', ['artist', 'artists', 'singer', 'singers', 'musician', 'musicians']),
    'label_performance_enhanced': ('standardized_label', 'standardized_label', ['label', 'labels', 'records', 'recordings']),
    'kpi_song': ('uri', 'uri', ['song', 'track', 'songs', 'tracks']),
}

_COUNT_KEYWORDS = ['how many', 'total number of', 'number of']
_TABLE_DISPLAY_NAME = {
    'country_performance': 'countries',
    'label_performance_enhanced': 'labels',
    'kpi_song': 'tracks',
    'artist_performance': 'artists',
}
_TREND_KEYWORDS = ['grew', 'growth', 'grow']
_SUPERLATIVE_KEYWORDS = [
    'highest', 'strongest', 'most', 'least', 'lowest', 'top', 'best',
    'worst', 'bottom', 'fastest', 'number one', 'number 1',
]
_ASCENDING_KEYWORDS = ['least', 'lowest', 'worst', 'bottom']

_YEAR_RE = re.compile(r'\b(20\d{2})\b')


def _sql_target_table(lowered_question):
    """Pick which gold table an aggregate/count/trend question is about,
    using the same keyword-matching style as classify_query()/_TABLE_KEYWORDS."""
    for table, (key_col, name_col, keywords) in _SQL_TABLE_KEYWORDS.items():
        if any(kw in lowered_question for kw in keywords):
            return table, key_col, name_col
    return None, None, None


def detect_sql_intent(question):
    """Returns a dict describing the SQL path to take, or None to fall
    through to vector retrieval. Keyword-triggered only — false negatives
    (an aggregate question phrased without a trigger word) degrade
    gracefully to the existing vector-retrieval behavior, not a regression."""
    lowered = question.lower()
    table, key_col, name_col = _sql_target_table(lowered)
    if table is None:
        # No entity keyword at all, but a bare "how many streams do we
        # have" is still answerable — it's an implicit global total, not a
        # per-entity one. country_performance is the natural "whole
        # platform" table (every country, every month) to sum from.
        # Anything else with no table match still correctly falls through
        # to vector retrieval.
        if any(kw in lowered for kw in _COUNT_KEYWORDS) and 'stream' in lowered:
            years = _YEAR_RE.findall(question)
            return {
                'kind': 'sum_streams', 'table': 'country_performance',
                'year': int(years[0]) if years else None,
            }
        return None

    if any(kw in lowered for kw in _COUNT_KEYWORDS):
        # "how many streams..." asks to SUM a metric, not COUNT(DISTINCT
        # entity) — without this, a question like "how many total streams
        # across all countries in 2025" matched "countries" as the table
        # keyword and wrongly answered with the *country count* (72)
        # instead of a streams total. 'stream' takes priority over the
        # generic count path whenever both are present, since a metric
        # noun in the question is a stronger, more specific signal than an
        # entity-plural keyword.
        if 'stream' in lowered:
            years = _YEAR_RE.findall(question)
            return {
                'kind': 'sum_streams', 'table': table,
                'year': int(years[0]) if years else None,
            }
        # "how many hit songs/tracks [in YEAR]" — a blanket COUNT(DISTINCT
        # uri) ignored both the "hit" filter and the year, e.g. answering
        # "how many hit songs were there in 2024" with the total track
        # count (242,572) regardless of hit status or year. Only kpi_song
        # has is_hit; other tables' "hit" concepts (hit_track_count on
        # artist_performance, hit_songs on country_performance) are
        # pre-aggregated counts, not filterable rows, so this only applies
        # here.
        if table == 'kpi_song' and 'hit' in lowered:
            years = _YEAR_RE.findall(question)
            return {
                'kind': 'count_hits', 'table': table,
                'year': int(years[0]) if years else None,
            }
        return {'kind': 'count', 'table': table, 'key_col': key_col}

    if any(kw in lowered for kw in _TREND_KEYWORDS):
        years = _YEAR_RE.findall(question)
        if not years:
            return None  # no explicit year to compute a delta against — don't guess
        target_year = int(years[0])
        return {
            'kind': 'trend', 'table': table, 'key_col': key_col, 'name_col': name_col,
            'target_year': target_year, 'prev_year': target_year - 1,
            'ascending': any(kw in lowered for kw in _ASCENDING_KEYWORDS),
        }

    if any(kw in lowered for kw in _SUPERLATIVE_KEYWORDS):
        return {
            'kind': 'superlative', 'table': table, 'key_col': key_col, 'name_col': name_col,
            'ascending': any(kw in lowered for kw in _ASCENDING_KEYWORDS),
        }

    return None


# kpi_song's only "name" column is uri (spotify:track:...) -- there's no
# title column on that table itself, but track_catalog (built from Silver,
# see schema.sql) has the real track_name for most uris. Superlative/trend
# queries on kpi_song join it in so "top track" cites a real name instead
# of the bare uri; COALESCE falls back to the uri for the tracks
# track_catalog doesn't cover (different source pipelines, not every
# kpi_song uri has a Silver-side match).
_NAME_JOIN = {
    'kpi_song': (
        'LEFT JOIN track_catalog tc ON tc.uri = {table}.uri',
        'COALESCE(tc.track_name, {table}.uri)',
    ),
}


def run_sql_intent(intent, limit=5):
    """Executes the SQL template selected by detect_sql_intent(). All
    table/column names come from the fixed _SQL_TABLE_KEYWORDS mapping
    (never from the raw question text); only numeric/year values are
    passed as query parameters. Returns (rows, description) where rows is
    a list of (label, value) tuples and description is a short string
    used both for the LLM context and for the 'sources' field."""
    table = intent['table']
    key_col = intent.get('key_col')
    join_clause, name_expr = _NAME_JOIN.get(table, ('', '{name_col}'))
    join_clause = join_clause.format(table=table)

    with connections['gold'].cursor() as cur:
        if intent['kind'] == 'count':
            cur.execute(f"SELECT COUNT(DISTINCT {key_col}) FROM {table}")  # noqa: S608 — key_col/table from fixed dict, not user input
            count = cur.fetchone()[0]
            return [(table, count)], f"sql:{table}:COUNT(DISTINCT {key_col})"

        if intent['kind'] == 'count_hits':
            if intent['year'] is not None:
                cur.execute(
                    "SELECT COUNT(DISTINCT uri) FROM kpi_song WHERE is_hit = 1 AND year = %s",
                    [intent['year']],
                )
                desc = f"sql:kpi_song:COUNT(DISTINCT uri) WHERE is_hit=1 AND year={intent['year']}"
            else:
                cur.execute("SELECT COUNT(DISTINCT uri) FROM kpi_song WHERE is_hit = 1")
                desc = "sql:kpi_song:COUNT(DISTINCT uri) WHERE is_hit=1"
            count = cur.fetchone()[0]
            return [(table, count)], desc

        if intent['kind'] == 'sum_streams':
            if intent['year'] is not None:
                cur.execute(
                    f"SELECT SUM(total_streams) FROM {table} WHERE year = %s",  # noqa: S608 — table from fixed dict, not user input
                    [intent['year']],
                )
                desc = f"sql:{table}:SUM(total_streams) WHERE year={intent['year']}"
            else:
                cur.execute(f"SELECT SUM(total_streams) FROM {table}")  # noqa: S608 — table from fixed dict, not user input
                desc = f"sql:{table}:SUM(total_streams)"
            total = cur.fetchone()[0] or 0
            return [(table, total)], desc

        if intent['kind'] == 'superlative':
            name_col = intent['name_col']
            select_name = name_expr.format(table=table, name_col=name_col)
            direction = 'ASC' if intent['ascending'] else 'DESC'
            cur.execute(
                f"SELECT {select_name}, SUM({table}.total_streams) AS total "  # noqa: S608
                f"FROM {table} {join_clause} GROUP BY {table}.{key_col}, {select_name} "
                f"ORDER BY total {direction} LIMIT %s",
                [limit],
            )
            rows = cur.fetchall()
            return rows, f"sql:{table}:SUM(total_streams) {direction}"

        if intent['kind'] == 'trend':
            name_col = intent['name_col']
            select_name = name_expr.format(table=table, name_col=name_col)
            direction = 'ASC' if intent['ascending'] else 'DESC'
            cur.execute(
                f"""
                WITH yearly AS (
                    SELECT {table}.{key_col} AS k, {select_name} AS name, {table}.year AS year, SUM({table}.total_streams) AS total
                    FROM {table} {join_clause}
                    WHERE {table}.year IN (%s, %s)
                    GROUP BY {table}.{key_col}, {select_name}, {table}.year
                )
                SELECT a.name, (a.total - COALESCE(b.total, 0)) AS growth
                FROM yearly a
                LEFT JOIN yearly b ON a.k = b.k AND b.year = %s
                WHERE a.year = %s
                ORDER BY growth {direction}
                LIMIT %s
                """,  # noqa: S608 — key_col/name_col/table from fixed dict, not user input
                [intent['target_year'], intent['prev_year'], intent['prev_year'], intent['target_year'], limit],
            )
            rows = cur.fetchall()
            return rows, f"sql:{table}:growth({intent['prev_year']}->{intent['target_year']}) {direction}"

    raise ValueError(f"unhandled SQL intent kind: {intent['kind']}")


def build_sql_prompt(question, rows, description):
    lines = "\n".join(f"- {label}: {value:,}" if isinstance(value, int) else f"- {label}: {value}" for label, value in rows)
    return f"Context (computed directly from the database, {description}):\n{lines}\n\nQuestion: {question}"


def _call_llm(prompt):
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': prompt},
    ]
    if GROQ_API_KEY:
        return _call_groq(messages)
    return _call_ollama(messages)


def _call_groq(messages):
    response = requests.post(
        GROQ_URL,
        headers={
            'Authorization': f'Bearer {GROQ_API_KEY}',
            'Content-Type': 'application/json',
        },
        json={
            'model': GROQ_MODEL,
            'messages': messages,
            'temperature': GENERATION_OPTIONS['temperature'],
            'max_tokens': 1024,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']


def _call_ollama(messages):
    response = requests.post(
        f'{OLLAMA_URL}/api/chat',
        json={
            'model': OLLAMA_MODEL,
            'messages': messages,
            'stream': False,
            'options': GENERATION_OPTIONS,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()['message']['content']


def get_rag_reply(question):
    # 1. SQL router — MAX/COUNT/AVG/trend questions have a deterministic
    # answer no top-k vector search can provide (see detect_sql_intent()
    # docstring). Checked first; falls through to normal retrieval below
    # when no trigger keyword matches.
    sql_intent = detect_sql_intent(question)
    if sql_intent is not None:
        rows, description = run_sql_intent(sql_intent)
        if sql_intent['kind'] == 'count':
            count = rows[0][1]
            table = rows[0][0]
            label = _TABLE_DISPLAY_NAME.get(table, table)
            return {'reply': f"There are **{count}** distinct {label} in the data.", 'sources': [description]}
        if sql_intent['kind'] == 'sum_streams':
            total = rows[0][1]
            year_note = f" in {sql_intent['year']}" if sql_intent['year'] else ""
            return {'reply': f"Total streams{year_note}: **{total:,}**.", 'sources': [description]}
        if sql_intent['kind'] == 'count_hits':
            count = rows[0][1]
            year_note = f" in {sql_intent['year']}" if sql_intent['year'] else ""
            return {'reply': f"There are **{count}** hit tracks{year_note} in the data.", 'sources': [description]}
        prompt = build_sql_prompt(question, rows, description)
        reply_text = _call_llm(prompt)
        return {'reply': reply_text, 'sources': [description]}

    # 2. Multi-country comparison — a single shared top-k lets whichever
    # country is semantically nearest crowd out the other(s) entirely (see
    # retrieve_chunks_for_entity() docstring), so a question naming 2+ real
    # countries gets one scoped retrieval per country instead of one shared
    # query. Same idea for artists in 2c/2d below.
    countries = detect_countries(question)
    if len(countries) >= 2:
        embedding = embed_query(question)
        chunks = []
        for name in countries:
            chunks.extend(retrieve_chunks_for_entity(embedding, 'country_performance', name, top_k=5))
        prompt = build_prompt(question, chunks)
        reply_text = _call_llm(prompt)
        sources = [f"{c['source_table']}:{c['source_key']}" for c in chunks]
        return {'reply': reply_text, 'sources': sources}

    # 2b. Single named/aliased country — same exact-match reasoning as the
    # comparison case above, not just a table restriction. Matters most for
    # aliases ("US", "UK"): the chunk text itself says "United States", not
    # "US", so relying on embedding similarity alone (the generic path
    # below) can miss it entirely and surface an unrelated country instead.
    if len(countries) == 1:
        embedding = embed_query(question)
        chunks = retrieve_chunks_for_entity(embedding, 'country_performance', countries[0], top_k=5)
        prompt = build_prompt(question, chunks)
        reply_text = _call_llm(prompt)
        sources = [f"{c['source_table']}:{c['source_key']}" for c in chunks]
        return {'reply': reply_text, 'sources': sources}

    # 2c. Multi-artist comparison — same reasoning as multi-country above.
    # Checked after countries (a question naming both would be unusual, and
    # country takes priority since that path was there first).
    artists = detect_artists(question)
    if len(artists) >= 2:
        embedding = embed_query(question)
        chunks = []
        for name, uri in artists:
            chunks.extend(retrieve_chunks_for_entity(embedding, 'artist_performance', uri, top_k=5))
        prompt = build_prompt(question, chunks)
        reply_text = _call_llm(prompt)
        sources = [f"{c['source_table']}:{c['source_key']}" for c in chunks]
        return {'reply': reply_text, 'sources': sources}

    # 2d. Single named artist — same exact-match reasoning as 2b for
    # countries. Without this, "How did Taylor Swift perform in 2025?" (no
    # "artist" keyword) falls all the way to the generic path below, where
    # embedding similarity alone can surface unrelated track chunks instead
    # of her own artist_performance chunks (observed in testing).
    if len(artists) == 1:
        name, uri = artists[0]
        embedding = embed_query(question)
        chunks = retrieve_chunks_for_entity(embedding, 'artist_performance', uri, top_k=5)
        prompt = build_prompt(question, chunks)
        reply_text = _call_llm(prompt)
        sources = [f"{c['source_table']}:{c['source_key']}" for c in chunks]
        return {'reply': reply_text, 'sources': sources}

    # 3. Normal single-entity/unclassified path.
    embedding = embed_query(question)
    source_table = classify_query(question)
    chunks = retrieve_chunks(embedding, source_table=source_table)

    # Confidence gate — only when classify_query() found no entity/keyword
    # match at all (source_table is None) and even the closest result is
    # farther than any confirmed-correct match observed for this project.
    # See NO_MATCH_DISTANCE_THRESHOLD above for why this isn't applied when
    # source_table is set (routed matches, including informally-phrased
    # ones, can legitimately exceed this distance and still be correct).
    if source_table is None:
        top1_distance = _top1_distance(embedding, chunks)
        if top1_distance is None or top1_distance > NO_MATCH_DISTANCE_THRESHOLD:
            return {'reply': NO_DATA_REPLY, 'sources': []}

    prompt = build_prompt(question, chunks)
    reply_text = _call_llm(prompt)

    sources = [f"{c['source_table']}:{c['source_key']}" for c in chunks]
    return {'reply': reply_text, 'sources': sources}
