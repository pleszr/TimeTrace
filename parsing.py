"""
parsing.py — CSV parsing and event construction for TimeTrace.

Reads a CSV file, detects required columns (timestamp, message) case-insensitively,
parses timestamps, and produces a clean list of event records.
"""

from __future__ import annotations

import pandas as pd


def detect_columns(df: pd.DataFrame) -> tuple[str, str]:
    """Find the actual column names that map to 'timestamp' and 'message'.

    Matching is case-insensitive with stripped whitespace.
    Returns (timestamp_col, message_col) using the original column names.
    Raises ValueError if either required column is missing.
    """
    col_map: dict[str, str] = {}
    for col in df.columns:
        normalized = col.strip().lower()
        if normalized == "timestamp" and "timestamp" not in col_map:
            col_map["timestamp"] = col
        elif normalized == "message" and "message" not in col_map:
            col_map["message"] = col

    missing = [name for name in ("timestamp", "message") if name not in col_map]
    if missing:
        raise ValueError(
            f"Missing required column(s): {', '.join(missing)}. "
            f"Found columns: {list(df.columns)}"
        )
    return col_map["timestamp"], col_map["message"]


def parse_csv(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Parse a raw DataFrame into a cleaned events DataFrame.

    Returns (events_df, skipped_count) where:
    - events_df has columns: row_index, timestamp, message, plus all original columns
    - skipped_count = rows dropped due to invalid timestamp or empty message
    """
    ts_col, msg_col = detect_columns(raw_df)

    # Work on a copy to avoid mutating the input
    df = raw_df.copy()
    df["_original_index"] = range(len(df))
    initial_count = len(df)

    # Trim whitespace from message and drop empties
    df[msg_col] = df[msg_col].astype(str).str.strip()
    df = df[df[msg_col].ne("") & df[msg_col].ne("nan")].copy()

    # Parse timestamps — coerce errors to NaT, then drop them
    df["_parsed_ts"] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    df = df.dropna(subset=["_parsed_ts"]).copy()

    skipped = initial_count - len(df)

    # Sort by timestamp
    df = df.sort_values("_parsed_ts").reset_index(drop=True)

    # Build the clean events DataFrame
    events = pd.DataFrame(
        {
            "row_index": df["_original_index"].values,
            "timestamp": df["_parsed_ts"].values,
            "message": df[msg_col].values,
        }
    )

    # Attach all original columns for debugging/display
    for col in raw_df.columns:
        if col.strip().lower() not in ("timestamp", "message"):
            events[f"raw_{col}"] = df[col].values

    return events, skipped
