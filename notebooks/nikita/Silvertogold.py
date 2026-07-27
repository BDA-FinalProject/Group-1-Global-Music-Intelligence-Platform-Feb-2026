"""
===============================================================================
Spotify Global Music Intelligence Platform
Silver -> Gold Layer ETL Job

Platform    : AWS EMR
Storage     : Amazon S3
Engine      : Apache Spark

Description
-----------
Reads the Spotify Silver layer song_charts dataset from Amazon S3
(bucket: bronzespotify) and builds five curated Gold layer analytics
tables by performing:

    • KPI / Dashboard summary aggregation
    • Country performance aggregation (market share, growth %,
      top artist, top label, catalog hit rate)
    • Monthly trend aggregation
    • Label performance aggregation (market share, catalog hit rate)
    • Artist performance aggregation (catalog hit rate, avg chart
      strength, countries reached)

Inputs
------
1. s3://bronzespotify/silver/song_charts/

Outputs
-------
1. s3://goldlayerscript/gold/dashboard_summary/
2. s3://goldlayerscript/gold/country_performance/
3. s3://goldlayerscript/gold/monthly_trends/
4. s3://goldlayerscript/gold/label_performance/
5. s3://goldlayerscript/gold/artist_performance/

Usage
-----
    spark-submit spotify_silver_to_gold_etl.py
    spark-submit spotify_silver_to_gold_etl.py \
        --input-path s3://bronzespotify/silver/song_charts/ \
        --output-bucket s3://goldlayerscript
===============================================================================
"""

# =============================================================================
# Imports
# =============================================================================

import argparse
import logging

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    arrays_zip,
    asc,
    avg,
    col,
    concat_ws,
    countDistinct,
    date_format,
    desc,
    explode,
    lag,
    lit,
    round,
    row_number,
    split,
    sum as spark_sum,
    to_date,
    trim,
    when,
)
from pyspark.sql.window import Window

# =============================================================================
# Logger
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("spotify_silver_to_gold_etl")

# =============================================================================
# Default S3 Paths
# =============================================================================

DEFAULT_SILVER_SONG_PATH = "s3://bronzespotify/silver/song_charts/"

