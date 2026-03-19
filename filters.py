"""
filters.py — Filtering logic for TimeTrace.

Provides functions to apply substring, regex, and raw-duration-threshold
filters to an events DataFrame. Filters are combinable: if any rule matches,
the event is excluded.
"""

from __future__ import annotations

import re

import pandas as pd


def apply_filters(
    events: pd.DataFrame,
    exclude_substrings: list[str] | None = None,
    exclude_regexes: list[str] | None = None,
    min_raw_duration_ms: float = 0.0,
    raw_durations_ms: pd.Series | None = None,
) -> pd.DataFrame:
    """Return a filtered copy of events, excluding rows matching any rule.

    Parameters
    ----------
    events : DataFrame with at least 'message' column.
    exclude_substrings : list of substrings — if message contains any, exclude.
    exclude_regexes : list of regex patterns — if any matches message, exclude.
    min_raw_duration_ms : hide events whose raw duration is below this threshold.
    raw_durations_ms : Series aligned with events, holding raw duration in ms.
                       Required when min_raw_duration_ms > 0.
    """
    mask = pd.Series(True, index=events.index)

    # Substring filters
    if exclude_substrings:
        for sub in exclude_substrings:
            if sub:
                mask &= ~events["message"].str.contains(sub, case=False, regex=False)

    # Regex filters
    if exclude_regexes:
        for pattern in exclude_regexes:
            pattern = pattern.strip()
            if pattern:
                try:
                    compiled = re.compile(pattern)
                    mask &= ~events["message"].str.contains(compiled)
                except re.error:
                    # Skip invalid regex patterns silently
                    pass

    # Raw-duration threshold filter
    if min_raw_duration_ms > 0 and raw_durations_ms is not None:
        # Keep events with NaN duration (last event) or duration >= threshold
        duration_ok = raw_durations_ms.isna() | (raw_durations_ms >= min_raw_duration_ms)
        mask &= duration_ok

    return events[mask].copy()
