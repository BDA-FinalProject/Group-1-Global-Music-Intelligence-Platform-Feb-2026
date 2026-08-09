"""
Description
-----------
Reads Spotify Bronze layer data from Amazon S3 and transforms it into the
Silver layer by performing:

• Data Cleaning
• Country Standardization
• Feature Engineering
• Optimized Parquet Writes

Outputs
-------
1. silver/song_charts
"""

# =============================================================================
# Imports
# =============================================================================

import logging

from pyspark.sql import SparkSession
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
    when,
    year,
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

BRONZE_SONG_PATH = ("s3://group-1-dbda/bronze/charts_songs_daily.parquet")
SILVER_SONG_PATH = ("s3://group-1-dbda/silver/song_charts/")

# =============================================================================
# Read Bronze Layer
# =============================================================================

def read_bronze():
    """
    Reads the Bronze charts_songs_daily dataset from S3.
    """

    logger.info("Reading Bronze dataset...")

    bronze_song_charts = spark.read.parquet(
        BRONZE_SONG_PATH
    )

    logger.info("Bronze dataset loaded successfully.")

    return bronze_song_charts

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
    Writes the Silver Song Charts dataset to Amazon S3.
    """

    logger.info("Writing Silver Song Charts...")

    (
        silver_song_charts
        .repartition(
            60,
            "year",
            "month"
        )
        .write
        .mode("overwrite")
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

    bronze_song_charts = read_bronze()
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

    except Exception:
        logger.exception("Spotify Silver ETL Failed.")
        raise

    finally:
        spark.stop()
        logger.info("Spark Session Stopped.")