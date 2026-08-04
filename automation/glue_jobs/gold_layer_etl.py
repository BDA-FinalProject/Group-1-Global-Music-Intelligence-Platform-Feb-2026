"""
===============================================================================
Spotify Global Music Intelligence Platform
Gold Layer ETL

Platform    : AWS EMR / AWS Glue
Storage     : Amazon S3
Engine      : Apache Spark

Description
-----------
Reads Spotify Silver layer datasets from Amazon S3 and transforms them into
business-ready Gold layer datasets for analytics and executive dashboards.

Outputs
-------
1. gold/dashboard_summary
2. gold/country_performance
3. gold/monthly_trends
4. gold/label_performance
5. gold/artist_performance
===============================================================================
"""

# =============================================================================
# Imports
# =============================================================================

import logging

from pyspark.sql import SparkSession

from pyspark.sql.functions import (
    arrays_zip,
    avg,
    col,
    concat_ws,
    countDistinct,
    date_format,
    desc,
    explode,
    lag,
    lit,
    max,
    round,
    row_number,
    split,
    sum,
    to_date,
    trim,
    when
)
from pyspark.sql.window import Window

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

SILVER_SONG_PATH = (
    "s3://spotify-lake-dev-data/silver/song_charts/"
)

GOLD_DASHBOARD_SUMMARY_PATH = (
    "s3://spotify-lake-dev-data/gold/dashboard_summary/"
)

GOLD_COUNTRY_PERFORMANCE_PATH = (
    "s3://spotify-lake-dev-data/gold/country_performance/"
)

GOLD_MONTHLY_TRENDS_PATH = (
    "s3://spotify-lake-dev-data/gold/monthly_trends/"
)

GOLD_LABEL_PERFORMANCE_PATH = (
    "s3://spotify-lake-dev-data/gold/label_performance/"
)

GOLD_ARTIST_PERFORMANCE_PATH = (
    "s3://spotify-lake-dev-data/gold/artist_performance/"
)

# =============================================================================
# Read Silver Layer
# =============================================================================

def read_silver():
    """
    Reads the Silver datasets from Amazon S3.
    """

    logger.info("Reading Silver datasets...")

    silver_song_charts = spark.read.parquet(
        SILVER_SONG_PATH
    )

    logger.info("Silver datasets loaded successfully.")

    return silver_song_charts

# =============================================================================
# Dashboard Summary
# =============================================================================

def create_dashboard_summary(silver_song_charts):
    """
    Creates the Dashboard Summary dataset.
    One row per Year-Month.
    """

    logger.info("Creating Dashboard Summary...")

    # -------------------------------------------------------------------------
    # KPI Aggregation
    # -------------------------------------------------------------------------

    dashboard_summary = (

        silver_song_charts

        .groupBy(
            "year",
            "month"
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
                "country_name"
            ).alias(
                "countries_covered"
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
            )
        )
    )

    # -------------------------------------------------------------------------
    # Active Artists
    # -------------------------------------------------------------------------

    artist_summary = (

        silver_song_charts

        .select(
            "year",
            "month",
            explode(
                split(
                    col("artist_uris"),
                    "\\|"
                )
            ).alias("artist_uri")
        )

        .withColumn(
            "artist_uri",
            trim(
                col("artist_uri")
            )
        )

        .filter(
            col("artist_uri") != ""
        )

        .groupBy(
            "year",
            "month"
        )

        .agg(
            countDistinct(
                "artist_uri"
            ).alias(
                "active_artists"
            )
        )
    )

    # -------------------------------------------------------------------------
    # Join
    # -------------------------------------------------------------------------

    dashboard_summary = (
        dashboard_summary
        .join(
            artist_summary,
            [
                "year",
                "month"
            ],
            "left"
        )

    )

    # -------------------------------------------------------------------------
    # Catalog Hit Rate
    # -------------------------------------------------------------------------

    dashboard_summary = (
        dashboard_summary
        .withColumn(
            "catalog_hit_rate",
            round(
                when(
                    col("active_songs") > 0,
                    (
                        col("hit_songs")
                        * 100
                    )
                    /
                    col("active_songs")
                )
                .otherwise(0),
                2
            )
        )
    )
    # -------------------------------------------------------------------------
    # Year Month
    # -------------------------------------------------------------------------
    dashboard_summary = (
        dashboard_summary
        .withColumn(
            "year_month",
            date_format(
                to_date(
                    concat_ws(
                        "-",
                        col("year"),
                        col("month"),
                        lit(1)
                    )
                ),
                "MMM yyyy"
            )
        )
        .select(
            "year",
            "month",
            "year_month",
            "total_streams",
            "active_songs",
            "active_artists",
            "active_labels",
            "countries_covered",
            "hit_songs",
            "catalog_hit_rate"
        )
        .orderBy(
            "year",
            "month"
        )
    )
    logger.info(
        "Dashboard Summary created successfully."
    )
    return dashboard_summary


