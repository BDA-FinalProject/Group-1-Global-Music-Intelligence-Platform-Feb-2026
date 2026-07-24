"""
===============================================================================
Project     : Spotify Big Data Project
Module      : logger.py
Description : Configures application logging.

Author      : Shrirang Awaghad
Created On  : 23-07-2026

Responsibilities:
- Create the log directory if it does not exist.
- Log messages to both the console and a log file.
- Rotate log files to prevent unlimited growth.
- Return a reusable logger instance.
===============================================================================
"""

import logging
import os
from logging.handlers import RotatingFileHandler

import config


def get_logger():
    """
    Creates and returns the application logger.

    Returns:
        logging.Logger: Configured logger instance.
    """

    # -------------------------------------------------------------------------
    # Create log directory if it does not exist
    # -------------------------------------------------------------------------
    os.makedirs(config.LOG_DIRECTORY, exist_ok=True)

    # -------------------------------------------------------------------------
    # Log file path
    # -------------------------------------------------------------------------
    log_file_path = os.path.join(
        config.LOG_DIRECTORY,
        config.LOG_FILE_NAME
    )

    # -------------------------------------------------------------------------
    # Create logger
    # -------------------------------------------------------------------------
    logger = logging.getLogger(config.APPLICATION_NAME)

    # Prevent duplicate handlers if the logger is imported multiple times
    if logger.hasHandlers():
        return logger

    logger.setLevel(config.LOG_LEVEL)

    # -------------------------------------------------------------------------
    # Log Formatter
    # -------------------------------------------------------------------------
    formatter = logging.Formatter(config.LOG_FORMAT)

    # -------------------------------------------------------------------------
    # Console Handler
    # -------------------------------------------------------------------------
    console_handler = logging.StreamHandler()
    console_handler.setLevel(config.LOG_LEVEL)
    console_handler.setFormatter(formatter)

    # -------------------------------------------------------------------------
    # Rotating File Handler
    # Creates a new log file after reaching 5 MB.
    # Keeps the latest 3 backup log files.
    # -------------------------------------------------------------------------
    file_handler = RotatingFileHandler(
        filename=log_file_path,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setLevel(config.LOG_LEVEL)
    file_handler.setFormatter(formatter)

    # -------------------------------------------------------------------------
    # Add Handlers
    # -------------------------------------------------------------------------
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
