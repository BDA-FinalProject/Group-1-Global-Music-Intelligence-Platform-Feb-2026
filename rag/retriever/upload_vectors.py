from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Iterator

from qdrant_client.models import PointStruct

from rag.retriever.qdrant_store import (
    ensure_collection,
    get_collection_name,
    get_qdrant_client,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "embedded_chunks.jsonl"


def read_jsonl(path: Path) -> Iterator[dict]:
    """Stream records from a JSONL file."""
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON at line {line_number}: {error}"
                ) from error


def to_qdrant_id(chunk_id: str) -> str:
    """Convert the deterministic chunk hash into a deterministic UUID."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def make_point(record: dict) -> PointStruct:
    """Convert an embedded chunk into a Qdrant point."""
    payload = {
        "chunk_id": record["id"],
        "text": record["text"],
        **record["metadata"],
    }

    return PointStruct(
        id=to_qdrant_id(record["id"]),
        vector=record["embedding"],
        payload=payload,
    )


def upload_batch(
    client,
    collection_name: str,
    batch: list[PointStruct],
) -> None:
    client.upsert(
        collection_name=collection_name,
        points=batch,
        wait=True,
    )


def upload_vectors(
    input_path: Path,
    batch_size: int,
) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    client = get_qdrant_client()
    collection_name = get_collection_name()

    ensure_collection(client, collection_name)

    batch: list[PointStruct] = []
    uploaded = 0

    for record in read_jsonl(input_path):
        batch.append(make_point(record))

        if len(batch) >= batch_size:
            upload_batch(client, collection_name, batch)

            uploaded += len(batch)
            print(f"Uploaded: {uploaded:,}")
            batch.clear()

    if batch:
        upload_batch(client, collection_name, batch)
        uploaded += len(batch)
        print(f"Uploaded: {uploaded:,}")

    print(f"Upload completed: {uploaded:,} vectors")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload embedded chunks to Qdrant Cloud."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    upload_vectors(
        input_path=args.input,
        batch_size=args.batch_size,
    )