# =============================================================================
# Write Dashboard Summary
# =============================================================================

def write_dashboard_summary(dashboard_summary):
    """
    Writes the Dashboard Summary dataset to Amazon S3.
    """

    logger.info("Writing Dashboard Summary...")
    (
        dashboard_summary
        .coalesce(1)
        .write
        .mode("overwrite")
        .option(
            "compression",
            "snappy"
        )
        .parquet(
            GOLD_DASHBOARD_SUMMARY_PATH
        )
    )
    logger.info(
        "Dashboard Summary written successfully."
    )

# =============================================================================
# Country Summary
# =============================================================================

def create_country_summary(silver_song_charts):
    """
    Creates the base Country Summary dataset.
    """

    logger.info("Creating Country Summary...")

    # -------------------------------------------------------------------------
    # Country Metrics
    # -------------------------------------------------------------------------

    country_summary = (
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
                "standardized_label"
            ).alias(
                "active_labels"
            ),
            countDistinct(
                when(
                    col("hit_category") == "Global Hit",
                    col("uri")
                )
            ).alias(
                "global_hits"
            ),
            countDistinct(
                when(
                    col("hit_category") == "Major Hit",
                    col("uri")
                )
            ).alias(
                "major_hits"
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

    # -------------------------------------------------------------------------
    # Active Artists
    # -------------------------------------------------------------------------

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
            col("artist_uri") != ""
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

    # -------------------------------------------------------------------------
    # Merge
    # -------------------------------------------------------------------------

    country_summary = (
        country_summary
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
    logger.info(
        "Country Summary created successfully."
    )
    return country_summary

# =============================================================================
# Market Share
# =============================================================================

def calculate_market_share(country_summary):
    """
    Calculates market share for each country by month.
    """

    logger.info("Calculating Market Share...")

    monthly_streams = (
        country_summary
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

    country_summary = (
        country_summary
        .join(
            monthly_streams,
            ["year", "month"],
            "left"
        )
        .withColumn(
            "market_share",
            round(
                (
                    col("total_streams")
                    * 100
                )
                /
                col("monthly_total_streams"),
                2
            )
        )
        .drop(
            "monthly_total_streams"
        )
    )
    logger.info(
        "Market Share calculated successfully."
    )

    return country_summary

# =============================================================================
# Top Artist
# =============================================================================

def get_top_artist(silver_song_charts):
    """
    Retrieves the top artist for each country and month.
    """

    logger.info("Identifying Top Artists...")

    artist_streams = (
        silver_song_charts
        .groupBy(
            "year",
            "month",
            "country_name",
            "artist_names"
        )
        .agg(
            sum("streams").alias(
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
            desc("artist_streams"),
            col("artist_names")
        )
    )

    top_artist = (
        artist_streams
        .withColumn(
            "rn",
            row_number().over(
                artist_window
            )
        )
        .filter(
            col("rn") == 1
        )
        .drop("rn")
        .withColumnRenamed(
            "artist_names",
            "top_artist"
        )
    )
    logger.info(
        "Top Artists identified successfully."
    )
    return top_artist

# =============================================================================
# Top Label
# =============================================================================

def get_top_label(silver_song_charts):
    """
    Retrieves the top label for each country and month.
    """

    logger.info("Identifying Top Labels...")

    label_streams = (
        silver_song_charts
        .groupBy(
            "year",
            "month",
            "country_name",
            "standardized_label"
        )
        .agg(
            sum("streams").alias(
                "label_streams"
            )
        )
    )
    label_window = (
        Window
        .partitionBy(
            "year",
            "month",
            "country_name"
        )
        .orderBy(
            desc("label_streams"),
            col("standardized_label")
        )
    )
    top_label = (
        label_streams
        .withColumn(
            "rn",
            row_number().over(
                label_window
            )
        )
        .filter(
            col("rn") == 1
        )
        .drop("rn")
        .withColumnRenamed(
            "standardized_label",
            "top_label"
        )
    )
    logger.info(
        "Top Labels identified successfully."
    )
    return top_label

# =============================================================================
# Country Performance
# =============================================================================

def create_country_performance(silver_song_charts):
    """
    Creates the Country Performance dataset.
    """

    logger.info("Creating Country Performance...")

    # -------------------------------------------------------------------------
    # Base Summary
    # -------------------------------------------------------------------------

    country_performance = create_country_summary(
        silver_song_charts
    )

    # -------------------------------------------------------------------------
    # Market Share
    # -------------------------------------------------------------------------

    country_performance = calculate_market_share(
        country_performance
    )

    # -------------------------------------------------------------------------
    # Top Artist
    # -------------------------------------------------------------------------

    top_artist = get_top_artist(
        silver_song_charts
    )

    # -------------------------------------------------------------------------
    # Top Label
    # -------------------------------------------------------------------------

    top_label = get_top_label(
        silver_song_charts
    )

    # -------------------------------------------------------------------------
    # Merge
    # -------------------------------------------------------------------------

    country_performance = (
        country_performance
        .join(
            top_artist,
            [
                "country_name",
                "year",
                "month"
            ],
            "left"
        )
        .join(
            top_label,
            [
                "country_name",
                "year",
                "month"
            ],
            "left"
        )
    )

    # -------------------------------------------------------------------------
    # Growth Percentage
    # -------------------------------------------------------------------------

    country_performance = calculate_growth(
        country_performance
    )

    # -------------------------------------------------------------------------
    # Catalog Hit Rate
    # -------------------------------------------------------------------------

    country_performance = calculate_catalog_hit_rate(
        country_performance
    )

    # -------------------------------------------------------------------------
    # Final Formatting
    # -------------------------------------------------------------------------

    country_performance = finalize_country_performance(
        country_performance
    )
    logger.info(
        "Country Performance created successfully."
    )
    return country_performance

# =============================================================================
# Growth Percentage
# =============================================================================

def calculate_growth(country_performance):
    """
    Calculates month-over-month growth percentage.
    """

    logger.info("Calculating Growth Percentage...")

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
                    col("previous_month_streams").isNull()
                    |
                    (col("previous_month_streams") == 0),
                    0
                )
                .otherwise(
                    (
                        (
                            col("total_streams")
                            -
                            col("previous_month_streams")
                        )
                        * 100
                    )
                    /
                    col("previous_month_streams")
                ),
                2
            )
        )
        .drop(
            "previous_month_streams"
        )
    )
    logger.info(
        "Growth Percentage calculated successfully."
    )
    return country_performance

