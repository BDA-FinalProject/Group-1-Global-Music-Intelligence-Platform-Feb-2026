"""
===============================================================================
Project     : Spotify Big Data Project
Module      : extractor.py
Description : Extracts the downloaded Kaggle dataset.

Author      : Shrirang Awaghad
Created On  : 23-07-2026

Responsibilities:
- Extract the downloaded ZIP archive.
- Store extracted files in downloads/extracted.
- Preserve the original file structure.
- Return the list of extracted file paths.
===============================================================================
"""

import os
import zipfile

import config
from helper import create_directory
from logger import get_logger

logger = get_logger()


class DatasetExtractor:
    """
    Handles extraction of downloaded dataset archives.
    """

    def extract_dataset(self, zip_file_path):
        """
        Extracts the dataset ZIP archive.

        Args:
            zip_file_path (str):
                Path to the downloaded ZIP file.

        Returns:
            list:
                List containing the full paths of all extracted files.

        Raises:
            FileNotFoundError:
                If the ZIP file does not exist.

            zipfile.BadZipFile:
                If the ZIP archive is invalid or corrupted.
        """

        logger.info("========== EXTRACTION STARTED ==========")

        if not os.path.isfile(zip_file_path):
            logger.error(f"ZIP file not found: {zip_file_path}")
            raise FileNotFoundError(zip_file_path)

        create_directory(config.EXTRACTED_DIRECTORY)

        try:

            with zipfile.ZipFile(zip_file_path, "r") as zip_ref:

                zip_ref.extractall(config.EXTRACTED_DIRECTORY)

                extracted_files = zip_ref.namelist()

            extracted_file_paths = []

            logger.info(
                f"Successfully extracted {len(extracted_files)} files."
            )

            for file_name in extracted_files:

                full_path = os.path.join(
                    config.EXTRACTED_DIRECTORY,
                    file_name
                )

                extracted_file_paths.append(full_path)

                logger.info(f"Extracted: {full_path}")

            logger.info("========== EXTRACTION COMPLETED ==========")

            return extracted_file_paths

        except zipfile.BadZipFile:

            logger.exception("Invalid or corrupted ZIP archive.")
            raise

        except Exception as error:

            logger.exception(f"Extraction failed: {error}")
            raise
