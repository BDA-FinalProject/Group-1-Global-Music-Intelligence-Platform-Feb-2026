"""
===============================================================================
Project     : Spotify Big Data Project
Module      : config.py
Description : Central configuration file for the Spotify Ingestion Pipeline.

Author      : Shrirang Awaghad
Created On  : 26-07-2026

Notes:
- AWS authentication is handled automatically through the aws configure.
- Kaggle authentication uses environment variables:
      KAGGLE_USERNAME
      KAGGLE_KEY
- No credentials are stored in this file.
===============================================================================
"""

# =============================================================================
# APPLICATION INFORMATION
# =============================================================================

APPLICATION_NAME = "Spotify Ingestion Pipeline"
APPLICATION_VERSION = "1.0.0"

# =============================================================================
# AWS CONFIGURATION
# =============================================================================

AWS_REGION = "us-east-1"

# Destination S3 Bucket
S3_BUCKET_NAME = "spotify-bronze-bucket"

# Folder inside the bucket
S3_FOLDER = "bronze"

# =============================================================================
# KAGGLE CONFIGURATION
# =============================================================================

# Kaggle Dataset
KAGGLE_DATASET = "gonzalopezgil/spotify-charts-daily-updated"

# =============================================================================
# LOCAL DIRECTORY STRUCTURE
# =============================================================================

# Root working directory
ROOT_DIRECTORY = "."

# Stores the downloaded Kaggle ZIP
RAW_DOWNLOAD_DIRECTORY = "downloads/raw"

# Stores extracted CSV / CSV.GZ files
EXTRACTED_DIRECTORY = "downloads/extracted"

# Application logs
LOG_DIRECTORY = "logs"

# =============================================================================
# FILE CONFIGURATION
# =============================================================================

# Kaggle downloads are ZIP archives
ZIP_EXTENSION = ".zip"

# Supported file types after extraction
SUPPORTED_FILE_TYPES = (
    ".csv",
    ".csv.gz",
)

# Delete ZIP after extraction
DELETE_ZIP_AFTER_EXTRACTION = False

# Overwrite downloaded ZIP if it already exists
OVERWRITE_EXISTING_DOWNLOAD = True

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

LOG_FILE_NAME = "spotify_ingestion.log"

LOG_LEVEL = "INFO"

LOG_FORMAT = (
    "%(asctime)s | "
    "%(levelname)s | "
    "%(filename)s | "
    "%(message)s"
)