# =============================================================================
# Catalog Hit Rate
# =============================================================================

def calculate_catalog_hit_rate(country_performance):
    """
    Calculates Catalog Hit Rate for each country.
    """

    logger.info("Calculating Catalog Hit Rate...")

    country_performance = (
        country_performance
        .withColumn(
            "catalog_hit_rate",
            round(
                when(
                    col("active_songs") > 0,
                    (
                        (
                            col("global_hits")
                            +
                            col("major_hits")
                        )
                        * 100
                    )
                    /
                    col("active_songs")
                )
                .otherwise(0),
                2
            )
        )
    )
    logger.info(
        "Catalog Hit Rate calculated successfully."
    )
    return country_performance

# =============================================================================
# Finalize Country Performance
# =============================================================================

def finalize_country_performance(country_performance):
    """
    Finalizes the Country Performance dataset.
    """

    logger.info("Finalizing Country Performance...")

    country_performance = (
        country_performance
        .withColumn(
            "year_month",
            date_format(
                to_date(
                    concat_ws(
                        "-",
                        col("year"),
                        col("month"),
                        lit(1)
                    )
                ),
                "MMM yyyy"
            )
        )
        .select(
            "country_name",
            "year",
            "month",
            "year_month",
            "total_streams",
            "market_share",
            "growth_percentage",
            "active_songs",
            "active_artists",
            "active_labels",
            "global_hits",
            "major_hits",
            "catalog_hit_rate",
            "avg_chart_strength",
            "top_artist",
            "top_label"
        )
    )
    logger.info(
        "Country Performance finalized successfully."
    )
    return country_performance

