"""
===============================================================================
Project     : Spotify Big Data Project
Module      : main.py
Description : Entry point for the Spotify Dataset Ingestion Pipeline.

Author      : Shrirang Awaghad
Created On  : 23-07-2026

Workflow:
1. Download dataset from Kaggle.
2. Extract dataset.
3. Upload extracted files to Amazon S3.
4. Generate ingestion summary.
===============================================================================
"""

from downloader import KaggleDownloader
from extractor import DatasetExtractor
from logger import get_logger
from uploader import S3Uploader
import config


logger = get_logger()


def run_pipeline():
    """
    Executes the complete ingestion pipeline.
    """

    logger.info("=" * 80)
    logger.info(f"{config.APPLICATION_NAME} Started")
    logger.info("=" * 80)

    ingestion_summary = {
        "dataset": config.KAGGLE_DATASET,
        "zip_file": None,
        "files_extracted": 0,
        "files_uploaded": 0,
        "uploaded_files": [],
        "status": "SUCCESS",
        "error": None
    }

    try:

        # -------------------------------------------------------------
        # Download Dataset
        # -------------------------------------------------------------
        downloader = KaggleDownloader()

        zip_file_path = downloader.download_dataset()

        ingestion_summary["zip_file"] = zip_file_path

        # -------------------------------------------------------------
        # Extract Dataset
        # -------------------------------------------------------------
        extractor = DatasetExtractor()

        extracted_files = extractor.extract_dataset(zip_file_path)

        ingestion_summary["files_extracted"] = len(extracted_files)

        # -------------------------------------------------------------
        # Upload Files
        # -------------------------------------------------------------
        uploader = S3Uploader()

        uploaded_files = uploader.upload_files(extracted_files)

        ingestion_summary["files_uploaded"] = len(uploaded_files)

        ingestion_summary["uploaded_files"] = uploaded_files

        logger.info("=" * 80)
        logger.info("INGESTION PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)

    except Exception as error:

        ingestion_summary["status"] = "FAILED"

        ingestion_summary["error"] = str(error)

        logger.exception("Pipeline execution failed.")

    finally:

        logger.info("")
        logger.info("=" * 80)
        logger.info("INGESTION SUMMARY")
        logger.info("=" * 80)

        logger.info(f"Dataset           : {ingestion_summary['dataset']}")
        logger.info(f"ZIP File          : {ingestion_summary['zip_file']}")
        logger.info(f"Files Extracted   : {ingestion_summary['files_extracted']}")
        logger.info(f"Files Uploaded    : {ingestion_summary['files_uploaded']}")
        logger.info(f"Pipeline Status   : {ingestion_summary['status']}")

        if ingestion_summary["error"]:
            logger.error(f"Error             : {ingestion_summary['error']}")

        logger.info("=" * 80)


if __name__ == "__main__":

    run_pipeline()
