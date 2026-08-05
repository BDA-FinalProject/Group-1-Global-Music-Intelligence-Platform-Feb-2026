"""
Description
-----------
Reads the Spotify Silver layer from Amazon S3 and transforms it into
Gold analytical datasets for business intelligence dashboards.

Current Gold Tables
-------------------
1. KPI Song
2. KPI Artist
3. Country Performance
4. Monthly Trends
5. Label Performance Enhanced

Outputs
-------
1. gold/kpi_song
2. gold/kpi_artist
3. gold/country_performance
4. gold/monthly_trends
5. gold/label_performance_enhanced
"""

# =============================================================================
# Imports
# =============================================================================

import logging

from pyspark.sql import SparkSession

from itertools import chain
from pyspark.sql import Window

from pyspark.sql.functions import (

    arrays_zip,
    asc,
    avg,
    col,
    countDistinct,
    desc,
    explode,
    lag,
    max,
    row_number,
    round,
    split,
    sum,
    trim,
    when,
    coalesce,
    create_map,
    lit

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

    .appName("Spotify Gold ETL")

    .config(
        "spark.sql.adaptive.enabled",
        "true"
    )

    .config(
        "spark.sql.adaptive.coalescePartitions.enabled",
        "true"
    )

    .config(
        "spark.sql.shuffle.partitions",
        "200"
    )

    .config(
        "spark.sql.parquet.compression.codec",
        "snappy"
    )

    .getOrCreate()

)

spark.sparkContext.setLogLevel("WARN")

# =============================================================================
# S3 Paths
# =============================================================================

SILVER_SONG_PATH = ("s3://group-1-dbda/silver/song_charts/")

GOLD_KPI_SONG_PATH = ("s3://group-1-dbda/gold/kpi_song/")

GOLD_KPI_ARTIST_PATH = ("s3://group-1-dbda/gold/kpi_artist/")

GOLD_COUNTRY_PERFORMANCE_PATH = ("s3://group-1-dbda/gold/country_performance/")

GOLD_MONTHLY_TRENDS_PATH = ("s3://group-1-dbda/gold/monthly_trends/")

GOLD_LABEL_PERFORMANCE_PATH = ("s3://group-1-dbda/gold/label_performance_enhanced/")

# =============================================================================
# Read Silver Song Charts
# =============================================================================

def read_silver():
    """
    Reads the Silver Song Charts dataset from Amazon S3.
    """

    logger.info("Reading Silver Song Charts...")
    silver_song_charts = spark.read.parquet(SILVER_SONG_PATH)
    logger.info("Silver Song Charts loaded successfully.")
    return silver_song_charts

# =============================================================================
# Create KPI Song
# =============================================================================

def create_kpi_song(silver_song_charts):
    """
    Creates the Gold KPI Song dataset.
    """

    logger.info("Creating KPI Song dataset...")

    gold_kpi_song = (
        silver_song_charts
        .groupBy(
            "year",
            "month",
            "country_name",
            "uri",
            "standardized_label"
        )
        .agg(
            sum(
                "streams"
            ).alias(
                "total_streams"
            ),
            max(
                when(
                    col("hit_category").isin(
                        "Global Hit",
                        "Major Hit"
                    ),
                    1
                ).otherwise(0)
            ).alias(
                "is_hit"
            )
        )
    )
    logger.info("KPI Song dataset created successfully.")
    return gold_kpi_song

# =============================================================================
# Write KPI Song
# =============================================================================

def write_kpi_song(gold_kpi_song):
    """
    Writes the Gold KPI Song dataset to Amazon S3.
    """

    logger.info("Writing KPI Song dataset...")
    (
        gold_kpi_song
        .repartition(
            20,
            "year",
            "month"
        )
        .write
        .mode(
            "overwrite"
        )
        .option(
            "compression",
            "snappy"
        )
        .partitionBy(
            "year",
            "month"
        )
        .parquet(
            GOLD_KPI_SONG_PATH
        )
    )
    logger.info("KPI Song dataset written successfully.")

# =============================================================================
# Create KPI Artist
# =============================================================================

