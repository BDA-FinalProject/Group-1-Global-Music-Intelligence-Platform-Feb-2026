"""
===============================================================================
Project     : Spotify Big Data Project
Module      : uploader.py
Description : Uploads extracted dataset files to Amazon S3.

Author      : Shrirang Awaghad
Created On  : 23-07-2026

Responsibilities:
- Upload extracted dataset files to Amazon S3.
- Preserve folder structure.
- Log upload progress.
===============================================================================
"""

import os

import boto3

import config
from logger import get_logger

logger = get_logger()


class S3Uploader:
    """
    Handles uploading extracted dataset files to Amazon S3.
    """

    def __init__(self):

        self.s3_client = boto3.client(
            "s3",
            region_name=config.AWS_REGION
        )

    def upload_files(self, extracted_files):
        """
        Uploads extracted files to Amazon S3.

        Args:
            extracted_files (list):
                List of extracted file paths.

        Returns:
            list:
                List of uploaded S3 object keys.
        """

        logger.info("========== S3 UPLOAD STARTED ==========")

        uploaded_files = []

        try:

            for file_path in extracted_files:

                relative_path = os.path.relpath(
                    file_path,
                    config.EXTRACTED_DIRECTORY
                )

                s3_key = os.path.join(
                    config.S3_FOLDER,
                    relative_path
                ).replace("\\", "/")

                logger.info(f"Uploading : {relative_path}")

                self.s3_client.upload_file(
                    Filename=file_path,
                    Bucket=config.S3_BUCKET_NAME,
                    Key=s3_key
                )

                uploaded_files.append(s3_key)

                logger.info(f"Uploaded  : {s3_key}")

            logger.info(
                f"Successfully uploaded {len(uploaded_files)} files."
            )

            logger.info("========== S3 UPLOAD COMPLETED ==========")

            return uploaded_files

        except Exception as error:

            logger.exception(
                f"S3 upload failed: {error}"
            )

            raise
