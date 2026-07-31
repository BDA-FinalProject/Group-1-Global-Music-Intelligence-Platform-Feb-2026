"""
===============================================================================
Spotify Global Music Intelligence Platform
Bronze -> Silver Layer ETL Job

Platform    : AWS EMR
Storage     : Amazon S3
Engine      : Apache Spark

Description
-----------
Reads Spotify Bronze layer data from Amazon S3 (bucket: bronze-script)
and transforms it into the Silver layer by performing:

    • Data Cleaning
    • Country Standardization
    • Feature Engineering
    • Optimized Parquet Writes

Writes the Silver layer output to Amazon S3 (bucket: bronze-script,
prefix: silverlayer/).

Inputs
------
1. s3://bronze-script/bronze/raw_data/charts_songs_daily.csv

Outputs
-------
1. s3://bronze-script/silverlayer/song_charts/

Usage
-----
    spark-submit spotify_bronze_to_silver_etl.py
    spark-submit spotify_bronze_to_silver_etl.py \
        --input-path s3://bronze-script/bronze/raw_data/charts_songs_daily.csv \
        --output-bucket s3://bronze-script/silverlayer
===============================================================================
"""

# =============================================================================
# Imports
# =============================================================================

import argparse
import logging

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    col,
    create_map,
    initcap,
    lit,
    lower,
    month,
    quarter,
    round,
    trim,
    weekofyear,
    when,
    year,
)

# =============================================================================
# Logger
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("spotify_bronze_to_silver_etl")

# =============================================================================
# Default S3 Paths
# =============================================================================

DEFAULT_BRONZE_SONG_PATH = "s3://bronze-script/bronze/raw_data/charts_songs_daily.csv"

DEFAULT_SILVER_BUCKET = "s3://bronze-script/silverlayer"

# =============================================================================
# Country Code -> Country Name Mapping
# =============================================================================

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
    "za": "South Africa",
}

# =============================================================================
# Argument Parsing
# =============================================================================

def parse_args():
    """
    Parses command-line arguments so the job's input/output locations
    can be overridden at run time (e.g. from an EMR step or Airflow DAG)
    without editing the script.
    """

    parser = argparse.ArgumentParser(
        description="Spotify Bronze -> Silver ETL Job"
    )

    parser.add_argument(
        "--input-path",
        type=str,
        default=DEFAULT_BRONZE_SONG_PATH,
        help="S3 path to the Bronze charts_songs_daily CSV dataset.",
    )

    parser.add_argument(
        "--output-bucket",
        type=str,
        default=DEFAULT_SILVER_BUCKET,
        help="S3 bucket/prefix (e.g. s3://bronze-script/silverlayer) that will hold the Silver output.",
    )

    # Using parse_known_args instead of parse_args so that extra/unknown
    # arguments injected by the launch environment (e.g. EMR notebooks,
    # Jupyter/IPython kernel args, or additional spark-submit options)
    # do not cause argparse to call sys.exit(2). Any unrecognized args
    # are simply logged and ignored.
    known_args, unknown_args = parser.parse_known_args()

    if unknown_args:
        logger.warning(
            "Ignoring unrecognized arguments: %s", unknown_args
        )

    return known_args

# =============================================================================
# Spark Session
# =============================================================================