def create_kpi_artist(silver_song_charts):
    """
    Creates the Gold KPI Artist dataset.
    """

    logger.info("Creating KPI Artist dataset...")

    gold_kpi_artist = (
        silver_song_charts
        .select(
            "year",
            "month",
            "country_name",
            explode(
                split(
                    col("artist_uris"),
                    "\\|"
                )
            ).alias(
                "artist_uri"
            )
        )
        .withColumn(
            "artist_uri",
            trim(
                col("artist_uri")
            )
        )
        .filter(
            (col("artist_uri").isNotNull())
            &
            (col("artist_uri") != "")
        )
        .distinct()
    )
    logger.info("KPI Artist dataset created successfully.")
    return gold_kpi_artist

# =============================================================================
# Write KPI Artist
# =============================================================================

def write_kpi_artist(gold_kpi_artist):
    """
    Writes the Gold KPI Artist dataset to Amazon S3.
    """

    logger.info("Writing KPI Artist dataset...")
    (
        gold_kpi_artist
        .repartition(
            20,
            "year",
            "month"
        )
        .write
        .mode(
            "overwrite"
        )
        .option(
            "compression",
            "snappy"
        )
        .partitionBy(
            "year",
            "month"
        )
        .parquet(
            GOLD_KPI_ARTIST_PATH
        )
    )
    logger.info("KPI Artist dataset written successfully.")


# =============================================================================
# Create Country Performance
# =============================================================================

