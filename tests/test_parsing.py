"""
test_parsing.py — Unit tests for parsing.py (CSV parsing and column detection).

Tests cover:
- Case-insensitive column detection
- Missing required columns
- Timestamp parsing (valid, invalid, mixed)
- Empty/NaN message handling
- Row ordering by timestamp
- Preservation of extra columns
- Edge cases: empty DataFrames, single-row, duplicate columns
"""

from __future__ import annotations

import pandas as pd
import pytest

from parsing import detect_columns, parse_csv


# ===================================================================
# detect_columns
# ===================================================================


class TestDetectColumns:
    """Tests for the detect_columns function."""

    def test_exact_column_names(self, sample_df: pd.DataFrame):
        ts_col, msg_col = detect_columns(sample_df)
        assert ts_col == "timestamp"
        assert msg_col == "message"

    def test_case_insensitive_uppercase(self):
        df = pd.DataFrame({"TIMESTAMP": ["2026-01-01"], "MESSAGE": ["hello"]})
        ts_col, msg_col = detect_columns(df)
        assert ts_col == "TIMESTAMP"
        assert msg_col == "MESSAGE"

    def test_case_insensitive_mixed_case(self):
        df = pd.DataFrame({"TimeStamp": ["2026-01-01"], "Message": ["hello"]})
        ts_col, msg_col = detect_columns(df)
        assert ts_col == "TimeStamp"
        assert msg_col == "Message"

    def test_columns_with_whitespace(self):
        df = pd.DataFrame({" timestamp ": ["2026-01-01"], " message ": ["hello"]})
        ts_col, msg_col = detect_columns(df)
        assert ts_col == " timestamp "
        assert msg_col == " message "

    def test_missing_timestamp_column(self):
        df = pd.DataFrame({"time": ["2026-01-01"], "message": ["hello"]})
        with pytest.raises(ValueError, match="Missing required column.*timestamp"):
            detect_columns(df)

    def test_missing_message_column(self):
        df = pd.DataFrame({"timestamp": ["2026-01-01"], "text": ["hello"]})
        with pytest.raises(ValueError, match="Missing required column.*message"):
            detect_columns(df)

    def test_missing_both_columns(self):
        df = pd.DataFrame({"a": [1], "b": [2]})
        with pytest.raises(ValueError, match="Missing required column"):
            detect_columns(df)

    def test_extra_columns_ignored(self):
        df = pd.DataFrame(
            {
                "id": [1],
                "timestamp": ["2026-01-01"],
                "message": ["hello"],
                "source": ["sys"],
                "extra": ["x"],
            }
        )
        ts_col, msg_col = detect_columns(df)
        assert ts_col == "timestamp"
        assert msg_col == "message"

    def test_empty_dataframe_with_correct_columns(self, empty_df: pd.DataFrame):
        ts_col, msg_col = detect_columns(empty_df)
        assert ts_col == "timestamp"
        assert msg_col == "message"

    def test_empty_dataframe_missing_columns(self):
        df = pd.DataFrame()
        with pytest.raises(ValueError):
            detect_columns(df)


# ===================================================================
# parse_csv
# ===================================================================