# =============================================================================
# Write Country Performance
# =============================================================================

def write_country_performance(country_performance):
    """
    Writes the Country Performance dataset to Amazon S3.
    """

    logger.info("Writing Country Performance...")

    (
        country_performance
        .repartition(
            24,
            "year"
        )
        .write
        .mode("overwrite")
        .partitionBy(
            "year"
        )
        .option(
            "compression",
            "snappy"
        )
        .parquet(
            GOLD_COUNTRY_PERFORMANCE_PATH
        )
    )
    logger.info(
        "Country Performance written successfully."
    )

# =============================================================================
# Monthly Trends
# =============================================================================

def create_monthly_trends(silver_song_charts):
    """
    Creates the Monthly Trends dataset.
    """

    logger.info("Creating Monthly Trends...")

    # -------------------------------------------------------------------------
    # Monthly Metrics
    # -------------------------------------------------------------------------

    monthly_trends = (
        silver_song_charts
        .groupBy(
            "year",
            "month"
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
            )
        )
    )

    # -------------------------------------------------------------------------
    # Active Artists
    # -------------------------------------------------------------------------

    monthly_artists = (
        silver_song_charts
        .select(
            "year",
            "month",
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
            col("artist_uri") != ""
        )
        .groupBy(
            "year",
            "month"
        )
        .agg(
            countDistinct(
                "artist_uri"
            ).alias(

                "active_artists"
            )
        )
    )

    # -------------------------------------------------------------------------
    # Join
    # -------------------------------------------------------------------------

    monthly_trends = (
        monthly_trends
        .join(
            monthly_artists,
            [
                "year",
                "month"
            ],
            "left"
        )
    )

    # -------------------------------------------------------------------------
    # Year Month
    # -------------------------------------------------------------------------

    monthly_trends = (
        monthly_trends
        .withColumn(
            "year_month",
            date_format(
                to_date(
                    concat_ws(
                        "-",
                        col("year"),
                        col("month"),
                        lit(1)
                    )
                ),
                "MMM yyyy"
            )
        )
        .select(
            "year",
            "month",
            "year_month",
            "total_streams",
            "active_songs",
            "active_artists",
            "active_labels"
        )
        .orderBy(
            "year",
            "month"
        )
    )
    logger.info(
        "Monthly Trends created successfully."
    )
    return monthly_trends


# =============================================================================
# Write Monthly Trends
# =============================================================================

def write_monthly_trends(monthly_trends):
    """
    Writes the Monthly Trends dataset to Amazon S3.
    """

    logger.info("Writing Monthly Trends...")
    (
        monthly_trends
        .coalesce(1)
        .write
        .mode("overwrite")
        .option(
            "compression",
            "snappy"
        )
        .parquet(
            GOLD_MONTHLY_TRENDS_PATH
        )
    )
    logger.info(
        "Monthly Trends written successfully."
    )

# =============================================================================
# Label Performance
# =============================================================================

