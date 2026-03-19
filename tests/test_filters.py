"""
test_filters.py — Unit tests for filters.py (substring, regex, duration filtering).

Tests cover:
- Substring exclusion (case insensitive)
- Regex exclusion with valid and invalid patterns
- ReDoS protection (pattern length limit)
- Duration threshold filtering
- Filter combinations
- Edge cases: empty inputs, no filters, all filtered
"""

from __future__ import annotations

import pandas as pd
import pytest

from filters import MAX_REGEX_LENGTH, _safe_compile_regex, apply_filters


# ===================================================================
# _safe_compile_regex
# ===================================================================


class TestSafeCompileRegex:
    """Tests for the _safe_compile_regex helper."""

    def test_valid_pattern(self):
        compiled = _safe_compile_regex(r"took ms: \d+")
        assert compiled is not None

    def test_invalid_pattern_returns_none(self):
        compiled = _safe_compile_regex(r"[invalid")
        assert compiled is None

    def test_empty_pattern(self):
        compiled = _safe_compile_regex("")
        assert compiled is not None  # empty regex is valid

    def test_pattern_too_long_returns_none(self):
        long_pattern = "a" * (MAX_REGEX_LENGTH + 1)
        compiled = _safe_compile_regex(long_pattern)
        assert compiled is None

    def test_pattern_at_max_length(self):
        pattern = "a" * MAX_REGEX_LENGTH
        compiled = _safe_compile_regex(pattern)
        assert compiled is not None

    def test_complex_valid_pattern(self):
        compiled = _safe_compile_regex(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        assert compiled is not None


# ===================================================================
# apply_filters — substring exclusion
# ===================================================================


class TestSubstringFilters:
    """Tests for substring-based filtering."""

    def _make_events(self, messages: list[str]) -> pd.DataFrame:
        return pd.DataFrame({"message": messages})

    def test_no_filters_returns_all(self):
        events = self._make_events(["a", "b", "c"])
        result = apply_filters(events)
        assert len(result) == 3

    def test_single_substring_excludes_matching(self):
        events = self._make_events(["hello world", "goodbye", "hello again"])
        result = apply_filters(events, exclude_substrings=["hello"])
        assert len(result) == 1
        assert result["message"].iloc[0] == "goodbye"

    def test_substring_case_insensitive(self):
        events = self._make_events(["Hello World", "HELLO", "goodbye"])
        result = apply_filters(events, exclude_substrings=["hello"])
        assert len(result) == 1
        assert result["message"].iloc[0] == "goodbye"

    def test_multiple_substrings(self):
        events = self._make_events(["hello", "world", "foo", "bar"])
        result = apply_filters(events, exclude_substrings=["hello", "foo"])
        assert len(result) == 2
        assert set(result["message"].tolist()) == {"world", "bar"}

    def test_empty_substring_ignored(self):
        events = self._make_events(["hello", "world"])
        result = apply_filters(events, exclude_substrings=[""])
        assert len(result) == 2

    def test_none_substrings(self):
        events = self._make_events(["hello", "world"])
        result = apply_filters(events, exclude_substrings=None)
        assert len(result) == 2

    def test_all_filtered_out(self):
        events = self._make_events(["took ms: 0", "took ms: 1"])
        result = apply_filters(events, exclude_substrings=["took ms"])
        assert len(result) == 0

    def test_substring_partial_match(self):
        events = self._make_events(["Application started", "App stopped"])
        result = apply_filters(events, exclude_substrings=["App"])
        assert len(result) == 0


# ===================================================================
# apply_filters — regex exclusion
# ===================================================================


class TestRegexFilters:
    """Tests for regex-based filtering."""

    def _make_events(self, messages: list[str]) -> pd.DataFrame:
        return pd.DataFrame({"message": messages})

    def test_single_regex(self):
        events = self._make_events(
            ["took ms: 0", "took ms: 123", "Application started"]
        )
        result = apply_filters(events, exclude_regexes=[r"took ms: \d+"])
        assert len(result) == 1
        assert result["message"].iloc[0] == "Application started"

    def test_invalid_regex_silently_ignored(self):
        events = self._make_events(["hello", "world"])
        result = apply_filters(events, exclude_regexes=[r"[invalid"])
        assert len(result) == 2

    def test_too_long_regex_ignored(self):
        events = self._make_events(["hello", "world"])
        long_regex = "a" * (MAX_REGEX_LENGTH + 1)
        result = apply_filters(events, exclude_regexes=[long_regex])
        assert len(result) == 2

    def test_multiple_regexes(self):
        events = self._make_events(["error: 404", "warn: low", "info: ok"])
        result = apply_filters(events, exclude_regexes=[r"error: \d+", r"warn:"])
        assert len(result) == 1
        assert result["message"].iloc[0] == "info: ok"

    def test_none_regexes(self):
        events = self._make_events(["hello", "world"])
        result = apply_filters(events, exclude_regexes=None)
        assert len(result) == 2

    def test_empty_regex_string_ignored(self):
        events = self._make_events(["hello", "world"])
        result = apply_filters(events, exclude_regexes=["", "  "])
        assert len(result) == 2

    def test_regex_with_whitespace_stripped(self):
        events = self._make_events(["took ms: 5", "hello"])
        result = apply_filters(events, exclude_regexes=["  took ms  "])
        assert len(result) == 1


# ===================================================================
# apply_filters — duration threshold
# ===================================================================


class TestDurationFilters:
    """Tests for raw-duration threshold filtering."""

    def _make_events_with_durations(
        self, messages: list[str], durations: list[float | None]
    ) -> tuple[pd.DataFrame, pd.Series]:
        events = pd.DataFrame({"message": messages})
        dur_values = [float("nan") if d is None else d for d in durations]
        durations_series = pd.Series(dur_values, index=events.index)
        return events, durations_series

    def test_no_threshold(self):
        events, durs = self._make_events_with_durations(["a", "b"], [100.0, 50.0])
        result = apply_filters(events, min_raw_duration_ms=0.0, raw_durations_ms=durs)
        assert len(result) == 2

    def test_threshold_filters_short_events(self):
        events, durs = self._make_events_with_durations(
            ["fast", "slow", "medium"], [10.0, 500.0, 100.0]
        )
        result = apply_filters(events, min_raw_duration_ms=50.0, raw_durations_ms=durs)
        assert len(result) == 2
        assert set(result["message"].tolist()) == {"slow", "medium"}

    def test_threshold_keeps_nan_duration(self):
        """Last event has NaN duration and should always be kept."""
        events, durs = self._make_events_with_durations(
            ["first", "last"], [100.0, None]
        )
        result = apply_filters(
            events, min_raw_duration_ms=50.0, raw_durations_ms=durs
        )
        assert len(result) == 2

    def test_threshold_exact_boundary(self):
        events, durs = self._make_events_with_durations(
            ["exact", "below"], [50.0, 49.9]
        )
        result = apply_filters(events, min_raw_duration_ms=50.0, raw_durations_ms=durs)
        assert len(result) == 1
        assert result["message"].iloc[0] == "exact"

    def test_threshold_without_durations_series(self):
        events = pd.DataFrame({"message": ["a", "b"]})
        result = apply_filters(events, min_raw_duration_ms=100.0, raw_durations_ms=None)
        assert len(result) == 2  # no filtering when series is None


# ===================================================================
# apply_filters — combined filters
# ===================================================================


class TestCombinedFilters:
    """Tests for combined substring + regex + duration filters."""

    def test_substring_and_regex_combined(self):
        events = pd.DataFrame(
            {
                "message": [
                    "took ms: 0",
                    "Loading config",
                    "error: timeout",
                    "Server ready",
                ]
            }
        )
        result = apply_filters(
            events,
            exclude_substrings=["took ms"],
            exclude_regexes=[r"error:"],
        )
        assert len(result) == 2
        assert set(result["message"].tolist()) == {"Loading config", "Server ready"}

    def test_all_three_filters_combined(self):
        events = pd.DataFrame(
            {
                "message": [
                    "took ms: 0",
                    "Loading config",
                    "fast op",
                    "Server ready",
                ]
            }
        )
        durations = pd.Series([10.0, 100.0, 5.0, float("nan")], index=events.index)
        result = apply_filters(
            events,
            exclude_substrings=["took ms"],
            exclude_regexes=[r"config"],
            min_raw_duration_ms=50.0,
            raw_durations_ms=durations,
        )
        # "took ms: 0" → excluded by substring
        # "Loading config" → excluded by regex
        # "fast op" → excluded by duration (5 < 50)
        # "Server ready" → NaN duration, kept
        assert len(result) == 1
        assert result["message"].iloc[0] == "Server ready"

    def test_returns_copy_not_view(self):
        events = pd.DataFrame({"message": ["a", "b"]})
        result = apply_filters(events)
        result["message"].iloc[0] = "modified"
        assert events["message"].iloc[0] == "a"
