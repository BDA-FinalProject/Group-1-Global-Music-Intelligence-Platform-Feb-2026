"""
S3 Gold Layer Reader

Reads partitioned Parquet datasets directly from Amazon S3 using
PyArrow Dataset API and yields memory-efficient record batches.
"""

from collections.abc import Iterator

import pyarrow as pa
import pyarrow.dataset as ds
from pyarrow.fs import S3FileSystem

from config.settings import settings


def get_s3_filesystem() -> S3FileSystem:
    """Create an S3 filesystem using the EC2 IAM role or local AWS credentials."""
    return S3FileSystem(region=settings.AWS_REGION)


def normalise_s3_path(s3_path: str) -> str:
    """
    PyArrow S3FileSystem expects:
    bucket-name/folder/path

    Instead of:
    s3://bucket-name/folder/path
    """
    return s3_path.removeprefix("s3://").rstrip("/")


def create_dataset(s3_path: str) -> ds.Dataset:
    """
    Create a partition-aware PyArrow Dataset.

    Hive partitioning reads values such as:
    year=2024/
    as a virtual column named 'year'.
    """
    return ds.dataset(
        normalise_s3_path(s3_path),
        filesystem=get_s3_filesystem(),
        format="parquet",
        partitioning="hive",
    )


def iter_batches(
    s3_path: str,
    batch_size: int = 10_000,
    columns: list[str] | None = None,
) -> Iterator[pa.RecordBatch]:
    """
    Yield Parquet data in batches instead of loading the entire table in memory.
    """
    dataset = create_dataset(s3_path)

    scanner = dataset.scanner(
        columns=columns,
        batch_size=batch_size,
        use_threads=True,
    )

    yield from scanner.to_batches()