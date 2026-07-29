from __future__ import annotations

import hashlib
from calendar import month_name
from typing import Any


def clean(value: Any, default: str = "unknown") -> str:
    return default if value is None else str(value)


def number(value: Any) -> str:
    if value is None:
        return "unknown"
    return f"{int(value):,}"


def percent(value: Any) -> str:
    if value is None:
        return "unknown"
    return f"{float(value):.2f}%"


def deterministic_id(*parts: Any) -> str:
    raw = "|".join(clean(part, "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_chunk(
    source_table: str,
    entity_type: str,
    entity_name: str,
    year: int,
    text: str,
    *,
    month: int | None = None,
    chunk_level: str = "child",
    parent_id: str | None = None,
) -> dict:
    chunk_id = deterministic_id(
        source_table,
        entity_type,
        entity_name,
        year,
        month,
        chunk_level,
    )

    return {
        "id": chunk_id,
        "text": text,
        "metadata": {
            "source_table": source_table,
            "entity_type": entity_type,
            "entity_name": entity_name,
            "year": year,
            "month": month,
            "chunk_level": chunk_level,
            "parent_id": parent_id,
        },
    }


def artist_chunk(row: dict) -> dict:
    year, month = int(row["year"]), int(row["month"])
    name = clean(row["artist_name"], clean(row["artist_uri"]))
    parent_id = deterministic_id(
        "artist_performance", "artist", name, year, None, "parent"
    )

    text = (
        f"{name}'s Spotify performance in {month_name[month]} {year}: "
        f"{number(row['total_streams'])} total streams, "
        f"{number(row['active_songs'])} active songs, "
        f"reach across {number(row['countries_reached'])} countries, "
        f"catalog hit rate {percent(row['catalog_hit_rate'])}, and "
        f"average chart strength {percent(row['avg_chart_strength'])}."
    )

    return make_chunk(
        "artist_performance", "artist", name, year, text,
        month=month, parent_id=parent_id,
    )


def country_chunk(row: dict) -> dict:
    year, month = int(row["year"]), int(row["month"])
    name = clean(row["country_name"])
    parent_id = deterministic_id(
        "country_performance", "country", name, year, None, "parent"
    )

    text = (
        f"{name}'s Spotify market performance in {month_name[month]} {year}: "
        f"{number(row['total_streams'])} streams, "
        f"{percent(row['market_share'])} market share, "
        f"{percent(row['growth_percentage'])} growth, "
        f"{number(row['active_songs'])} active songs, "
        f"{number(row['active_artists'])} active artists, and "
        f"{number(row['active_labels'])} active labels. "
        f"Top artist: {clean(row['top_artist'])}. "
        f"Top label: {clean(row['top_label'])}."
    )

    return make_chunk(
        "country_performance", "country", name, year, text,
        month=month, parent_id=parent_id,
    )


def label_chunk(row: dict) -> dict:
    year, month = int(row["year"]), int(row["month"])
    name = clean(row["standardized_label"])
    parent_id = deterministic_id(
        "label_performance", "label", name, year, None, "parent"
    )

    text = (
        f"{name}'s Spotify performance in {month_name[month]} {year}: "
        f"{number(row['total_streams'])} total streams, "
        f"{percent(row['market_share'])} market share, "
        f"{percent(row['catalog_hit_rate'])} catalog hit rate, "
        f"{number(row['active_songs'])} active songs, and "
        f"{number(row['active_artists'])} active artists."
    )

    return make_chunk(
        "label_performance", "label", name, year, text,
        month=month, parent_id=parent_id,
    )


def global_chunk(row: dict, source_table: str) -> dict:
    year, month = int(row["year"]), int(row["month"])

    metrics = [
        f"{number(value)} {column.replace('_', ' ')}"
        for column, value in row.items()
        if column not in {"year", "month", "year_month"}
    ]

    text = (
        f"Global Spotify {source_table.replace('_', ' ')} for "
        f"{month_name[month]} {year}: {', '.join(metrics)}."
    )

    return make_chunk(
        source_table,
        "global",
        "Global Spotify",
        year,
        text,
        month=month,
    )