def create_country_performance(silver_song_charts):
    """
    Creates the Gold Country Performance dataset.
    """

    logger.info("Creating Country Performance dataset...")

    # --------------------------------------------------------
    # Base Country Performance
    # --------------------------------------------------------

    country_performance = (
        silver_song_charts
        .groupBy(
            "year",
            "month",
            "country_name"
        )
        .agg(
            round(
                sum("streams"),
                0
            ).alias(
                "total_streams"
            ),
            countDistinct(
                "uri"
            ).alias(
                "active_songs"
            ),
            countDistinct(
                when(
                    col("hit_category").isin(
                        "Global Hit",
                        "Major Hit"
                    ),
                    col("uri")
                )
            ).alias(
                "hit_songs"
            ),
            round(
                avg(
                    "chart_strength_score"
                ),
                2
            ).alias(
                "avg_chart_strength"
            )
        )
    )
    # --------------------------------------------------------
    # Active Artists
    # --------------------------------------------------------

    country_artists = (
        silver_song_charts
        .select(
            "year",
            "month",
            "country_name",
            explode(
                split(
                    col("artist_uris"),
                    "\\|"
                )
            ).alias(
                "artist_uri"
            )
        )
        .withColumn(
            "artist_uri",
            trim(
                col("artist_uri")
            )
        )
        .filter(
            (col("artist_uri").isNotNull())
            &
            (col("artist_uri") != "")
        )
        .groupBy(
            "year",
            "month",
            "country_name"
        )
        .agg(
            countDistinct(
                "artist_uri"
            ).alias(
                "active_artists"
            )
        )
    )

    country_performance = (
        country_performance
        .join(
            country_artists,
            [
                "year",
                "month",
                "country_name"
            ],
            "left"
        )
    )

    # --------------------------------------------------------
    # Monthly Total Streams
    # --------------------------------------------------------

    monthly_streams = (
        country_performance
        .groupBy(
            "year",
            "month"
        )
        .agg(
            sum(
                "total_streams"
            ).alias(
                "monthly_total_streams"
            )
        )
    )

    country_performance = (
        country_performance
        .join(
            monthly_streams,
            [
                "year",
                "month"
            ],
            "left"
        )
    )

    # --------------------------------------------------------
    # Top Song
    # --------------------------------------------------------

    country_song_streams = (
        silver_song_charts
        .filter(
            col("track_name") != "Unknown Track"
        )
        .groupBy(
            "year",
            "month",
            "country_name",
            "track_name"
        )
        .agg(
            sum(
                "streams"
            ).alias(
                "song_streams"
            )
        )
    )

    song_window = (
        Window
        .partitionBy(
            "year",
            "month",
            "country_name"
        )
        .orderBy(
            desc("song_streams"),
            asc("track_name")
        )
    )
    top_song = (
        country_song_streams
        .withColumn(
            "rank",
            row_number().over(
                song_window
            )
        )
        .filter(
            col("rank") == 1
        )
        .select(
            "year",
            "month",
            "country_name",
            col("track_name").alias(
                "top_song_name"
            )
        )
    )

    country_performance = (
        country_performance
        .join(
            top_song,
            [
                "year",
                "month",
                "country_name"
            ],
            "left"
        )
    )

    # --------------------------------------------------------
    # Top Artist
    # --------------------------------------------------------

    country_artist_streams = (
        silver_song_charts
        .select(
            "year",
            "month",
            "country_name",
            "streams",
            explode(
                arrays_zip(
                    split(
                        col("artist_names"),
                        "\\|"
                    ),
                    split(
                        col("artist_uris"),
                        "\\|"
                    )
                )
            ).alias(
                "artist"
            )
        )
        .select(
            "year",
            "month",
            "country_name",
            "streams",
            trim(
                col("artist.0")
            ).alias(
                "artist_name"
            ),
            trim(
                col("artist.1")
            ).alias(
                "artist_uri"
            )
        )
        .filter(
            col("artist_name") != "Unknown Artist"
        )
        .groupBy(
            "year",
            "month",
            "country_name",
            "artist_name",
            "artist_uri"
        )
        .agg(
            sum(
                "streams"
            ).alias(
                "artist_streams"
            )
        )
    )
    artist_window = (
        Window
        .partitionBy(
            "year",
            "month",
            "country_name"
        )
        .orderBy(
            desc(
                "artist_streams"
            ),
            asc(
                "artist_name"
            )
        )
    )
    top_artist = (
        country_artist_streams
        .withColumn(
            "rank",
            row_number().over(
                artist_window
            )
        )
        .filter(
            col("rank") == 1
        )
        .select(
            "year",
            "month",
            "country_name",
            col(
                "artist_name"
            ).alias(
                "top_artist_name"
            )
        )
    )

    country_performance = (
        country_performance
        .join(
            top_artist,
            [
                "year",
                "month",
                "country_name"
            ],
            "left"
        )
    )

    # --------------------------------------------------------
    # Growth Percentage
    # --------------------------------------------------------

    growth_window = (
        Window
        .partitionBy(
            "country_name"
        )
        .orderBy(
            "year",
            "month"
        )
    )

    country_performance = (
        country_performance
        .withColumn(
            "previous_month_streams",
            lag(
                "total_streams"
            ).over(
                growth_window
            )
        )
        .withColumn(
            "growth_percentage",
            round(
                when(
                    col("previous_month_streams").isNull(),
                    None
                )
                .otherwise(
                    (
                        (
                            col("total_streams")
                            -
                            col("previous_month_streams")
                        )
                        /
                        col("previous_month_streams")
                    ) * 100
                ),
                2
            )
        )
        .drop(
            "previous_month_streams"
        )
    )
    logger.info("Country Performance dataset created successfully.")
    return country_performance

# =============================================================================
# Write Country Performance
# =============================================================================

def write_country_performance(country_performance):
    """
    Writes the Gold Country Performance dataset to Amazon S3.
    """

    logger.info("Writing Country Performance dataset...")
    (
        country_performance
        .repartition(
            20,
            "year"
        )
        .write
        .mode(
            "overwrite"
        )
        .option(
            "compression",
            "snappy"
        )
        .partitionBy(
            "year"
        )
        .parquet(
            GOLD_COUNTRY_PERFORMANCE_PATH
        )
    )
    logger.info("Country Performance dataset written successfully.")

# =============================================================================
# Create Monthly Trends
# =============================================================================

