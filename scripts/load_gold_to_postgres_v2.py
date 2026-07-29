"""
Production-ready Spotify Gold Layer loader.

Loads partitioned Parquet datasets directly from Amazon S3 into PostgreSQL.

Existing project modules used:
- config.settings
- config.database
- config.constants
- scripts.s3_reader
- scripts.validators

Usage:
    python scripts/load_gold_to_postgres_v2.py

Load selected datasets:
    python scripts/load_gold_to_postgres_v2.py \
        --datasets artist_performance country_performance

Validate S3 schemas without loading:
    python scripts/load_gold_to_postgres_v2.py --dry-run

Custom batch size:
    python scripts/load_gold_to_postgres_v2.py --batch-size 50000
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
import pyarrow as pa
from psycopg2 import sql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.constants import BATCH_SIZE, GOLD_TABLES
from config.database import get_connection
from config.settings import settings
from scripts.s3_reader import create_dataset, iter_batches
from scripts.validators import validate_table


LOGGER = logging.getLogger("spotify_gold_loader")


@dataclass
class LoadResult:
    dataset: str
    rows_loaded: int = 0
    batches_loaded: int = 0
    elapsed_seconds: float = 0.0
    status: str = "pending"


def configure_logging() -> None:
    """Configure console and file logging once."""
    if LOGGER.handlers:
        return

    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(
        log_dir / "load_gold_to_postgres_v2.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    LOGGER.setLevel(logging.INFO)
    LOGGER.addHandler(console_handler)
    LOGGER.addHandler(file_handler)
    LOGGER.propagate = False


def normalise_prefix(prefix: str | None) -> str:
    """Return the Gold prefix without a trailing slash."""
    if not prefix or not prefix.strip():
        raise RuntimeError("S3_GOLD_PREFIX is missing from .env.")

    return prefix.strip().rstrip("/")


def dataset_s3_path(dataset_name: str) -> str:
    """Build the S3 path for one Gold dataset."""
    return f"{normalise_prefix(settings.S3_GOLD_PREFIX)}/{dataset_name}"


def arrow_type_to_postgres(data_type: pa.DataType) -> str:
    """Map common PyArrow types to PostgreSQL types."""
    if pa.types.is_boolean(data_type):
        return "BOOLEAN"
    if pa.types.is_int8(data_type) or pa.types.is_int16(data_type):
        return "SMALLINT"
    if pa.types.is_int32(data_type):
        return "INTEGER"
    if pa.types.is_int64(data_type):
        return "BIGINT"
    if pa.types.is_uint8(data_type):
        return "SMALLINT"
    if pa.types.is_uint16(data_type):
        return "INTEGER"
    if pa.types.is_uint32(data_type):
        return "BIGINT"
    if pa.types.is_uint64(data_type):
        return "NUMERIC(20, 0)"
    if pa.types.is_float16(data_type) or pa.types.is_float32(data_type):
        return "REAL"
    if pa.types.is_float64(data_type):
        return "DOUBLE PRECISION"
    if pa.types.is_decimal(data_type):
        return f"NUMERIC({data_type.precision}, {data_type.scale})"
    if pa.types.is_date(data_type):
        return "DATE"
    if pa.types.is_timestamp(data_type):
        return "TIMESTAMPTZ" if data_type.tz else "TIMESTAMP"
    if pa.types.is_time(data_type):
        return "TIME"
    if pa.types.is_binary(data_type) or pa.types.is_large_binary(data_type):
        return "BYTEA"
    if (
        pa.types.is_list(data_type)
        or pa.types.is_large_list(data_type)
        or pa.types.is_struct(data_type)
        or pa.types.is_map(data_type)
    ):
        return "JSONB"
    return "TEXT"


def schema_columns(arrow_schema: pa.Schema) -> list[tuple[str, str]]:
    """Convert a PyArrow schema into PostgreSQL column definitions."""
    columns: list[tuple[str, str]] = []
    seen: set[str] = set()

    for field in arrow_schema:
        column_name = field.name.strip()

        if not column_name:
            raise ValueError("An empty column name was found.")
        if column_name in seen:
            raise ValueError(
                f"Duplicate column found in dataset schema: {column_name}"
            )

        seen.add(column_name)
        columns.append((column_name, arrow_type_to_postgres(field.type)))

    if not columns:
        raise ValueError("The dataset schema contains no columns.")

    return columns


def create_table_if_missing(
    conn,
    table_name: str,
    column_definitions: Sequence[tuple[str, str]],
) -> None:
    """Create the target table from the dataset schema."""
    definitions = sql.SQL(", ").join(
        sql.SQL("{} {}").format(
            sql.Identifier(column_name),
            sql.SQL(postgres_type),
        )
        for column_name, postgres_type in column_definitions
    )

    query = sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
        sql.Identifier(table_name),
        definitions,
    )

    with conn.cursor() as cursor:
        cursor.execute(query)


def get_existing_columns(conn, table_name: str) -> list[str]:
    """Return target-table columns in physical order."""
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        rows = cursor.fetchall()

    return [row["column_name"] for row in rows]


def validate_existing_schema(
    expected_columns: Sequence[str],
    existing_columns: Sequence[str],
    table_name: str,
) -> None:
    """Stop loading when the existing table schema differs."""
    expected = list(expected_columns)
    existing = list(existing_columns)

    if expected != existing:
        raise RuntimeError(
            f"Schema mismatch for public.{table_name}.\n"
            f"Expected: {expected}\n"
            f"Existing: {existing}"
        )


def truncate_table(conn, table_name: str) -> None:
    """Remove old rows before a complete Gold Layer reload."""
    with conn.cursor() as cursor:
        cursor.execute(
            sql.SQL("TRUNCATE TABLE {}").format(sql.Identifier(table_name))
        )


def serialise_complex_value(value: Any) -> Any:
    """Convert non-scalar values into JSON strings for COPY."""
    if value is None:
        return None

    if isinstance(
        value,
        (str, int, float, bool, date, datetime, Decimal),
    ):
        return value

    if isinstance(value, (list, tuple, dict, set)):
        return json.dumps(value, ensure_ascii=False, default=str)

    if hasattr(value, "tolist"):
        converted = value.tolist()
        if isinstance(converted, (list, dict)):
            return json.dumps(converted, ensure_ascii=False, default=str)

    return str(value)


def prepare_dataframe(
    record_batch: pa.RecordBatch,
    target_columns: Sequence[str],
) -> pd.DataFrame:
    """Convert one Arrow batch into a COPY-ready DataFrame."""
    dataframe = record_batch.to_pandas(
        date_as_object=False,
        timestamp_as_object=False,
    )

    actual_columns = list(dataframe.columns)
    expected_columns = list(target_columns)

    if actual_columns != expected_columns:
        raise RuntimeError(
            "Incoming batch columns do not match the target table.\n"
            f"Expected: {expected_columns}\n"
            f"Actual: {actual_columns}"
        )

    object_columns = dataframe.select_dtypes(include=["object"]).columns
    for column_name in object_columns:
        dataframe[column_name] = dataframe[column_name].map(
            serialise_complex_value
        )

    return dataframe


def copy_dataframe(
    conn,
    dataframe: pd.DataFrame,
    table_name: str,
    columns: Sequence[str],
) -> int:
    """Bulk insert one DataFrame using PostgreSQL COPY."""
    if dataframe.empty:
        return 0

    buffer = StringIO()
    dataframe.to_csv(
        buffer,
        index=False,
        header=False,
        na_rep="\\N",
        quoting=csv.QUOTE_MINIMAL,
        doublequote=True,
        lineterminator="\n",
        date_format="%Y-%m-%d %H:%M:%S",
    )
    buffer.seek(0)

    copy_query = sql.SQL(
        """
        COPY {} ({})
        FROM STDIN
        WITH (
            FORMAT CSV,
            NULL '\\N',
            QUOTE '"'
        )
        """
    ).format(
        sql.Identifier(table_name),
        sql.SQL(", ").join(
            sql.Identifier(column_name) for column_name in columns
        ),
    )

    with conn.cursor() as cursor:
        cursor.copy_expert(copy_query.as_string(conn), buffer)

    return len(dataframe)


def database_row_count(conn, table_name: str) -> int:
    """Return the final row count stored in PostgreSQL."""
    with conn.cursor() as cursor:
        cursor.execute(
            sql.SQL("SELECT COUNT(*) AS row_count FROM {}").format(
                sql.Identifier(table_name)
            )
        )
        row = cursor.fetchone()

    return int(row["row_count"])


def analyse_table(conn, table_name: str) -> None:
    """Refresh PostgreSQL planner statistics."""
    with conn.cursor() as cursor:
        cursor.execute(
            sql.SQL("ANALYZE {}").format(sql.Identifier(table_name))
        )


def inspect_dataset(dataset_name: str) -> tuple[str, pa.Schema]:
    """Validate S3 access and return the dataset path and schema."""
    validate_table(dataset_name)

    s3_path = dataset_s3_path(dataset_name)
    dataset = create_dataset(s3_path)
    arrow_schema = dataset.schema

    if len(arrow_schema) == 0:
        raise RuntimeError(f"No schema found for dataset: {s3_path}")

    return s3_path, arrow_schema


def load_dataset(
    conn,
    dataset_name: str,
    batch_size: int,
    dry_run: bool = False,
) -> LoadResult:
    """Load one complete Gold dataset in one transaction."""
    started_at = time.perf_counter()
    result = LoadResult(dataset=dataset_name)

    s3_path, arrow_schema = inspect_dataset(dataset_name)
    column_definitions = schema_columns(arrow_schema)
    target_columns = [name for name, _ in column_definitions]

    LOGGER.info("=" * 72)
    LOGGER.info("Dataset=%s | source=%s", dataset_name, s3_path)
    LOGGER.info("Columns=%s", ", ".join(target_columns))

    if dry_run:
        first_batch = next(
            iter_batches(
                s3_path=s3_path,
                batch_size=min(batch_size, 10),
            ),
            None,
        )

        if first_batch is None:
            raise RuntimeError(
                f"No Parquet rows found for dataset: {dataset_name}"
            )

        result.status = "validated"
        result.elapsed_seconds = time.perf_counter() - started_at
        return result

    try:
        create_table_if_missing(conn, dataset_name, column_definitions)

        existing_columns = get_existing_columns(conn, dataset_name)
        validate_existing_schema(
            target_columns,
            existing_columns,
            dataset_name,
        )

        truncate_table(conn, dataset_name)

        for batch_number, record_batch in enumerate(
            iter_batches(
                s3_path=s3_path,
                batch_size=batch_size,
            ),
            start=1,
        ):
            dataframe = prepare_dataframe(record_batch, target_columns)
            inserted = copy_dataframe(
                conn,
                dataframe,
                dataset_name,
                target_columns,
            )

            result.rows_loaded += inserted
            result.batches_loaded = batch_number

            LOGGER.info(
                "Dataset=%s | batch=%d | batch_rows=%d | total_rows=%d",
                dataset_name,
                batch_number,
                inserted,
                result.rows_loaded,
            )

        if result.batches_loaded == 0:
            raise RuntimeError(
                f"No rows were read from dataset: {dataset_name}"
            )

        stored_rows = database_row_count(conn, dataset_name)
        if stored_rows != result.rows_loaded:
            raise RuntimeError(
                f"Row-count validation failed for {dataset_name}: "
                f"loaded={result.rows_loaded}, stored={stored_rows}"
            )

        analyse_table(conn, dataset_name)
        conn.commit()

        result.status = "success"
        result.elapsed_seconds = time.perf_counter() - started_at

        LOGGER.info(
            "Committed dataset=%s | rows=%d | batches=%d | time=%.2fs",
            dataset_name,
            result.rows_loaded,
            result.batches_loaded,
            result.elapsed_seconds,
        )
        return result

    except Exception:
        conn.rollback()
        result.status = "failed"
        result.elapsed_seconds = time.perf_counter() - started_at
        LOGGER.exception("Rolled back dataset=%s", dataset_name)
        raise


def print_summary(results: Sequence[LoadResult]) -> None:
    """Write a compact final load summary."""
    LOGGER.info("=" * 72)
    LOGGER.info("LOAD SUMMARY")
    LOGGER.info("=" * 72)

    for result in results:
        LOGGER.info(
            "%-24s | %-10s | rows=%-12d | batches=%-6d | %.2fs",
            result.dataset,
            result.status,
            result.rows_loaded,
            result.batches_loaded,
            result.elapsed_seconds,
        )


def parse_arguments() -> argparse.Namespace:
    """Read command-line options."""
    parser = argparse.ArgumentParser(
        description=(
            "Load Spotify Gold Layer Parquet datasets "
            "from S3 into PostgreSQL."
        )
    )

    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=tuple(GOLD_TABLES.keys()),
        default=list(GOLD_TABLES.keys()),
        help="Datasets to load. Default: all configured Gold datasets.",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Rows processed per Arrow batch. Default: {BATCH_SIZE}.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate S3 access and schemas without writing PostgreSQL.",
    )

    args = parser.parse_args()
    if args.batch_size <= 0:
        parser.error("--batch-size must be greater than zero.")

    return args


def main() -> int:
    """Application entry point."""
    configure_logging()
    args = parse_arguments()

    LOGGER.info("Spotify Gold Layer Loader V2 started")
    LOGGER.info(
        "Datasets=%s | batch_size=%d | dry_run=%s",
        ", ".join(args.datasets),
        args.batch_size,
        args.dry_run,
    )

    results: list[LoadResult] = []
    conn = None

    try:
        if not args.dry_run:
            conn = get_connection()
            LOGGER.info(
                "Connected to PostgreSQL database=%s",
                settings.PGDATABASE,
            )

        for dataset_name in args.datasets:
            result = load_dataset(
                conn=conn,
                dataset_name=dataset_name,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
            )
            results.append(result)

        print_summary(results)
        LOGGER.info("Gold Layer Loader V2 completed successfully")
        return 0

    except Exception:
        print_summary(results)
        LOGGER.exception("Gold Layer Loader V2 failed")
        return 1

    finally:
        if conn is not None:
            conn.close()
            LOGGER.info("PostgreSQL connection closed")


if __name__ == "__main__":
    raise SystemExit(main())
