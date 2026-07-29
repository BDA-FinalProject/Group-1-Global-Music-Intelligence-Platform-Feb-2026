from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from psycopg2.extras import RealDictCursor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from config.database import get_connection
from rag.chunking.chunk_builder import (
    artist_chunk,
    country_chunk,
    global_chunk,
    label_chunk,
)

OUTPUT = PROJECT_ROOT / "data" / "gold_chunks.jsonl"


QUERIES = {
    "artist_performance": """
        SELECT *
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY year_month
                       ORDER BY total_streams DESC NULLS LAST
                   ) AS row_num
            FROM artist_performance
        ) ranked
        WHERE row_num <= %s
        ORDER BY year, month, total_streams DESC
    """,
    "label_performance": """
        SELECT *
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY year_month
                       ORDER BY total_streams DESC NULLS LAST
                   ) AS row_num
            FROM label_performance
        ) ranked
        WHERE row_num <= %s
        ORDER BY year, month, total_streams DESC
    """,
    "country_performance": """
        SELECT *
        FROM country_performance
        ORDER BY year, month, total_streams DESC
    """,
    "dashboard_summary": """
        SELECT * FROM dashboard_summary ORDER BY year, month
    """,
    "monthly_trends": """
        SELECT * FROM monthly_trends ORDER BY year, month
    """,
}


def write_rows(cursor, output_file, table: str) -> int:
    count = 0

    for row in cursor:
        row = dict(row)
        row.pop("row_num", None)

        if table == "artist_performance":
            chunk = artist_chunk(row)
        elif table == "label_performance":
            chunk = label_chunk(row)
        elif table == "country_performance":
            chunk = country_chunk(row)
        else:
            chunk = global_chunk(row, table)

        output_file.write(json.dumps(chunk, ensure_ascii=False) + "\n")
        count += 1

    return count


def main(limit: int) -> None:
    OUTPUT.parent.mkdir(exist_ok=True)
    total = 0

    with get_connection() as conn, OUTPUT.open("w", encoding="utf-8") as file:
        for table, query in QUERIES.items():
            with conn.cursor(
                name=f"{table}_cursor",
                cursor_factory=RealDictCursor,
            ) as cursor:
                cursor.itersize = 2000

                if table in {"artist_performance", "label_performance"}:
                    cursor.execute(query, (limit,))
                else:
                    cursor.execute(query)

                count = write_rows(cursor, file, table)
                total += count
                print(f"{table}: {count:,} chunks")

    print(f"\nTotal chunks: {total:,}")
    print(f"Saved to: {OUTPUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit-per-month",
        type=int,
        default=100,
        help="Top artists and labels selected per month.",
    )
    args = parser.parse_args()
    main(args.limit_per_month)