def create_monthly_trends(silver_song_charts):
    """
    Creates the Gold Monthly Trends dataset.
    """

    logger.info("Creating Monthly Trends dataset...")

    # --------------------------------------------------------
    # Monthly Trends
    # --------------------------------------------------------

    monthly_trends = (
        silver_song_charts
        .filter(
            ~(
                (col("year") == 2026)
                &
                (col("month") == 5)
            )
        )
        .groupBy(
            "year",
            "month",
            "country_name"
        )
        .agg(
            round(
                sum("streams"),
                0
            ).alias(
                "total_streams"
            ),
            countDistinct(
                "uri"
            ).alias(
                "active_songs"
            ),
            countDistinct(
                "standardized_label"
            ).alias(
                "active_labels"
            ),
            countDistinct(
                when(
                    col("hit_category").isin(
                        "Global Hit",
                        "Major Hit"
                    ),
                    col("uri")
                )
            ).alias(
                "hit_songs"
            ),
            round(
                avg(
                    "chart_strength_score"
                ),
                2
            ).alias(
                "avg_chart_strength"
            )
        )
    )

    # --------------------------------------------------------
    # Monthly Active Artists
    # --------------------------------------------------------

    monthly_artists = (
        silver_song_charts
        .filter(
            ~(
                (col("year") == 2026)
                &
                (col("month") == 5)
            )
        )
        .select(
            "year",
            "month",
            "country_name",
            explode(
                split(
                    col("artist_uris"),
                    "\\|"
                )
            ).alias(
                "artist_uri"
            )
        )
        .withColumn(
            "artist_uri",
            trim(
                col("artist_uri")
            )
        )
        .filter(
            (col("artist_uri").isNotNull())
            &
            (col("artist_uri") != "")
        )
        .groupBy(
            "year",
            "month",
            "country_name"
        )
        .agg(
            countDistinct(
                "artist_uri"
            ).alias(
                "active_artists"
            )
        )
    )

    # --------------------------------------------------------
    # Merge Active Artists
    # --------------------------------------------------------

    monthly_trends = (
        monthly_trends
        .join(
            monthly_artists,
            [
                "year",
                "month",
                "country_name"
            ],
            "left"
        )
    )

    # --------------------------------------------------------
    # Growth Percentage
    # --------------------------------------------------------

    growth_window = (
        Window
        .partitionBy(
            "country_name"
        )
        .orderBy(
            "year",
            "month"
        )
    )

    monthly_trends = (
        monthly_trends
        .withColumn(
            "previous_month_streams",
            lag(
                "total_streams"
            ).over(
                growth_window
            )
        )
        .withColumn(
            "growth_percentage",
            when(
                (col("previous_month_streams").isNull())
                |
                (col("previous_month_streams") == 0),
                None
            )
            .otherwise(
                round(
                    (
                        (
                            col("total_streams")
                            -
                            col("previous_month_streams")
                        )
                        /
                        col("previous_month_streams")
                    )
                    * 100,
                    2
                )
            )
        )
        .drop(
            "previous_month_streams"
        )
    )
    logger.info("Monthly Trends dataset created successfully.")
    return monthly_trends

# =============================================================================
# Write Monthly Trends
# =============================================================================

def write_monthly_trends(monthly_trends):
    """
    Writes the Gold Monthly Trends dataset to Amazon S3.
    """

    logger.info("Writing Monthly Trends dataset...")
    (
        monthly_trends
        .repartition(
            20,
            "year"
        )
        .write
        .mode(
            "overwrite"
        )
        .option(
            "compression",
            "snappy"
        )
        .partitionBy(
            "year"
        )
        .parquet(GOLD_MONTHLY_TRENDS_PATH)
    )
    logger.info("Monthly Trends dataset written successfully.")

# =============================================================================
# Create Label Performance Enhanced
# =============================================================================