def create_label_performance(silver_song_charts):
    """
    Creates the Label Performance dataset.
    """

    logger.info("Creating Label Performance...")

    # -------------------------------------------------------------------------
    # Label Metrics
    # -------------------------------------------------------------------------

    label_summary = (
        silver_song_charts
        .groupBy(
            "year",
            "month",
            "standardized_label"
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
            )
        )
    )

    # -------------------------------------------------------------------------
    # Active Artists
    # -------------------------------------------------------------------------

    label_artists = (
        silver_song_charts
        .select(
            "year",
            "month",
            "standardized_label",
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
            col("artist_uri") != ""
        )
        .groupBy(
            "year",
            "month",
            "standardized_label"
        )
        .agg(
            countDistinct(
                "artist_uri"
            ).alias(
                "active_artists"
            )
        )
    )

    # -------------------------------------------------------------------------
    # Market Share
    # -------------------------------------------------------------------------

    monthly_label_streams = (
        label_summary
        .groupBy(
            "year",
            "month"
        )
        .agg(
            sum(
                "total_streams"
            ).alias(
                "monthly_streams"
            )
        )
    )

    label_summary = (
        label_summary
        .join(
            monthly_label_streams,
            [
                "year",
                "month"
            ],
            "left"
        )
        .withColumn(
            "market_share",
            round(
                (
                    col("total_streams")
                    /
                    col("monthly_streams")
                )
                * 100,
                2
            )
        )
        .drop(
            "monthly_streams"
        )
    )

    # -------------------------------------------------------------------------
    # Hit Songs
    # -------------------------------------------------------------------------

    label_hits = (
        silver_song_charts
        .groupBy(
            "year",
            "month",
            "standardized_label"
        )
        .agg(
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
            )
        )
    )

    # -------------------------------------------------------------------------
    # Final Join
    # -------------------------------------------------------------------------

    label_performance = (
        label_summary
        .join(
            label_artists,
            [
                "year",
                "month",
                "standardized_label"
            ],
            "left"
        )
        .join(
            label_hits,
            [
                "year",
                "month",
                "standardized_label"
            ],
            "left"
        )
        .fillna(
            {
                "hit_songs": 0
            }
        )

        .withColumn(
            "catalog_hit_rate",
            round(
                when(
                    col("active_songs") > 0,
                    (
                        col("hit_songs")
                        /
                        col("active_songs")
                    )
                    * 100
                )
                .otherwise(0),
                2
            )
        )
        .drop(
            "hit_songs"
        )
    )

    # -------------------------------------------------------------------------
    # Year Month
    # -------------------------------------------------------------------------

    label_performance = (

        label_performance
        .withColumn(
            "year_month",
            date_format(
                to_date(
                    concat_ws(
                        "-",
                        col("year"),
                        col("month"),
                        lit(1)
                    )
                ),
                "MMM yyyy"
            )
        )
        .select(
            "year",
            "month",
            "year_month",
            "standardized_label",
            "total_streams",
            "market_share",
            "catalog_hit_rate",
            "active_songs",
            "active_artists"
        )
        .orderBy(
            "year",
            "month",
            "standardized_label"
        )
    )
    logger.info(
        "Label Performance created successfully."
    )
    return label_performance

# =============================================================================
# Write Label Performance
# =============================================================================

def write_label_performance(label_performance):
    """
    Writes the Label Performance dataset to Amazon S3.
    """

    logger.info("Writing Label Performance...")
    (
        label_performance
        .coalesce(
            1
        )
        .write
        .mode("overwrite")
        .option(
            "compression",
            "snappy"
        )
        .parquet(
            GOLD_LABEL_PERFORMANCE_PATH
        )
    )
    logger.info(
        "Label Performance written successfully."
    )

# =============================================================================
# Artist Performance
# =============================================================================

