"""
===============================================================================
Project     : Spotify Big Data Project
Module      : downloader.py
Description : Downloads the Spotify dataset using the Kaggle CLI.

Author      : Shrirang Awaghad
Created On  : 23-07-2026

Responsibilities:
- Download the configured Kaggle dataset.
- Store the ZIP file in downloads/raw.
- Return the downloaded ZIP file path.
===============================================================================
"""

import os
import subprocess

import config
from helper import create_directory
from logger import get_logger

logger = get_logger()


class KaggleDownloader:
    """
    Handles downloading datasets from Kaggle using the Kaggle CLI.
    """

    def download_dataset(self):
        """
        Downloads the configured Kaggle dataset.

        Returns:
            str: Path to the downloaded ZIP file.

        Raises:
            RuntimeError:
                If the Kaggle CLI download fails.

            FileNotFoundError:
                If no ZIP file is found after download.
        """

        logger.info("========== KAGGLE DOWNLOAD STARTED ==========")
        logger.info(f"Dataset           : {config.KAGGLE_DATASET}")
        logger.info(f"Download Location : {config.RAW_DOWNLOAD_DIRECTORY}")

        create_directory(config.RAW_DOWNLOAD_DIRECTORY)

        command = [
            "kaggle",
            "datasets",
            "download",
            "-d",
            config.KAGGLE_DATASET,
            "-p",
            config.RAW_DOWNLOAD_DIRECTORY,
            "--force"
        ]

        try:

            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True
            )

            logger.info(result.stdout)

            zip_files = [
                file_name
                for file_name in os.listdir(config.RAW_DOWNLOAD_DIRECTORY)
                if file_name.lower().endswith(".zip")
            ]

            if not zip_files:
                raise FileNotFoundError(
                    "Dataset download completed but no ZIP file was found."
                )

            zip_file_path = os.path.join(
                config.RAW_DOWNLOAD_DIRECTORY,
                zip_files[0]
            )

            logger.info(f"Downloaded ZIP : {zip_file_path}")
            logger.info("========== KAGGLE DOWNLOAD COMPLETED ==========")

            return zip_file_path

        except subprocess.CalledProcessError as error:

            logger.error(error.stderr)

            raise RuntimeError(
                "Kaggle CLI download failed."
            ) from error
