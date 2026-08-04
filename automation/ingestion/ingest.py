#!/usr/bin/env python3
"""Download one file from a Kaggle dataset and land it in the bronze layer.

Reads Kaggle credentials from SSM at runtime, downloads the target file,
converts it to Parquet in bounded-memory chunks (the source file can be
several GB decompressed), and uploads both the raw file and the Parquet
output to S3 under bronze/. Idempotent: re-running for the same
--ingest-date overwrites the same dated partition rather than duplicating.
"""
import argparse
import json
import logging
import os
import stat
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("ingest")

CHUNK_SIZE = 250_000


def parse_args():
    p = argparse.ArgumentParser(description="Kaggle -> bronze S3 ingestion")
    p.add_argument("--kaggle-slug", default=os.environ.get("KAGGLE_SLUG"))
    p.add_argument("--target-file", default=os.environ.get("TARGET_FILE"))
    p.add_argument("--table-name", default=os.environ.get("TABLE_NAME"))
    p.add_argument("--data-bucket", default=os.environ.get("DATA_BUCKET"))
    p.add_argument("--kaggle-username-param", default=os.environ.get("KAGGLE_USERNAME_PARAM"))
    p.add_argument("--kaggle-key-param", default=os.environ.get("KAGGLE_KEY_PARAM"))
    p.add_argument("--aws-region", default=os.environ.get("AWS_REGION", "ap-south-1"))
    p.add_argument("--work-dir", default=os.environ.get("WORK_DIR", "/tmp/ingest"))
    p.add_argument("--ingest-date", default=os.environ.get("INGEST_DATE") or date.today().isoformat())
    args = p.parse_args()

    required = {
        "--kaggle-slug": args.kaggle_slug,
        "--target-file": args.target_file,
        "--table-name": args.table_name,
        "--data-bucket": args.data_bucket,
        "--kaggle-username-param": args.kaggle_username_param,
        "--kaggle-key-param": args.kaggle_key_param,
    }
    missing = [name for name, val in required.items() if not val]
    if missing:
        p.error(f"missing required config: {', '.join(missing)}")
    return args


def write_kaggle_credentials(ssm, username_param, key_param):
    username = ssm.get_parameter(Name=username_param, WithDecryption=True)["Parameter"]["Value"]
    key = ssm.get_parameter(Name=key_param, WithDecryption=True)["Parameter"]["Value"]

    kaggle_dir = Path.home() / ".kaggle"
    kaggle_dir.mkdir(parents=True, exist_ok=True)
    creds_path = kaggle_dir / "kaggle.json"
    creds_path.write_text(json.dumps({"username": username, "key": key}))
    creds_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    log.info("wrote Kaggle credentials to %s", creds_path)


def download_target_file(kaggle_slug, target_file, work_dir):
    work_dir.mkdir(parents=True, exist_ok=True)
    log.info("downloading %s from %s", target_file, kaggle_slug)
    subprocess.run(
        [
            "kaggle", "datasets", "download",
            "-d", kaggle_slug,
            "-f", target_file,
            "-p", str(work_dir),
            "--force",
        ],
        check=True,
    )

    downloaded = work_dir / target_file
    if not downloaded.exists():
        # Kaggle sometimes wraps the single requested file in a zip.
        zipped = work_dir / f"{target_file}.zip"
        if zipped.exists():
            with zipfile.ZipFile(zipped) as zf:
                zf.extractall(work_dir)
        if not downloaded.exists():
            raise FileNotFoundError(f"expected {downloaded} after download, not found")
    return downloaded


def csv_to_parquet_chunked(csv_path, parquet_path, compression):
    """Streams CSV -> Parquet in bounded chunks so memory use doesn't scale
    with file size (source files here run 8-10GB decompressed)."""
    log.info("converting %s -> %s (chunked, %d rows/chunk)", csv_path, parquet_path, CHUNK_SIZE)
    writer = None
    total_rows = 0
    try:
        reader = pd.read_csv(csv_path, compression=compression, chunksize=CHUNK_SIZE)
        for i, chunk in enumerate(reader):
            table = pa.Table.from_pandas(chunk, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(parquet_path, table.schema, compression="snappy")
            writer.write_table(table)
            total_rows += len(chunk)
            log.info("chunk %d: %d rows written (total %d)", i, len(chunk), total_rows)
    finally:
        if writer is not None:
            writer.close()
    log.info("conversion complete: %d total rows", total_rows)
    return total_rows


def upload_file(s3, bucket, local_path, key):
    log.info("uploading %s -> s3://%s/%s", local_path, bucket, key)
    s3.upload_file(str(local_path), bucket, key)


def main():
    args = parse_args()
    work_dir = Path(args.work_dir)

    session = boto3.session.Session(region_name=args.aws_region)
    ssm = session.client("ssm")
    s3 = session.client("s3")

    write_kaggle_credentials(ssm, args.kaggle_username_param, args.kaggle_key_param)
    csv_path = download_target_file(args.kaggle_slug, args.target_file, work_dir)

    compression = "gzip" if csv_path.suffix == ".gz" else None
    parquet_path = work_dir / f"{args.table_name}.parquet"
    csv_to_parquet_chunked(csv_path, parquet_path, compression)

    raw_key = f"bronze/_raw/{args.table_name}/ingest_date={args.ingest_date}/{csv_path.name}"
    parquet_key = f"bronze/{args.table_name}/ingest_date={args.ingest_date}/{args.table_name}.parquet"

    upload_file(s3, args.data_bucket, csv_path, raw_key)
    upload_file(s3, args.data_bucket, parquet_path, parquet_key)

    log.info(
        "ingestion complete: raw=s3://%s/%s parquet=s3://%s/%s",
        args.data_bucket, raw_key, args.data_bucket, parquet_key,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("ingestion failed")
        sys.exit(1)
