"""
Description
-----------
Reads Spotify Bronze layer data (raw CSV) from Amazon S3 and transforms it
into the Silver layer by performing:

• Data Cleaning
• Country Standardization
• Feature Engineering
• Optimized Parquet Writes

Incremental Loading
--------------------
Bronze holds one full-history CSV snapshot per ingest_date (Kaggle serves
the whole dataset each time, not a delta). This job only reprocesses rows
newer than what's already in Silver: it reads the latest Bronze snapshot,
filters to `date > max(date already in Silver)`, and appends the result.
On the very first run (no Silver data yet), the full snapshot is processed.

Outputs
-------
1. silver/song_charts
"""

# =============================================================================
# Imports
# =============================================================================

import logging

import boto3
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    create_map,
    initcap,
    lit,
    lower,
    max as spark_max,
    month,
    quarter,
    round,
    trim,
    when,
    year
)

# =============================================================================
# Logger
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

# =============================================================================
# Spark Session
# =============================================================================

spark = (
    SparkSession.builder
    .appName("Spotify Silver ETL")
    .config("spark.sql.adaptive.enabled", "true")
    .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
    .config("spark.sql.shuffle.partitions", "200")
    .config("spark.sql.parquet.compression.codec", "snappy")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

# =============================================================================
# S3 Paths
# =============================================================================
# Points at spotify-lake-dev-data (this branch's isolated test bucket), not
# group-1-dbda (the team's real bucket) — deliberately kept separate so this
# never touches shared/production data.

DATA_BUCKET = "spotify-lake-dev-data"
BRONZE_PREFIX = "bronze/charts_songs_daily/"
BRONZE_SONG_PATH = f"s3://{DATA_BUCKET}/{BRONZE_PREFIX}"
SILVER_SONG_PATH = "s3://spotify-lake-dev-data/silver/song_charts/"

# =============================================================================
# Read Bronze Layer
# =============================================================================

def get_latest_ingest_date():
    """
    Finds the most recent ingest_date=YYYY-MM-DD partition under Bronze.
    Bronze holds one full-history snapshot per ingest date, so only the
    latest one needs to be read.
    """

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")

    ingest_dates = set()
    for page in paginator.paginate(Bucket=DATA_BUCKET, Prefix=BRONZE_PREFIX, Delimiter="/"):
        for common_prefix in page.get("CommonPrefixes", []):
            partition = common_prefix["Prefix"].rstrip("/").split("/")[-1]
            if partition.startswith("ingest_date="):
                ingest_dates.add(partition.split("=", 1)[1])

    if not ingest_dates:
        raise FileNotFoundError(f"No ingest_date partitions found under s3://{DATA_BUCKET}/{BRONZE_PREFIX}")

    return max(ingest_dates)


def read_bronze():
    """
    Reads the latest raw Bronze charts_songs_daily CSV snapshot from S3.
    """

    latest_ingest_date = get_latest_ingest_date()
    bronze_path = f"{BRONZE_SONG_PATH}ingest_date={latest_ingest_date}/"

    logger.info("Reading Bronze snapshot: %s", bronze_path)

    bronze_song_charts = (
        spark.read
        .option("header", "true")
        .option("inferSchema", "true")
        .csv(bronze_path)
    )

    logger.info("Bronze dataset loaded successfully.")

    return bronze_song_charts

# =============================================================================
# Incremental Filtering
# =============================================================================

def get_last_processed_date():
    """
    Returns the max `date` already written to Silver, or None if Silver
    doesn't exist yet (first run).
    """

    s3 = boto3.client("s3")
    silver_prefix = SILVER_SONG_PATH.replace(f"s3://{DATA_BUCKET}/", "")
    response = s3.list_objects_v2(Bucket=DATA_BUCKET, Prefix=silver_prefix, MaxKeys=1)

    if response.get("KeyCount", 0) == 0:
        logger.info("No existing Silver data found — this is the first run.")
        return None

    last_date = (
        spark.read.parquet(SILVER_SONG_PATH)
        .agg(spark_max("date"))
        .collect()[0][0]
    )
    logger.info("Last processed date in Silver: %s", last_date)
    return last_date


def filter_new_rows(bronze_song_charts, last_processed_date):
    """
    Keeps only rows newer than what's already in Silver.
    """

    if last_processed_date is None:
        logger.info("Processing full Bronze snapshot (no prior Silver data).")
        return bronze_song_charts

    logger.info("Incremental load: keeping rows with date > %s", last_processed_date)
    return bronze_song_charts.filter(col("date") > lit(last_processed_date))

COUNTRY_MAPPING = {
    "ad": "Andorra",
    "ae": "United Arab Emirates",
    "ar": "Argentina",
    "at": "Austria",
    "au": "Australia",
    "be": "Belgium",
    "bg": "Bulgaria",
    "bo": "Bolivia",
    "br": "Brazil",
    "by": "Belarus",
    "ca": "Canada",
    "ch": "Switzerland",
    "cl": "Chile",
    "co": "Colombia",
    "cr": "Costa Rica",
    "cy": "Cyprus",
    "cz": "Czech Republic",
    "de": "Germany",
    "dk": "Denmark",
    "do": "Dominican Republic",
    "ec": "Ecuador",
    "ee": "Estonia",
    "eg": "Egypt",
    "es": "Spain",
    "fi": "Finland",
    "fr": "France",
    "gb": "United Kingdom",
    "global": "Global",
    "gr": "Greece",
    "gt": "Guatemala",
    "hk": "Hong Kong",
    "hn": "Honduras",
    "hu": "Hungary",
    "id": "Indonesia",
    "ie": "Ireland",
    "il": "Israel",
    "in": "India",
    "is": "Iceland",
    "it": "Italy",
    "jp": "Japan",
    "kr": "South Korea",
    "kz": "Kazakhstan",
    "lt": "Lithuania",
    "lu": "Luxembourg",
    "lv": "Latvia",
    "ma": "Morocco",
    "mx": "Mexico",
    "my": "Malaysia",
    "ng": "Nigeria",
    "ni": "Nicaragua",
    "nl": "Netherlands",
    "no": "Norway",
    "nz": "New Zealand",
    "pa": "Panama",
    "pe": "Peru",
    "ph": "Philippines",
    "pk": "Pakistan",
    "pl": "Poland",
    "pt": "Portugal",
    "py": "Paraguay",
    "ro": "Romania",
    "sa": "Saudi Arabia",
    "se": "Sweden",
    "sg": "Singapore",
    "sk": "Slovakia",
    "sv": "El Salvador",
    "th": "Thailand",
    "tr": "Turkey",
    "tw": "Taiwan",
    "ua": "Ukraine",
    "us": "United States",
    "uy": "Uruguay",
    "ve": "Venezuela",
    "vn": "Vietnam",
    "za": "South Africa"
}

# =============================================================================
# Initial Cleaning
# =============================================================================

def clean_song_charts(bronze_song_charts):
    """
    Cleans and standardizes the Bronze dataset.
    """

    logger.info("Cleaning Bronze dataset...")

    mapping_expr = create_map(
        *[
            value
            for item in COUNTRY_MAPPING.items()
            for value in (lit(item[0]), lit(item[1]))
        ]
    )

    silver_song_charts = (

        bronze_song_charts

        # Remove duplicate records
        .dropDuplicates(
            [
                "date",
                "country",
                "uri"
            ]
        )

        # Rename country code column
        .withColumnRenamed(
            "country",
            "market"
        )

        # Add readable country name
        .withColumn(
            "country_name",
            mapping_expr[col("market")]
        )

        # Remove Global aggregate market
        .filter(
            col("country_name") != "Global"
        )

        # Replace NULL values
        .fillna({
            "artist_names": "Unknown Artist",
            "track_name": "Unknown Track",
            "label": "Independent"
        })

        # Trim artist names
        .withColumn(
            "artist_names",
            trim(col("artist_names"))
        )
        .withColumn("track_name", trim(col("track_name")))
        .withColumn("label", trim(col("label")))
    )

    logger.info("Initial cleaning completed.")

    return silver_song_charts

# =============================================================================
# Feature Engineering
# =============================================================================

def feature_engineering(silver_song_charts):
    """
    Creates analytical features for the Silver Song Charts table.
    """

    logger.info("Creating analytical features...")

    silver_song_charts = (

        silver_song_charts

        # --------------------------------------------------------
        # Time Intelligence
        # --------------------------------------------------------

        .withColumn(
            "year",
            year(col("date"))
        )

        .withColumn(
            "month",
            month(col("date"))
        )

        .withColumn(
            "quarter",
            quarter(col("date"))
        )

        # --------------------------------------------------------
        # Hit Classification
        # --------------------------------------------------------

        .withColumn(

            "hit_category",

            when(
                col("rank") <= 10,
                "Global Hit"
            )

            .when(
                col("rank") <= 50,
                "Major Hit"
            )

            .when(
                col("rank") <= 100,
                "Popular Track"
            )

            .otherwise(
                "Charting Track"
            )
        )

        # --------------------------------------------------------
        # Standardized Label
        # --------------------------------------------------------

        .withColumn(
            "standardized_label",
            initcap(
                lower(
                    trim(col("label"))
                )
            )
        )

        # --------------------------------------------------------
        # Chart Strength Score
        # --------------------------------------------------------

        .withColumn(
            "chart_strength_score",
            round(
                (
                    ((201 - col("rank")) * 0.4)
                    +
                    ((201 - col("peak_rank")) * 0.3)
                    +
                    (col("days_on_chart") * 0.2)
                    +
                    (col("consecutive_days") * 0.1)
                ),
                2
            )
        )

    )

    logger.info("Feature engineering completed.")

    return silver_song_charts


def write_song_charts(silver_song_charts):
    """
    Appends the new Silver Song Charts rows to Amazon S3. Append (not
    overwrite) because the incoming DataFrame only contains the
    incremental delta — overwriting would wipe out already-processed
    months that aren't part of this run's data.
    """

    logger.info("Writing Silver Song Charts (incremental append)...")

    (
        silver_song_charts
        .repartition(
            60,
            "year",
            "month"
        )
        .write
        .mode("append")
        .partitionBy(
            "year",
            "month"
        )
        .option("compression", "snappy")
        .parquet(SILVER_SONG_PATH)
    )

    logger.info("Silver Song Charts written successfully.")

# =============================================================================
# Main ETL Pipeline
# =============================================================================

def main():

    logger.info("=" * 80)
    logger.info("Spotify Silver ETL Started")
    logger.info("=" * 80)

    last_processed_date = get_last_processed_date()

    bronze_song_charts = read_bronze()
    bronze_song_charts = filter_new_rows(bronze_song_charts, last_processed_date)

    if bronze_song_charts.isEmpty():
        logger.info("No new rows to process — Silver is already up to date.")
    else:
        silver_song_charts = clean_song_charts(bronze_song_charts)
        silver_song_charts = feature_engineering(silver_song_charts)
        write_song_charts(silver_song_charts)

    logger.info("=" * 80)
    logger.info("Spotify Silver ETL Completed Successfully")
    logger.info("=" * 80)

# =============================================================================
# Driver
# =============================================================================

if __name__ == "__main__":

    try:
        main()

    except Exception as e:
        logger.exception("Spotify Silver ETL Failed.")
        raise e

    finally:
        spark.stop()
        logger.info("Spark Session Stopped.")
