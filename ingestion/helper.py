"""
===============================================================================
Project     : Spotify Big Data Project
Module      : helper.py
Description : Common utility functions used across the ingestion pipeline.

Author      : Shrirang Awaghad
Created On  : 23-07-2026

Responsibilities:
- Directory management
- File management
- File discovery
- File size formatting
- Timestamp generation
===============================================================================
"""

import os
import shutil
from datetime import datetime


def create_directory(directory_path):
    """
    Creates a directory if it does not already exist.

    Args:
        directory_path (str): Directory path.
    """
    os.makedirs(directory_path, exist_ok=True)


def file_exists(file_path):
    """
    Checks whether a file exists.

    Args:
        file_path (str): File path.

    Returns:
        bool
    """
    return os.path.isfile(file_path)


def directory_exists(directory_path):
    """
    Checks whether a directory exists.

    Args:
        directory_path (str): Directory path.

    Returns:
        bool
    """
    return os.path.isdir(directory_path)


def get_files(directory_path):
    """
    Returns all files present inside a directory
    (non-recursive).

    Args:
        directory_path (str)

    Returns:
        list
    """

    if not directory_exists(directory_path):
        return []

    return [
        os.path.join(directory_path, file_name)
        for file_name in os.listdir(directory_path)
        if os.path.isfile(os.path.join(directory_path, file_name))
    ]


def get_all_files(directory_path):
    """
    Returns every file inside a directory recursively.

    Args:
        directory_path (str)

    Returns:
        list
    """

    all_files = []

    if not directory_exists(directory_path):
        return all_files

    for root, _, files in os.walk(directory_path):

        for file_name in files:

            all_files.append(
                os.path.join(root, file_name)
            )

    return all_files


def get_file_name(file_path):
    """
    Returns only the file name.

    Example:
        downloads/raw/data.zip

    Returns:
        data.zip
    """

    return os.path.basename(file_path)


def get_file_extension(file_path):
    """
    Returns the complete file extension.

    Examples:
        songs.csv       -> .csv
        songs.csv.gz    -> .csv.gz
        archive.zip     -> .zip

    Args:
        file_path (str)

    Returns:
        str
    """

    file_name = os.path.basename(file_path).lower()

    if file_name.endswith(".csv.gz"):
        return ".csv.gz"

    return os.path.splitext(file_name)[1]

def get_file_size(file_path):
    """
    Returns file size in bytes.

    Args:
        file_path (str)

    Returns:
        int
    """

    return os.path.getsize(file_path)


def format_file_size(size):
    """
    Converts bytes into a human-readable format.

    Args:
        size (int)

    Returns:
        str
    """

    units = ["B", "KB", "MB", "GB", "TB"]

    for unit in units:

        if size < 1024:
            return f"{size:.2f} {unit}"

        size /= 1024

    return f"{size:.2f} PB"


def delete_file(file_path):
    """
    Deletes a file if it exists.

    Args:
        file_path (str)
    """

    if file_exists(file_path):
        os.remove(file_path)


def delete_directory(directory_path):
    """
    Deletes an entire directory.

    Args:
        directory_path (str)
    """

    if directory_exists(directory_path):
        shutil.rmtree(directory_path)


def clear_directory(directory_path):
    """
    Removes all files and subdirectories inside
    a directory while keeping the directory itself.

    Args:
        directory_path (str)
    """

    if not directory_exists(directory_path):
        return

    for item in os.listdir(directory_path):

        item_path = os.path.join(directory_path, item)

        if os.path.isfile(item_path):
            os.remove(item_path)

        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)


def get_timestamp():
    """
    Returns the current timestamp.

    Returns:
        str
    """

    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
