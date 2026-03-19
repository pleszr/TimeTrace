"""
conftest.py — Shared pytest fixtures for TimeTrace tests.

Provides reusable DataFrames (valid CSV data, edge cases) and helper
factories used across all test modules.
"""

from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """A well-formed CSV DataFrame with timestamp, message, and source columns."""
    return pd.DataFrame(
        {
            "timestamp": [
                "2026-03-19T15:24:17.000Z",
                "2026-03-19T15:24:17.100Z",
                "2026-03-19T15:24:17.200Z",
                "2026-03-19T15:24:17.500Z",
                "2026-03-19T15:24:18.000Z",
            ],
            "message": [
                "Application started",
                "Loading configuration",
                "Service call to UserService.getUser(..) took ms: 0",
                "Connecting to database",
                "Server ready",
            ],
            "source": ["system", "system", "trace", "db", "system"],
        }
    )


@pytest.fixture
def sample_events(sample_df: pd.DataFrame) -> pd.DataFrame:
    """Parsed events DataFrame (output of parse_csv)."""
    from parsing import parse_csv

    events, _ = parse_csv(sample_df)
    return events


@pytest.fixture
def empty_df() -> pd.DataFrame:
    """An empty DataFrame with correct column names."""
    return pd.DataFrame(columns=["timestamp", "message"])


@pytest.fixture
def sample_csv_path(tmp_path) -> str:
    """Write sample CSV to a temp file and return the path."""
    csv_content = (
        "timestamp,message,source\n"
        "2026-03-19T15:24:17.000Z,Application started,system\n"
        "2026-03-19T15:24:17.100Z,Loading configuration,system\n"
        "2026-03-19T15:24:17.200Z,Config loaded,system\n"
    )
    path = tmp_path / "sample.csv"
    path.write_text(csv_content)
    return str(path)