class TestParseCsv:
    """Tests for the parse_csv function."""

    def test_basic_parsing(self, sample_df: pd.DataFrame):
        events, skipped = parse_csv(sample_df)
        assert len(events) == 5
        assert skipped == 0
        assert list(events.columns[:3]) == ["row_index", "timestamp", "message"]

    def test_output_columns(self, sample_df: pd.DataFrame):
        events, _ = parse_csv(sample_df)
        assert "row_index" in events.columns
        assert "timestamp" in events.columns
        assert "message" in events.columns
        assert "raw_source" in events.columns  # extra column preserved

    def test_events_sorted_by_timestamp(self):
        df = pd.DataFrame(
            {
                "timestamp": [
                    "2026-03-19T15:24:19.000Z",
                    "2026-03-19T15:24:17.000Z",
                    "2026-03-19T15:24:18.000Z",
                ],
                "message": ["third", "first", "second"],
            }
        )
        events, skipped = parse_csv(df)
        assert skipped == 0
        messages = events["message"].tolist()
        assert messages == ["first", "second", "third"]

    def test_invalid_timestamps_skipped(self):
        df = pd.DataFrame(
            {
                "timestamp": [
                    "2026-03-19T15:24:17.000Z",
                    "not-a-date",
                    "also-invalid",
                    "2026-03-19T15:24:18.000Z",
                ],
                "message": ["valid1", "bad1", "bad2", "valid2"],
            }
        )
        events, skipped = parse_csv(df)
        assert len(events) == 2
        assert skipped == 2

    def test_empty_messages_skipped(self):
        df = pd.DataFrame(
            {
                "timestamp": [
                    "2026-03-19T15:24:17.000Z",
                    "2026-03-19T15:24:18.000Z",
                    "2026-03-19T15:24:19.000Z",
                ],
                "message": ["valid", "", "  "],
            }
        )
        events, skipped = parse_csv(df)
        assert len(events) == 1
        assert skipped == 2

    def test_nan_messages_skipped(self):
        df = pd.DataFrame(
            {
                "timestamp": [
                    "2026-03-19T15:24:17.000Z",
                    "2026-03-19T15:24:18.000Z",
                ],
                "message": ["valid", float("nan")],
            }
        )
        events, skipped = parse_csv(df)
        assert len(events) == 1
        assert skipped == 1

    def test_preserves_original_row_index(self):
        df = pd.DataFrame(
            {
                "timestamp": [
                    "2026-03-19T15:24:17.000Z",
                    "2026-03-19T15:24:18.000Z",
                    "2026-03-19T15:24:19.000Z",
                ],
                "message": ["a", "b", "c"],
            }
        )
        events, _ = parse_csv(df)
        assert events["row_index"].tolist() == [0, 1, 2]

    def test_preserves_extra_columns(self):
        df = pd.DataFrame(
            {
                "timestamp": ["2026-03-19T15:24:17.000Z"],
                "message": ["hello"],
                "level": ["INFO"],
                "source": ["app"],
            }
        )
        events, _ = parse_csv(df)
        assert "raw_level" in events.columns
        assert "raw_source" in events.columns
        assert events["raw_level"].iloc[0] == "INFO"

    def test_single_row(self):
        df = pd.DataFrame(
            {
                "timestamp": ["2026-03-19T15:24:17.000Z"],
                "message": ["only one"],
            }
        )
        events, skipped = parse_csv(df)
        assert len(events) == 1
        assert skipped == 0

    def test_all_rows_invalid(self):
        df = pd.DataFrame(
            {
                "timestamp": ["bad1", "bad2"],
                "message": ["a", "b"],
            }
        )
        events, skipped = parse_csv(df)
        assert len(events) == 0
        assert skipped == 2

    def test_does_not_mutate_input(self, sample_df: pd.DataFrame):
        original = sample_df.copy()
        parse_csv(sample_df)
        pd.testing.assert_frame_equal(sample_df, original)

    def test_whitespace_messages_trimmed(self):
        df = pd.DataFrame(
            {
                "timestamp": ["2026-03-19T15:24:17.000Z"],
                "message": ["  hello world  "],
            }
        )
        events, _ = parse_csv(df)
        assert events["message"].iloc[0] == "hello world"

    def test_case_insensitive_columns(self):
        df = pd.DataFrame(
            {
                "TIMESTAMP": ["2026-03-19T15:24:17.000Z"],
                "MESSAGE": ["hello"],
            }
        )
        events, skipped = parse_csv(df)
        assert len(events) == 1
        assert skipped == 0

    def test_mixed_valid_and_invalid_rows(self):
        df = pd.DataFrame(
            {
                "timestamp": [
                    "2026-03-19T15:24:17.000Z",
                    "bad",
                    "2026-03-19T15:24:18.000Z",
                    "",
                    "2026-03-19T15:24:19.000Z",
                ],
                "message": ["a", "b", "", "d", "e"],
            }
        )
        events, skipped = parse_csv(df)
        # Row 0: valid timestamp, valid message → kept
        # Row 1: bad timestamp → skipped
        # Row 2: valid timestamp, empty message → skipped
        # Row 3: empty timestamp (invalid) → skipped
        # Row 4: valid timestamp, valid message → kept
        assert len(events) == 2
        assert skipped == 3
