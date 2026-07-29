from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Iterator

from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_INPUT = PROJECT_ROOT / "data" / "gold_chunks.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "embedded_chunks.jsonl"
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def read_jsonl(path: Path) -> Iterator[dict]:
    """Read valid JSON objects from a JSONL file."""
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


def load_completed_ids(output_path: Path) -> set[str]:
    """Read already embedded chunk IDs for resume support."""
    if not output_path.exists():
        return set()

    completed_ids: set[str] = set()

    for record in read_jsonl(output_path):
        chunk_id = record.get("id")

        if chunk_id:
            completed_ids.add(chunk_id)

    return completed_ids


def write_embedded_batch(
    output_file,
    chunks: list[dict],
    embeddings,
) -> int:
    """Write one embedded batch to the output JSONL file."""
    written = 0

    for chunk, vector in zip(chunks, embeddings):
        output_record = {
            "id": chunk["id"],
            "text": chunk["text"],
            "embedding": vector.tolist(),
            "metadata": chunk["metadata"],
        }

        output_file.write(
            json.dumps(output_record, ensure_ascii=False) + "\n"
        )
        written += 1

    output_file.flush()
    return written


def embed_batch(
    model: SentenceTransformer,
    chunks: list[dict],
):
    """Generate normalised embeddings for chunk texts."""
    texts = [chunk["text"] for chunk in chunks]

    return model.encode(
        texts,
        batch_size=len(texts),
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )


def embed_chunks(
    input_path: Path,
    output_path: Path,
    model_name: str,
    batch_size: int,
    resume: bool,
    max_chunks: int | None,
) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    completed_ids = (
        load_completed_ids(output_path)
        if resume
        else set()
    )

    if completed_ids:
        logger.info(
            "Resume enabled: %s chunks already embedded",
            f"{len(completed_ids):,}",
        )

    logger.info("Loading embedding model: %s", model_name)

    model = SentenceTransformer(model_name)

    logger.info(
        "Model loaded. Embedding dimension: %s",
        model.get_sentence_embedding_dimension(),
    )

    file_mode = "a" if resume else "w"
    batch: list[dict] = []
    embedded_count = 0
    skipped_count = 0

    with output_path.open(file_mode, encoding="utf-8") as output_file:
        for chunk in read_jsonl(input_path):
            chunk_id = chunk.get("id")
            text = chunk.get("text")

            if not chunk_id or not text:
                logger.warning("Skipping chunk with missing ID or text")
                skipped_count += 1
                continue

            if chunk_id in completed_ids:
                skipped_count += 1
                continue

            batch.append(chunk)

            if len(batch) >= batch_size:
                embeddings = embed_batch(model, batch)

                embedded_count += write_embedded_batch(
                    output_file,
                    batch,
                    embeddings,
                )

                logger.info(
                    "Embedded %s chunks",
                    f"{embedded_count:,}",
                )

                batch.clear()

                if max_chunks and embedded_count >= max_chunks:
                    break

        if batch and (not max_chunks or embedded_count < max_chunks):
            if max_chunks:
                remaining = max_chunks - embedded_count
                batch = batch[:remaining]

            embeddings = embed_batch(model, batch)

            embedded_count += write_embedded_batch(
                output_file,
                batch,
                embeddings,
            )

    logger.info("Embedding completed")
    logger.info("New embedded chunks: %s", f"{embedded_count:,}")
    logger.info("Skipped chunks: %s", f"{skipped_count:,}")
    logger.info("Output file: %s", output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate BGE embeddings for Gold RAG chunks."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
    )
    parser.add_argument(
        "--resume",
        action="store_true",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    embed_chunks(
        input_path=args.input,
        output_path=args.output,
        model_name=args.model,
        batch_size=args.batch_size,
        resume=args.resume,
        max_chunks=args.max_chunks,
    )