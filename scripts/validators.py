"""
Schema Validation Utilities
"""

from config.constants import GOLD_TABLES


def validate_table(table_name: str):
    """
    Validate whether the table is supported.
    """

    if table_name not in GOLD_TABLES:
        raise ValueError(
            f"Unsupported Gold table: {table_name}"
        )


def get_primary_key(table_name: str):
    """
    Returns configured primary key.
    """

    return GOLD_TABLES[table_name]["primary_key"]