def create_artist_performance(silver_song_charts):
    """
    Creates the Artist Performance dataset.
    """

    logger.info("Creating Artist Performance...")

    # -------------------------------------------------------------------------
    # Explode Artists
    # -------------------------------------------------------------------------

    artist_data = (
        silver_song_charts
        .select(
            "year",
            "month",
            "country_name",
            "uri",
            "streams",
            "chart_strength_score",
            "hit_category",
            arrays_zip(
                split(
                    col("artist_uris"),
                    "\\|"
                ),
                split(
                    col("artist_names"),
                    "\\|"
                )
            ).alias(
                "artists"
            )
        )
        .withColumn(
            "artist",
            explode(
                col("artists")
            )
        )
        .withColumn(
            "artist_uri",
            trim(
                col("artist.0")
            )
        )
        .withColumn(
            "artist_name",
            trim(
                col("artist.1")
            )
        )
        .drop(
            "artists",
            "artist"
        )
    )

    # -------------------------------------------------------------------------
    # Artist Metrics
    # -------------------------------------------------------------------------

    artist_summary = (
        artist_data
        .groupBy(
            "year",
            "month",
            "artist_uri",
            "artist_name"
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
                "country_name"
            ).alias(
                "countries_reached"
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

    # -------------------------------------------------------------------------
    # Hit Songs
    # -------------------------------------------------------------------------

    artist_hits = (
        artist_data
        .groupBy(
            "year",
            "month",
            "artist_uri",
            "artist_name"
        )
        .agg(
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
            )
        )
    )

    # -------------------------------------------------------------------------
    # Final Join
    # -------------------------------------------------------------------------

    artist_performance = (
        artist_summary
        .join(
            artist_hits,
            [
                "year",
                "month",
                "artist_uri",
                "artist_name"
            ],
            "left"
        )
        .fillna(
            {
                "hit_songs": 0
            }
        )
        .withColumn(
            "catalog_hit_rate",
            round(
                when(
                    col("active_songs") > 0,
                    (
                        col("hit_songs")
                        /
                        col("active_songs")
                    )
                    * 100
                )
                .otherwise(0),
                2
            )
        )
        .drop(
            "hit_songs"
        )
    )

    # -------------------------------------------------------------------------
    # Year Month
    # -------------------------------------------------------------------------

    artist_performance = (
        artist_performance
        .withColumn(
            "year_month",
            date_format(
                to_date(
                    concat_ws(
                        "-",
                        col("year"),
                        col("month"),
                        lit(1)
                    )
                ),
                "MMM yyyy"
            )
        )
        .select(
            "year",
            "month",
            "year_month",
            "artist_uri",
            "artist_name",
            "total_streams",
            "active_songs",
            "countries_reached",
            "catalog_hit_rate",
            "avg_chart_strength"
        )
        .orderBy(
            "year",
            "month",
            "artist_name"
        )
    )
    logger.info(
        "Artist Performance created successfully."
    )
    return artist_performance

# =============================================================================
# Write Artist Performance
# =============================================================================

def write_artist_performance(artist_performance):
    """
    Writes the Artist Performance dataset to Amazon S3.
    """

    logger.info("Writing Artist Performance...")
    (
        artist_performance
        .coalesce(
            1
        )
        .write
        .mode("overwrite")
        .option(
            "compression",
            "snappy"
        )
        .parquet(
            GOLD_ARTIST_PERFORMANCE_PATH
        )
    )
    logger.info(
        "Artist Performance written successfully."
    )


# =============================================================================
# Main ETL Pipeline
# =============================================================================

def main():
    """
    Executes the complete Gold Layer ETL pipeline.
    """

    logger.info("Starting Gold Layer ETL Pipeline...")

    # -------------------------------------------------------------------------
    # Read Silver Layer
    # -------------------------------------------------------------------------

    silver_song_charts = read_silver()

    # -------------------------------------------------------------------------
    # Dashboard Summary
    # -------------------------------------------------------------------------

    dashboard_summary = create_dashboard_summary(
        silver_song_charts
    )
    write_dashboard_summary(
        dashboard_summary
    )

    # -------------------------------------------------------------------------
    # Country Performance
    # -------------------------------------------------------------------------

    country_performance = create_country_performance(
        silver_song_charts
    )
    write_country_performance(
        country_performance
    )

    # -------------------------------------------------------------------------
    # Monthly Trends
    # -------------------------------------------------------------------------

    monthly_trends = create_monthly_trends(
        silver_song_charts
    )
    write_monthly_trends(
        monthly_trends
    )

    # -------------------------------------------------------------------------
    # Label Performance
    # -------------------------------------------------------------------------

    label_performance = create_label_performance(
        silver_song_charts
    )
    write_label_performance(
        label_performance
    )

    # -------------------------------------------------------------------------
    # Artist Performance
    # -------------------------------------------------------------------------

    artist_performance = create_artist_performance(
        silver_song_charts
    )
    write_artist_performance(
        artist_performance
    )
    logger.info(
        "Gold Layer ETL completed successfully."
    )

# =============================================================================
# Driver
# =============================================================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(
            f"Gold Layer ETL failed: {e}"
        )
        raise

    finally:
        logger.info(
            "Stopping Spark Session..."
        )

        spark.stop()

        logger.info(
            "Spark Session stopped."
        )
