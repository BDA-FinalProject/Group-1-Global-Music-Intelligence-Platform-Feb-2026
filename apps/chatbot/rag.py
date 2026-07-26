"""
RAG pipeline: embed the question, retrieve nearest gold_chunks via pgvector,
assemble a grounded prompt, generate an answer via a local Ollama model
(free, no API key — chosen over the Anthropic API since a paid key wasn't
available). Requires `ollama serve` running locally with OLLAMA_MODEL
pulled (see get_rag_reply()).
"""
import os

import requests
from django.db import connections

OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'llama3.2:3b')

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model


def embed_query(text):
    return _get_model().encode([text])[0].tolist()


def retrieve_chunks(query_embedding, top_k=5):
    """Nearest-neighbor search against gold_chunks via pgvector's <-> operator."""
    with connections['gold'].cursor() as cur:
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


SYSTEM_PROMPT = (
    "You are a data analyst assistant for a Spotify streaming analytics "
    "platform. Answer the user's question using ONLY the context provided "
    "below. If the context doesn't contain the answer, say so — do not "
    "make up numbers. When you cite a fact, name the artist/country/label "
    "and time period it came from."
)


def build_prompt(question, chunks):
    context = "\n".join(f"- {c['chunk_text']}" for c in chunks)
    return f"Context:\n{context}\n\nQuestion: {question}"


def get_rag_reply(question):
    embedding = embed_query(question)
    chunks = retrieve_chunks(embedding)
    prompt = build_prompt(question, chunks)

    response = requests.post(
        f'{OLLAMA_URL}/api/chat',
        json={
            'model': OLLAMA_MODEL,
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt},
            ],
            'stream': False,
        },
        timeout=60,
    )
    response.raise_for_status()
    reply_text = response.json()['message']['content']

    sources = [f"{c['source_table']}:{c['source_key']}" for c in chunks]
    return {'reply': reply_text, 'sources': sources}
