"""
===============================================================================
Spotify Global Music Intelligence Platform
Bronze -> Silver Layer ETL Job

Platform    : AWS EMR
Storage     : Amazon S3
Engine      : Apache Spark

Description
-----------
Reads Spotify Bronze layer data from Amazon S3 (bucket: bronzetosilverspotify)
and transforms it into the Silver layer by performing:

    • Data Cleaning
    • Country Standardization
    • Feature Engineering
    • Artist Mapping
    • Optimized Parquet Writes

Writes the Silver layer output to Amazon S3 (bucket: bronzespotify).

Inputs
------
1. s3://bronzetosilverspotify/charts_songs_daily.parquet

Outputs
-------
1. s3://bronzespotify/silver/song_charts/
2. s3://bronzespotify/silver/artist_mapping/

Usage
-----
    spark-submit spotify_bronze_to_silver_etl.py
    spark-submit spotify_bronze_to_silver_etl.py \
        --input-path s3://bronzetosilverspotify/charts_songs_daily.parquet \
        --output-bucket s3://bronzespotify
===============================================================================
"""

# =============================================================================
# Imports
# =============================================================================

import argparse
import logging
import sys

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    arrays_zip,
    col,
    create_map,
    datediff,
    explode,
    initcap,
    lit,
    lower,
    month,
    quarter,
    regexp_replace,
    round,
    split,
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

DEFAULT_BRONZE_SONG_PATH = "s3://bronzetosilverspotify/charts_songs_daily.parquet"

DEFAULT_SILVER_BUCKET = "s3://bronzespotify"
DEFAULT_SILVER_SONG_PATH = f"{DEFAULT_SILVER_BUCKET}/silver/song_charts/"
DEFAULT_SILVER_ARTIST_PATH = f"{DEFAULT_SILVER_BUCKET}/silver/artist_mapping/"

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
        help="S3 path to the Bronze charts_songs_daily parquet dataset.",
    )

    parser.add_argument(
        "--output-bucket",
        type=str,
        default=DEFAULT_SILVER_BUCKET,
        help="S3 bucket (e.g. s3://bronzespotify) that will hold the Silver output.",
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
    Reads the Bronze charts_songs_daily dataset from S3.
    """

    logger.info("Reading Bronze dataset from: %s", bronze_song_path)

    bronze_song_charts = spark.read.parquet(bronze_song_path)

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
        • Song lifecycle / age category
        • Rank movement and movement category
        • Hit classification
        • Stream tier
        • Standardized label
        • Chart strength score
    """

    logger.info("Creating analytical features...")

    silver_song_charts = (

        silver_song_charts

        # --------------------------------------------------------
        # Valid Release Date
        # --------------------------------------------------------

        .withColumn(
            "valid_release_date",
            when(
                col("release_date") <= col("date"),
                col("release_date"),
            ),
        )

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

        .withColumn(
            "song_age_days",
            datediff(
                col("date"),
                col("valid_release_date"),
            ),
        )

        # --------------------------------------------------------
        # Song Lifecycle
        # --------------------------------------------------------

        .withColumn(

            "song_age_category",

            when(
                col("song_age_days") <= 90,
                "New Release",
            )

            .when(
                col("song_age_days") <= 365,
                "Recent Hit",
            )

            .when(
                col("song_age_days") <= 1825,
                "Established",
            )

            .when(
                col("song_age_days") > 1825,
                "Evergreen",
            )

            .otherwise(
                "Unknown",
            ),
        )

        # --------------------------------------------------------
        # Rank Movement
        # --------------------------------------------------------

        .withColumn(

            "rank_movement",

            when(
                col("previous_rank") > 0,
                col("previous_rank") - col("rank"),
            ),
        )

        .withColumn(

            "movement_category",

            when(
                col("rank_movement").isNull(),
                "New Entry",
            )

            .when(
                col("rank_movement") >= 50,
                "Strong Gainer",
            )

            .when(
                col("rank_movement") > 0,
                "Gainer",
            )

            .when(
                col("rank_movement") == 0,
                "Stable",
            )

            .when(
                col("rank_movement") <= -50,
                "Strong Decliner",
            )

            .otherwise(
                "Decliner",
            ),
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
        # Stream Tier
        # --------------------------------------------------------

        .withColumn(

            "stream_tier",

            when(
                col("streams") >= 10000000,
                "Mega Hit",
            )

            .when(
                col("streams") >= 1000000,
                "Super Hit",
            )

            .when(
                col("streams") >= 100000,
                "High Performer",
            )

            .otherwise(
                "Regular",
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
# Transform: Artist Mapping
# =============================================================================

def create_artist_mapping(silver_song_charts: DataFrame) -> DataFrame:
    """
    Creates the Artist Mapping dimension from the song charts dataset by
    exploding the pipe/comma/semicolon-delimited artist_uris and
    artist_names columns into one row per (uri, artist) pair.
    """

    logger.info("Creating artist mapping...")

    artist_cleaned = (

        silver_song_charts

        .withColumn(
            "artist_names_clean",
            regexp_replace(
                col("artist_names"),
                ",|;",
                "|",
            ),
        )

    )

    silver_artist_mapping = (

        artist_cleaned

        .select(

            "uri",

            explode(

                arrays_zip(

                    split(
                        col("artist_uris"),
                        "\\|",
                    ),

                    split(
                        col("artist_names_clean"),
                        "\\|",
                    ),

                )

            ).alias("artist"),

        )

        .select(

            col("uri"),

            col("artist.0")
            .alias("artist_uri"),

            col("artist.1")
            .alias("artist_name"),

        )

        .withColumn(

            "standardized_artist_name",

            initcap(

                lower(

                    trim(
                        col("artist_name"),
                    ),

                ),

            ),

        )

        .filter(
            col("artist_uri").isNotNull(),
        )

        .dropDuplicates()

    )

    logger.info("Artist mapping created successfully.")

    return silver_artist_mapping

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
# Load: Write Artist Mapping
# =============================================================================

def write_artist_mapping(silver_artist_mapping: DataFrame, silver_artist_path: str) -> None:
    """
    Writes the Artist Mapping dataset to Amazon S3.
    """

    logger.info("Writing Artist Mapping to: %s", silver_artist_path)

    (
        silver_artist_mapping
        .repartition(
            40,
            "artist_uri",
        )
        .write
        .mode("overwrite")
        .option(
            "compression",
            "snappy",
        )
        .parquet(
            silver_artist_path,
        )
    )

    logger.info("Artist Mapping written successfully.")

# =============================================================================
# Main ETL Pipeline
# =============================================================================

def run_etl(spark: SparkSession, input_path: str, output_bucket: str) -> None:
    """
    Orchestrates the full Bronze -> Silver ETL pipeline:
        Extract -> Clean -> Feature Engineer -> Map Artists -> Load
    """

    silver_song_path = f"{output_bucket.rstrip('/')}/silver/song_charts/"
    silver_artist_path = f"{output_bucket.rstrip('/')}/silver/artist_mapping/"

    # ---- Extract ----
    bronze_song_charts = read_bronze(spark, input_path)

    # ---- Transform ----
    silver_song_charts = clean_song_charts(bronze_song_charts)
    silver_song_charts = feature_engineering(silver_song_charts)
    silver_artist_mapping = create_artist_mapping(silver_song_charts)

    # ---- Load ----
    write_song_charts(silver_song_charts, silver_song_path)
    write_artist_mapping(silver_artist_mapping, silver_artist_path)


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