def get_spark_session() -> SparkSession:
    """
    Builds and returns the SparkSession used by this ETL job.
    """

    spark = (
        SparkSession.builder
        .appName("Spotify Bronze to Silver ETL")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.shuffle.partitions", "200")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    return spark

# =============================================================================
# Extract: Read Bronze Layer
# =============================================================================

def read_bronze(spark: SparkSession, bronze_song_path: str) -> DataFrame:
    """
    Reads the Bronze charts_songs_daily dataset from S3. The Bronze
    layer for this pipeline is delivered as CSV (with a header row),
    so the file is read with schema inference enabled.
    """

    logger.info("Reading Bronze dataset from: %s", bronze_song_path)

    bronze_song_charts = (
        spark.read
        .option("header", "true")
        .option("inferSchema", "true")
        .csv(bronze_song_path)
    )

    record_count = bronze_song_charts.count()

    logger.info(
        "Bronze dataset loaded successfully. Record count: %s",
        record_count,
    )

    if record_count == 0:
        raise ValueError(
            f"Bronze dataset at {bronze_song_path} is empty. Aborting ETL."
        )

    return bronze_song_charts

# =============================================================================
# Transform: Initial Cleaning
# =============================================================================

def clean_song_charts(bronze_song_charts: DataFrame) -> DataFrame:
    """
    Cleans and standardizes the Bronze dataset:
        • Removes duplicate records
        • Renames the country code column
        • Maps country codes to readable country names
        • Fills NULL values with sensible defaults
        • Trims whitespace from text columns
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
                "uri",
            ]
        )

        # Rename country code column
        .withColumnRenamed(
            "country",
            "market",
        )

        # Add readable country name
        .withColumn(
            "country_name",
            mapping_expr[col("market")],
        )

        # Replace NULL values
        .fillna({
            "artist_names": "Unknown Artist",
            "track_name": "Unknown Track",
            "label": "Independent",
        })

        # Trim artist names
        .withColumn(
            "artist_names",
            trim(col("artist_names")),
        )
        .withColumn("track_name", trim(col("track_name")))
        .withColumn("label", trim(col("label")))
    )

    logger.info("Initial cleaning completed.")

    return silver_song_charts

# =============================================================================
# Transform: Feature Engineering
# =============================================================================

def feature_engineering(silver_song_charts: DataFrame) -> DataFrame:
    """
    Creates analytical features for the Silver Song Charts table:
        • Time intelligence (year, month, quarter, week)
        • Hit classification
        • Standardized label
        • Chart strength score
    """

    logger.info("Creating analytical features...")

    silver_song_charts = (

        silver_song_charts

        # --------------------------------------------------------
        # Time Intelligence
        # --------------------------------------------------------

        .withColumn(
            "year",
            year(col("date")),
        )

        .withColumn(
            "month",
            month(col("date")),
        )

        .withColumn(
            "quarter",
            quarter(col("date")),
        )

        .withColumn(
            "week",
            weekofyear(col("date")),
        )

        # --------------------------------------------------------
        # Hit Classification
        # --------------------------------------------------------

        .withColumn(

            "hit_category",

            when(
                col("rank") <= 10,
                "Global Hit",
            )

            .when(
                col("rank") <= 50,
                "Major Hit",
            )

            .when(
                col("rank") <= 100,
                "Popular Track",
            )

            .otherwise(
                "Charting Track",
            ),
        )

        # --------------------------------------------------------
        # Standardized Label
        # --------------------------------------------------------

        .withColumn(
            "standardized_label",
            initcap(
                lower(
                    trim(col("label")),
                ),
            ),
        )

        # --------------------------------------------------------
        # Chart Strength Score
        # --------------------------------------------------------

        .withColumn(
            "chart_strength_score",
            round(
                (
                    ((201 - col("rank")) * 0.4)
                    + ((201 - col("peak_rank")) * 0.3)
                    + (col("days_on_chart") * 0.2)
                    + (col("consecutive_days") * 0.1)
                ),
                2,
            ),
        )

    )

    logger.info("Feature engineering completed.")

    return silver_song_charts

# =============================================================================
# Load: Write Silver Song Charts
# =============================================================================

def write_song_charts(silver_song_charts: DataFrame, silver_song_path: str) -> None:
    """
    Writes the Silver Song Charts dataset to Amazon S3, partitioned by
    year and country_name.
    """

    logger.info("Writing Silver Song Charts to: %s", silver_song_path)

    (
        silver_song_charts
        .repartition(
            60,
            "year",
            "country_name",
        )
        .write
        .mode("overwrite")
        .partitionBy(
            "year",
            "country_name",
        )
        .option("compression", "snappy")
        .parquet(silver_song_path)
    )

    logger.info("Silver Song Charts written successfully.")

# =============================================================================
# Main ETL Pipeline
# =============================================================================

def run_etl(spark: SparkSession, input_path: str, output_bucket: str) -> None:
    """
    Orchestrates the full Bronze -> Silver ETL pipeline:
        Extract -> Clean -> Feature Engineer -> Load
    """

    silver_song_path = f"{output_bucket.rstrip('/')}/song_charts/"

    # ---- Extract ----
    bronze_song_charts = read_bronze(spark, input_path)

    # ---- Transform ----
    silver_song_charts = clean_song_charts(bronze_song_charts)
    silver_song_charts = feature_engineering(silver_song_charts)

    # ---- Load ----
    write_song_charts(silver_song_charts, silver_song_path)


def main():

    args = parse_args()

    logger.info("=" * 80)
    logger.info("Spotify Bronze to Silver ETL Started")
    logger.info("Input path   : %s", args.input_path)
    logger.info("Output bucket: %s", args.output_bucket)
    logger.info("=" * 80)

    spark = get_spark_session()

    try:

        run_etl(
            spark=spark,
            input_path=args.input_path,
            output_bucket=args.output_bucket,
        )

        logger.info("=" * 80)
        logger.info("Spotify Bronze to Silver ETL Completed Successfully")
        logger.info("=" * 80)

    except Exception:

        logger.exception("Spotify Bronze to Silver ETL Failed.")
        raise

    finally:

        spark.stop()
        logger.info("Spark Session Stopped.")

# =============================================================================
# Driver
# =============================================================================

if __name__ == "__main__":
    main()