def create_label_performance_enhanced(silver_song_charts):
    """
    Creates the Gold Label Performance Enhanced dataset.
    """

    logger.info("Creating Label Performance Enhanced dataset...")

    # --------------------------------------------------------
    # Label Mapping
    # --------------------------------------------------------

    label_mapping = {
        # Republic Records
        "Taylor Swift": "Republic Records",
        "Lord Huron": "Republic Records",

        # Warner Music India
        "Shubh": "Warner Music India",
        "Diljit Dosanjh": "Warner Music India",

        # Columbia
        "Central Cee": "Columbia",
        "Arizona Zervas": "Columbia",

        # Geffen

        "Olivia Rodrigo Ps": "Geffen",
        # XO / Republic Records
        "The Weeknd/Lyric": "Xo / Republic Records"
    }

    india_mapping = {
        "Ap Dhillon": "Republic Records",
        "Karan Aujla": "Rehaan Records",
        "Ritviz": "Sony Music Entertainment India Pvt. Ltd."
    }

    # --------------------------------------------------------
    # Apply Label Mapping
    # --------------------------------------------------------
    mapping_expr = create_map(
        [
            lit(x)
            for x in chain(*label_mapping.items())
        ]
    )
    mapped_song_charts = (
        silver_song_charts
        .withColumn(
            "standardized_label",
            coalesce(
                mapping_expr[col("standardized_label")],
                col("standardized_label")
            )
        )
    )

    # --------------------------------------------------------
    # Apply India Label Mapping
    # --------------------------------------------------------

    india_mapping_expr = create_map(
        [
            lit(x)
            for x in chain(
                *india_mapping.items()
            )
        ]
    )

    mapped_song_charts = (
        mapped_song_charts
        .withColumn(
            "standardized_label",
            coalesce(
                india_mapping_expr[
                    col("standardized_label")
                ],
                col("standardized_label")
            )
        )
    )
    # --------------------------------------------------------
    # Label Performance Enhanced
    # --------------------------------------------------------

    label_performance_enhanced = (
        mapped_song_charts
        .groupBy(
            "year",
            "month",
            "country_name",
            "standardized_label"
        )
        .agg(
            sum(
                "streams"
            ).alias(
                "total_streams"
            ),
            countDistinct(
                "uri"
            ).alias(
                "active_songs"
            ),
            countDistinct(
                "artist_names"
            ).alias(
                "active_artists"
            )
        )
    )
    logger.info("Label Performance Enhanced dataset created successfully.")
    return label_performance_enhanced

# =============================================================================
# Write Label Performance Enhanced
# =============================================================================

def write_label_performance_enhanced(label_performance_enhanced):
    """
    Writes the Gold Label Performance Enhanced dataset to Amazon S3.
    """

    logger.info("Writing Label Performance Enhanced dataset...")
    (
        label_performance_enhanced
        .repartition(
            20,
            "year"
        )
        .write
        .mode(
            "overwrite"
        )
        .option(
            "compression",
            "snappy"
        )
        .partitionBy(
            "year"
        )
        .parquet(
            GOLD_LABEL_PERFORMANCE_PATH
        )
    )

    logger.info("Label Performance Enhanced dataset written successfully.")


# =============================================================================
# Main ETL Pipeline
# =============================================================================

def main():

    logger.info("=" * 80)
    logger.info("Spotify Gold ETL Started")
    logger.info("=" * 80)

    # --------------------------------------------------------
    # Read Silver Layer
    # --------------------------------------------------------

    silver_song_charts = (
        read_silver()
        .cache()
    )
    silver_song_charts.count()

    # --------------------------------------------------------
    # KPI Song
    # --------------------------------------------------------

    gold_kpi_song = create_kpi_song(silver_song_charts)
    write_kpi_song(gold_kpi_song)

    # --------------------------------------------------------
    # KPI Artist
    # --------------------------------------------------------

    gold_kpi_artist = create_kpi_artist(silver_song_charts)
    write_kpi_artist(gold_kpi_artist)

    # --------------------------------------------------------
    # Country Performance
    # --------------------------------------------------------

    country_performance = create_country_performance(silver_song_charts)
    write_country_performance(country_performance)

    # --------------------------------------------------------
    # Monthly Trends
    # --------------------------------------------------------

    monthly_trends = create_monthly_trends(silver_song_charts)
    write_monthly_trends(monthly_trends)

    # --------------------------------------------------------
    # Label Performance Enhanced
    # --------------------------------------------------------

    label_performance_enhanced = (create_label_performance_enhanced(silver_song_charts))
    write_label_performance_enhanced(label_performance_enhanced)

    silver_song_charts.unpersist()

    logger.info("=" * 80)
    logger.info("Spotify Gold ETL Completed Successfully")
    logger.info("=" * 80)



# =============================================================================
# Driver
# =============================================================================

if __name__ == "__main__":
    try:
        main()

    except Exception:
        logger.exception("Spotify Gold ETL Failed.")
        raise

    finally:
        spark.stop()
        logger.info("Spark Session Stopped.")