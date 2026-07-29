from __future__ import annotations

import argparse

from sentence_transformers import SentenceTransformer

from rag.retriever.qdrant_store import (
    get_collection_name,
    get_qdrant_client,
)

MODEL_NAME = "BAAI/bge-small-en-v1.5"


class Retriever:
    def __init__(self):
        self.client = get_qdrant_client()
        self.collection = get_collection_name()

        print("Loading embedding model...")
        self.model = SentenceTransformer(MODEL_NAME)

    def search(self, query: str, top_k: int = 5):
        query_embedding = self.model.encode(
            query,
            normalize_embeddings=True,
        ).tolist()

        results = self.client.query_points(
            collection_name=self.collection,
            query=query_embedding,
            limit=top_k,
            with_payload=True,
        ).points

        output = []

        for point in results:
            output.append(
                {
                    "score": round(point.score, 4),
                    "text": point.payload.get("text"),
                    "metadata": {
                        k: v
                        for k, v in point.payload.items()
                        if k != "text"
                    },
                }
            )

        return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str)
    parser.add_argument("--top-k", type=int, default=5)

    args = parser.parse_args()

    retriever = Retriever()

    results = retriever.search(
        args.query,
        top_k=args.top_k,
    )

    for i, item in enumerate(results, start=1):
        print("=" * 80)
        print(f"Rank : {i}")
        print(f"Score: {item['score']}")
        print(item["text"])


if __name__ == "__main__":
    main()