DEFAULT_GOLD_BUCKET = "s3://goldlayerscript"

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
        description="Spotify Silver -> Gold ETL Job"
    )

    parser.add_argument(
        "--input-path",
        type=str,
        default=DEFAULT_SILVER_SONG_PATH,
        help="S3 path to the Silver song_charts parquet dataset.",
    )

    parser.add_argument(
        "--output-bucket",
        type=str,
        default=DEFAULT_GOLD_BUCKET,
        help="S3 bucket (e.g. s3://goldlayerscript) that will hold the Gold output.",
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
        .appName("Spotify Silver to Gold ETL")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.shuffle.partitions", "200")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    return spark

# =============================================================================
# Extract: Read Silver Layer
# =============================================================================

def read_silver(spark: SparkSession, silver_song_path: str) -> DataFrame:
    """
    Reads the Silver song_charts dataset from S3.
    """

    logger.info("Reading Silver dataset from: %s", silver_song_path)

    gold_song_charts = spark.read.parquet(silver_song_path)

    record_count = gold_song_charts.count()

    logger.info(
        "Silver dataset loaded successfully. Rows: %s | Columns: %s",
        record_count,
        len(gold_song_charts.columns),
    )

    if record_count == 0:
        raise ValueError(
            f"Silver dataset at {silver_song_path} is empty. Aborting ETL."
        )

    return gold_song_charts

# =============================================================================
# Shared Helper: Exploded Artist URIs
# =============================================================================

def explode_artist_uris(gold_song_charts: DataFrame, group_cols: list) -> DataFrame:
    """
    Explodes the pipe-delimited artist_uris column into one row per
    artist_uri, trims whitespace, drops blanks, and returns distinct
    active-artist counts grouped by the given columns.
    """

    return (
        gold_song_charts
        .select(
            *group_cols,
            explode(split(col("artist_uris"), "\\|")).alias("artist_uri"),
        )
        .withColumn(
            "artist_uri",
            trim(col("artist_uri")),
        )
        .filter(col("artist_uri") != "")
        .groupBy(*group_cols)
        .agg(
            countDistinct("artist_uri").alias("active_artists"),
        )
    )

# =============================================================================
# Transform: Gold - Dashboard Summary
# =============================================================================

def build_dashboard_summary(gold_song_charts: DataFrame) -> DataFrame:
    """
    Builds the monthly KPI dashboard summary:
        total streams, active songs, active artists, active labels,
        countries covered, hit songs, and catalog hit rate.
    """

    logger.info("Building dashboard_summary...")

    # KPI Aggregation
    dashboard_summary = (
        gold_song_charts
        .groupBy("year", "month")
        .agg(
            spark_sum("streams").alias("total_streams"),

            countDistinct("uri").alias("active_songs"),

            countDistinct("standardized_label").alias("active_labels"),

            countDistinct("country_name").alias("countries_covered"),

            countDistinct(
                when(
                    col("hit_category").isin("Global Hit", "Major Hit"),
                    col("uri"),
                )
            ).alias("hit_songs"),
        )
    )

    # Artist Aggregation
    artist_summary = explode_artist_uris(gold_song_charts, ["year", "month"])

    # Join Both Tables
    dashboard_summary = (
        dashboard_summary
        .join(
            artist_summary,
            ["year", "month"],
            "left",
        )
    )

    # Catalog Hit Rate
    dashboard_summary = (
        dashboard_summary
        .withColumn(
            "catalog_hit_rate",
            round(
                (
                    col("hit_songs")
                    / col("active_songs")
                ) * 100,
                2,
            ),
        )
    )

    # Order the Data
    dashboard_summary = (
        dashboard_summary
        .orderBy("year", "month")
    )

    # Year-Month Label
    dashboard_summary = dashboard_summary.withColumn(
        "year_month",
        date_format(
            to_date(
                concat_ws("-", col("year"), col("month"), lit(1))
            ),
            "MMM yyyy",
        ),
    )

    # Final Column Order
    dashboard_summary = dashboard_summary.select(
        "year",
        "month",
        "year_month",
        "total_streams",
        "active_songs",
        "active_artists",
        "active_labels",
        "countries_covered",
        "hit_songs",
        "catalog_hit_rate",
    )

    logger.info("dashboard_summary built successfully.")

    return dashboard_summary

# =============================================================================
# Transform: Gold - Country Performance
# =============================================================================

def build_country_performance(gold_song_charts: DataFrame) -> DataFrame:
    """
    Builds country-level performance metrics:
        total streams, market share, month-over-month growth %,
        catalog hit rate, active songs/artists/labels, top artist,
        and top label per country per month.
    """

    logger.info("Building country_performance...")

    # Aggregate Country Metrics
    country_summary = (
        gold_song_charts
        .groupBy(
            "year",
            "month",
            "country_name",
        )
        .agg(
            spark_sum("streams").alias("total_streams"),

            countDistinct("uri").alias("active_songs"),

            countDistinct("standardized_label").alias("active_labels"),
        )
    )

    # Active Artists
    country_artists = explode_artist_uris(
        gold_song_charts, ["year", "month", "country_name"]
    )

    # Market Share
    monthly_streams = (
        country_summary
        .groupBy(
            "year",
            "month",
        )
        .agg(
            spark_sum("total_streams").alias("monthly_streams"),
        )
    )

    country_summary = (
        country_summary
        .join(
            monthly_streams,
            ["year", "month"],
        )
    )

    country_summary = (
        country_summary
        .withColumn(
            "market_share",
            round(
                col("total_streams")
                / col("monthly_streams")
                * 100,
                2,
            ),
        )
    )

    # Join Active Artists
    country_summary = (
        country_summary
        .join(
            country_artists,
            [
                "year",
                "month",
                "country_name",
            ],
            "left",
        )
    )

    # Aggregate Artist Streams (for top artist)
    artist_streams = (
        gold_song_charts
        .groupBy(
            "year",
            "month",
            "country_name",
            "artist_names",
        )
        .agg(
            spark_sum("streams").alias("artist_streams"),
        )
    )

    # Window Specification - Top Artist
    artist_window = Window.partitionBy(
        "year",
        "month",
        "country_name",
    ).orderBy(
        desc("artist_streams"),
        asc("artist_names"),  # tie-breaker
    )

    # Rank + Rename
    top_artist = (
        artist_streams
        .withColumn(
            "rn",
            row_number().over(artist_window),
        )
        .filter(col("rn") == 1)
        .drop("rn")
        .withColumnRenamed(
            "artist_names",
            "top_artist",
        )
    )

    # Aggregate Label Streams (for top label)
    label_streams = (
        gold_song_charts
        .groupBy(
            "year",
            "month",
            "country_name",
            "standardized_label",
        )
        .agg(
            spark_sum("streams").alias("label_streams"),
        )
    )

    # Window Specification - Top Label
    label_window = Window.partitionBy(
        "year",
        "month",
        "country_name",
    ).orderBy(
        desc("label_streams"),
        asc("standardized_label"),
    )

    # Rank + Rename
    top_label = (
        label_streams
        .withColumn(
            "rn",
            row_number().over(label_window),
        )
        .filter(col("rn") == 1)
        .drop("rn")
        .withColumnRenamed(
            "standardized_label",
            "top_label",
        )
    )

    # Merge Everything
    country_performance = (
        country_summary
        .join(
            top_artist.select(
                "year",
                "month",
                "country_name",
                "top_artist",
            ),
            ["year", "month", "country_name"],
            "left",
        )
        .join(
            top_label.select(
                "year",
                "month",
                "country_name",
                "top_label",
            ),
            ["year", "month", "country_name"],
            "left",
        )
    )

    country_performance = country_performance.drop("monthly_streams")

    # Growth % - Window over Country ordered by time
    growth_window = (
        Window
        .partitionBy("country_name")
        .orderBy("year", "month")
    )

    # Get Previous Month Streams
    country_performance = (
        country_performance
        .withColumn(
            "previous_month_streams",
            lag("total_streams").over(growth_window),
        )
    )

    # Calculate Growth %
    country_performance = (
        country_performance
        .withColumn(
            "growth_percentage",
            round(
                (
                    (col("total_streams") - col("previous_month_streams"))
                    / col("previous_month_streams")
                ) * 100,
                2,
            ),
        )
    )

    # Handle First Month: the first record for each country has no
    # previous month, so growth_percentage will be NULL.
    country_performance = (
        country_performance
        .fillna(
            {"growth_percentage": 0.0}
        )
    )

    # Clean Up
    country_performance = (
        country_performance
        .drop("previous_month_streams")
    )

    # Calculate Country Hit Counts
    country_hits = (
        gold_song_charts
        .groupBy(
            "year",
            "month",
            "country_name",
        )
        .agg(
            countDistinct(
                when(
                    col("hit_category").isin("Global Hit", "Major Hit"),
                    col("uri"),
                )
            ).alias("hit_songs"),
        )
    )

    # Join + Catalog Hit Rate
    country_performance = (
        country_performance
        .join(
            country_hits,
            ["year", "month", "country_name"],
            "left",
        )
        .fillna({"hit_songs": 0})
        .withColumn(
            "catalog_hit_rate",
            round(
                col("hit_songs")
                / col("active_songs")
                * 100,
                2,
            ),
        )
        .drop("hit_songs")
    )

    # Year-Month Label
    country_performance = (
        country_performance
        .withColumn(
            "year_month",
            date_format(
                to_date(
                    concat_ws("-", col("year"), col("month"), lit(1))
                ),
                "MMM yyyy",
            ),
        )
    )

    # Final Column Order
    country_performance = country_performance.select(
        "year",
        "month",
        "year_month",
        "country_name",
        "total_streams",
        "market_share",
        "growth_percentage",
        "catalog_hit_rate",
        "active_songs",
        "active_artists",
        "active_labels",
        "top_artist",
        "top_label",
    )

    logger.info("country_performance built successfully.")

    return country_performance

# =============================================================================
# Transform: Gold - Monthly Trends
# =============================================================================

def build_monthly_trends(gold_song_charts: DataFrame) -> DataFrame:
    """
    Builds global monthly trend metrics:
        total streams, active songs, active artists, active labels.
    """

    logger.info("Building monthly_trends...")

    # Monthly Aggregation
    monthly_trends = (
        gold_song_charts
        .groupBy(
            "year",
            "month",
        )
        .agg(
            spark_sum("streams").alias("total_streams"),

            countDistinct("uri").alias("active_songs"),

            countDistinct("standardized_label").alias("active_labels"),
        )
    )

    # Active Artists
    monthly_artists = explode_artist_uris(gold_song_charts, ["year", "month"])

    # Join
    monthly_trends = (
        monthly_trends
        .join(
            monthly_artists,
            ["year", "month"],
            "left",
        )
    )

    # Year-Month Label
    monthly_trends = (
        monthly_trends
        .withColumn(
            "year_month",
            date_format(
                to_date(
                    concat_ws("-", col("year"), col("month"), lit(1))
                ),
                "MMM yyyy",
            ),
        )
    )

    # Final Column Order
    monthly_trends = (
        monthly_trends.select(
            "year",
            "month",
            "year_month",
            "total_streams",
            "active_songs",
            "active_artists",
            "active_labels",
        )
    )

    logger.info("monthly_trends built successfully.")

    return monthly_trends

# =============================================================================
# Transform: Gold - Label Performance
# =============================================================================

def build_label_performance(gold_song_charts: DataFrame) -> DataFrame:
    """
    Builds label-level performance metrics:
        total streams, market share, catalog hit rate, active songs,
        and active artists per label per month.
    """

    logger.info("Building label_performance...")

    # Aggregate Label Metrics
    label_summary = (
        gold_song_charts
        .groupBy(
            "year",
            "month",
            "standardized_label",
        )
        .agg(
            spark_sum("streams").alias("total_streams"),

            countDistinct("uri").alias("active_songs"),
        )
    )

    # Active Artists
    label_artists = explode_artist_uris(
        gold_song_charts, ["year", "month", "standardized_label"]
    )

    # Market Share
    monthly_label_streams = (
        label_summary
        .groupBy("year", "month")
        .agg(
            spark_sum("total_streams").alias("monthly_streams"),
        )
    )

    label_summary = (
        label_summary
        .join(monthly_label_streams, ["year", "month"])
        .withColumn(
            "market_share",
            round(
                col("total_streams")
                / col("monthly_streams")
                * 100,
                2,
            ),
        )
        .drop("monthly_streams")
    )

    # Catalog Hit Rate
    label_hits = (
        gold_song_charts
        .groupBy(
            "year",
            "month",
            "standardized_label",
        )
        .agg(
            countDistinct(
                when(
                    col("hit_category").isin("Global Hit", "Major Hit"),
                    col("uri"),
                )
            ).alias("hit_songs"),
        )
    )

    # Final Join
    label_performance = (
        label_summary
        .join(
            label_artists,
            ["year", "month", "standardized_label"],
            "left",
        )
        .join(
            label_hits,
            ["year", "month", "standardized_label"],
            "left",
        )
        .fillna({"hit_songs": 0})
        .withColumn(
            "catalog_hit_rate",
            round(
                col("hit_songs")
                / col("active_songs")
                * 100,
                2,
            ),
        )
        .drop("hit_songs")
    )

    # Year-Month Label
    label_performance = (
        label_performance
        .withColumn(
            "year_month",
            date_format(
                to_date(
                    concat_ws("-", col("year"), col("month"), lit(1))
                ),
                "MMM yyyy",
            ),
        )
    )

    # Final Column Order
    label_performance = label_performance.select(
        "year",
        "month",
        "year_month",
        "standardized_label",
        "total_streams",
        "market_share",
        "catalog_hit_rate",
        "active_songs",
        "active_artists",
    )

    logger.info("label_performance built successfully.")

    return label_performance

# =============================================================================
# Transform: Gold - Artist Performance
# =============================================================================

def build_artist_performance(gold_song_charts: DataFrame) -> DataFrame:
    """
    Builds artist-level performance metrics:
        total streams, active songs, countries reached, average chart
        strength score, and catalog hit rate per artist per month.
    """

    logger.info("Building artist_performance...")

    # Explode artist_uris + artist_names in lockstep (zipped, not a
    # cross join) so each artist row keeps its own URI/name pairing.
    artist_data = (
        gold_song_charts
        .select(
            "year",
            "month",
            "country_name",
            "uri",
            "streams",
            "chart_strength_score",
            "hit_category",
            arrays_zip(
                split(col("artist_uris"), "\\|"),
                split(col("artist_names"), "\\|"),
            ).alias("artists"),
        )
        .withColumn(
            "artist",
            explode(col("artists")),
        )
        .withColumn("artist_uri", trim(col("artist.0")))
        .withColumn("artist_name", trim(col("artist.1")))
        .drop("artists", "artist")
    )

    # Aggregate Artist Metrics
    artist_summary = (
        artist_data
        .groupBy(
            "year",
            "month",
            "artist_uri",
            "artist_name",
        )
        .agg(
            spark_sum("streams").alias("total_streams"),

            countDistinct("uri").alias("active_songs"),

            countDistinct("country_name").alias("countries_reached"),

            round(
                avg("chart_strength_score"),
                2,
            ).alias("avg_chart_strength"),
        )
    )

    # Hit Songs
    artist_hits = (
        artist_data
        .groupBy(
            "year",
            "month",
            "artist_uri",
            "artist_name",
        )
        .agg(
            countDistinct(
                when(
                    col("hit_category").isin("Global Hit", "Major Hit"),
                    col("uri"),
                )
            ).alias("hit_songs"),
        )
    )

    # Final Join
    artist_performance = (
        artist_summary
        .join(
            artist_hits,
            [
                "year",
                "month",
                "artist_uri",
                "artist_name",
            ],
            "left",
        )
        .fillna({"hit_songs": 0})
        .withColumn(
            "catalog_hit_rate",
            round(
                col("hit_songs")
                / col("active_songs")
                * 100,
                2,
            ),
        )
        .drop("hit_songs")
    )

    # Year-Month Label
    artist_performance = (
        artist_performance
        .withColumn(
            "year_month",
            date_format(
                to_date(
                    concat_ws("-", col("year"), col("month"), lit(1))
                ),
                "MMM yyyy",
            ),
        )
    )

    # Final Column Order
    artist_performance = artist_performance.select(
        "year",
        "month",
        "year_month",
        "artist_uri",
        "artist_name",
        "total_streams",
        "active_songs",
        "countries_reached",
        "catalog_hit_rate",
        "avg_chart_strength",
    )

    logger.info("artist_performance built successfully.")

    return artist_performance

# =============================================================================
# Load: Generic Gold Table Writer
# =============================================================================

def write_gold_table(
    df: DataFrame,
    output_path: str,
    partition_by: str = None,
    coalesce_to_one: bool = False,
) -> None:
    """
    Writes a Gold table to Amazon S3 as Snappy-compressed Parquet,
    optionally partitioned and/or coalesced to a single file (used for
    the smaller dashboard_summary / monthly_trends tables so they load
    as a single BI-friendly file).
    """

    logger.info("Writing Gold table to: %s", output_path)

    writer = df

    if coalesce_to_one:
        writer = writer.coalesce(1)

    writer = (
        writer
        .write
        .mode("overwrite")
        .option("compression", "snappy")
    )

    if partition_by:
        writer = writer.partitionBy(partition_by)

    writer.parquet(output_path)

    logger.info("Gold table written successfully: %s", output_path)

# =============================================================================
# Main ETL Pipeline
# =============================================================================

def run_etl(spark: SparkSession, input_path: str, output_bucket: str) -> None:
    """
    Orchestrates the full Silver -> Gold ETL pipeline:
        Extract -> Build each Gold aggregate -> Load
    """

    output_bucket = output_bucket.rstrip("/")

    gold_dashboard_summary_path = f"{output_bucket}/gold/dashboard_summary/"
    gold_country_performance_path = f"{output_bucket}/gold/country_performance/"
    gold_monthly_trends_path = f"{output_bucket}/gold/monthly_trends/"
    gold_label_performance_path = f"{output_bucket}/gold/label_performance/"
    gold_artist_performance_path = f"{output_bucket}/gold/artist_performance/"

    # ---- Extract ----
    gold_song_charts = read_silver(spark, input_path)

    # ---- Transform + Load: Dashboard Summary ----
    dashboard_summary = build_dashboard_summary(gold_song_charts)
    write_gold_table(
        dashboard_summary,
        gold_dashboard_summary_path,
        coalesce_to_one=True,
    )

    # ---- Transform + Load: Country Performance ----
    country_performance = build_country_performance(gold_song_charts)
    write_gold_table(
        country_performance,
        gold_country_performance_path,
        partition_by="year",
    )

    # ---- Transform + Load: Monthly Trends ----
    monthly_trends = build_monthly_trends(gold_song_charts)
    write_gold_table(
        monthly_trends,
        gold_monthly_trends_path,
        coalesce_to_one=True,
    )

    # ---- Transform + Load: Label Performance ----
    label_performance = build_label_performance(gold_song_charts)
    write_gold_table(
        label_performance,
        gold_label_performance_path,
        partition_by="year",
    )

    # ---- Transform + Load: Artist Performance ----
    artist_performance = build_artist_performance(gold_song_charts)
    write_gold_table(
        artist_performance,
        gold_artist_performance_path,
        partition_by="year",
    )


def main():

    args = parse_args()

    logger.info("=" * 80)
    logger.info("Spotify Silver to Gold ETL Started")
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
        logger.info("Spotify Silver to Gold ETL Completed Successfully")
        logger.info("=" * 80)

    except Exception:

        logger.exception("Spotify Silver to Gold ETL Failed.")
        raise

    finally:

        spark.stop()
        logger.info("Spark Session Stopped.")

# =============================================================================
# Driver
# =============================================================================

if __name__ == "__main__":
    main()