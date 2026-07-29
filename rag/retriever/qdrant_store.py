from __future__ import annotations

import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

load_dotenv()

VECTOR_SIZE = 384


def get_qdrant_client() -> QdrantClient:
    """Create an authenticated Qdrant Cloud client."""
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")

    if not url or not api_key:
        raise ValueError(
            "QDRANT_URL and QDRANT_API_KEY must be set in .env"
        )

    return QdrantClient(
        url=url,
        api_key=api_key,
        timeout=60,
    )


def get_collection_name() -> str:
    """Return the configured Qdrant collection name."""
    return os.getenv(
        "QDRANT_COLLECTION",
        "spotify_gold_chunks",
    )


def ensure_collection(
    client: QdrantClient,
    collection_name: str,
) -> None:
    """Create the collection if it does not already exist."""
    if client.collection_exists(collection_name):
        print(f"Collection already exists: {collection_name}")
        return

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )

    print(f"Collection created: {collection_name}")