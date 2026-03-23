"""
test_timeline.py — Unit tests for timeline.py (duration computation and chart building).

Tests cover:
- Forward-looking duration computation
- Effective vs raw duration in build_timeline_data
- Plotly chart construction (figure structure, labels, axes)
- Edge cases: single event, empty DataFrame, large gaps
- _fmt_dur helper formatting
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import pytest

from timeline import _fmt_dur, _fmt_pct, _wrap_text, build_chart, build_timeline_data, compute_durations_ms


# ===================================================================
# compute_durations_ms
# ===================================================================


class TestComputeDurations:
    """Tests for compute_durations_ms function."""

    def test_basic_durations(self):
        events = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    [
                        "2026-03-19T15:24:17.000Z",
                        "2026-03-19T15:24:17.100Z",
                        "2026-03-19T15:24:17.500Z",
                    ]
                )
            }
        )
        durations = compute_durations_ms(events)
        assert len(durations) == 3
        assert pytest.approx(durations.iloc[0], abs=1) == 100.0
        assert pytest.approx(durations.iloc[1], abs=1) == 400.0
        assert pd.isna(durations.iloc[2])  # last event has NaN

    def test_single_event_nan(self):
        events = pd.DataFrame(
            {"timestamp": pd.to_datetime(["2026-03-19T15:24:17.000Z"])}
        )
        durations = compute_durations_ms(events)
        assert len(durations) == 1
        assert pd.isna(durations.iloc[0])

    def test_two_events(self):
        events = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    [
                        "2026-03-19T15:24:17.000Z",
                        "2026-03-19T15:24:18.000Z",
                    ]
                )
            }
        )
        durations = compute_durations_ms(events)
        assert pytest.approx(durations.iloc[0], abs=1) == 1000.0
        assert pd.isna(durations.iloc[1])

    def test_equal_timestamps_zero_duration(self):
        events = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    [
                        "2026-03-19T15:24:17.000Z",
                        "2026-03-19T15:24:17.000Z",
                        "2026-03-19T15:24:18.000Z",
                    ]
                )
            }
        )
        durations = compute_durations_ms(events)
        assert pytest.approx(durations.iloc[0], abs=0.1) == 0.0
        assert pytest.approx(durations.iloc[1], abs=1) == 1000.0

    def test_sub_millisecond_precision(self):
        events = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    [
                        "2026-03-19T15:24:17.0000Z",
                        "2026-03-19T15:24:17.0005Z",
                    ]
                )
            }
        )
        durations = compute_durations_ms(events)
        assert pytest.approx(durations.iloc[0], abs=0.1) == 0.5


# ===================================================================
# build_timeline_data
# ===================================================================


class TestBuildTimelineData:
    """Tests for build_timeline_data function."""

    def _make_events(self, count: int = 5) -> pd.DataFrame:
        base_ts = pd.Timestamp("2026-03-19T15:24:17.000Z")
        timestamps = [base_ts + pd.Timedelta(milliseconds=i * 100) for i in range(count)]
        return pd.DataFrame(
            {
                "timestamp": timestamps,
                "message": [f"event_{i}" for i in range(count)],
            }
        )

    def test_basic_timeline_data(self):
        raw = self._make_events(5)
        filtered = raw.iloc[[0, 2, 4]].copy()  # skip events 1 and 3
        timeline = build_timeline_data(raw, filtered)

        assert "raw_duration_ms" in timeline.columns
        assert "effective_duration_ms" in timeline.columns
        assert len(timeline) == 3

    def test_raw_duration_from_full_set(self):
        raw = self._make_events(3)
        filtered = raw.copy()
        timeline = build_timeline_data(raw, filtered)

        # Raw durations: 100ms, 100ms, NaN
        assert pytest.approx(timeline["raw_duration_ms"].iloc[0], abs=1) == 100.0
        assert pytest.approx(timeline["raw_duration_ms"].iloc[1], abs=1) == 100.0
        assert pd.isna(timeline["raw_duration_ms"].iloc[2])

    def test_effective_duration_from_filtered_set(self):
        raw = self._make_events(5)
        # Keep events 0, 2, 4 (at 0ms, 200ms, 400ms)
        filtered = raw.iloc[[0, 2, 4]].copy()
        timeline = build_timeline_data(raw, filtered)

        # Effective durations: 200ms, 200ms, NaN
        assert pytest.approx(timeline["effective_duration_ms"].iloc[0], abs=1) == 200.0
        assert pytest.approx(timeline["effective_duration_ms"].iloc[1], abs=1) == 200.0
        assert pd.isna(timeline["effective_duration_ms"].iloc[2])

    def test_single_event_timeline(self):
        raw = self._make_events(1)
        filtered = raw.copy()
        timeline = build_timeline_data(raw, filtered)
        assert len(timeline) == 1
        assert pd.isna(timeline["raw_duration_ms"].iloc[0])
        assert pd.isna(timeline["effective_duration_ms"].iloc[0])

    def test_empty_filtered_returns_empty(self):
        raw = self._make_events(3)
        filtered = raw.iloc[0:0].copy()  # empty
        timeline = build_timeline_data(raw, filtered)
        assert len(timeline) == 0


# ===================================================================
# build_chart
# ===================================================================


class TestBuildChart:
    """Tests for the build_chart function."""

    def _make_timeline(self, count: int = 3) -> pd.DataFrame:
        base_ts = pd.Timestamp("2026-03-19T15:24:17.000Z")
        timestamps = [base_ts + pd.Timedelta(milliseconds=i * 100) for i in range(count)]
        return pd.DataFrame(
            {
                "timestamp": timestamps,
                "message": [f"Event {i}" for i in range(count)],
                "raw_duration_ms": [100.0] * (count - 1) + [float("nan")],
                "effective_duration_ms": [100.0] * (count - 1) + [float("nan")],
            }
        )

    def test_returns_plotly_figure(self):
        timeline = self._make_timeline()
        fig = build_chart(timeline)
        assert isinstance(fig, go.Figure)

    def test_figure_has_bar_trace(self):
        timeline = self._make_timeline()
        fig = build_chart(timeline)
        assert len(fig.data) == 1
        assert isinstance(fig.data[0], go.Bar)

    def test_figure_horizontal_orientation(self):
        timeline = self._make_timeline()
        fig = build_chart(timeline)
        assert fig.data[0].orientation == "h"

    def test_figure_labels_are_numbered(self):
        timeline = self._make_timeline(3)
        fig = build_chart(timeline)
        y_labels = list(fig.data[0].y)
        assert y_labels[0].startswith("1. ")
        assert y_labels[1].startswith("2. ")
        assert y_labels[2].startswith("3. ")

    def test_figure_labels_truncated_at_80_chars(self):
        timeline = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-03-19T15:24:17.000Z"]),
                "message": ["A" * 200],
                "raw_duration_ms": [float("nan")],
                "effective_duration_ms": [float("nan")],
            }
        )
        fig = build_chart(timeline)
        label = fig.data[0].y[0]
        # "1. " (3 chars) + 80 chars = 83
        assert len(label) == 83

    def test_empty_timeline_returns_figure(self):
        timeline = pd.DataFrame(
            columns=["timestamp", "message", "raw_duration_ms", "effective_duration_ms"]
        )
        fig = build_chart(timeline)
        assert isinstance(fig, go.Figure)

    def test_chart_axes_titles(self):
        timeline = self._make_timeline()
        fig = build_chart(timeline)
        assert fig.layout.xaxis.title.text == "Time offset (ms)"
        assert fig.layout.yaxis.title.text == "Events"

    def test_chart_title(self):
        timeline = self._make_timeline()
        fig = build_chart(timeline)
        assert fig.layout.title.text == "TimeTrace Timeline"

    def test_last_event_gets_minimal_width(self):
        timeline = self._make_timeline(2)
        fig = build_chart(timeline)
        bar_widths = list(fig.data[0].x)
        # Last event should have a non-zero width
        assert bar_widths[-1] > 0

    def test_chart_reversed_y_axis(self):
        timeline = self._make_timeline()
        fig = build_chart(timeline)
        assert fig.layout.yaxis.autorange == "reversed"

    def test_hover_text_present(self):
        timeline = self._make_timeline()
        fig = build_chart(timeline)
        hover_texts = fig.data[0].hovertext
        assert len(hover_texts) == 3
        for text in hover_texts:
            assert "Timestamp:" in text
            assert "Effective duration:" in text
            assert "Percentage of total:" in text
            assert "Raw duration:" in text

    def test_hover_text_percentage_values(self):
        timeline = self._make_timeline(3)
        fig = build_chart(timeline)
        hover_texts = fig.data[0].hovertext
        # First two events each have 100ms effective duration
        assert "50.00%" in hover_texts[0]
        assert "50.00%" in hover_texts[1]
        # Last event gets NaN → "— (last event)"
        assert "— (last event)" in hover_texts[2]

    def test_hover_text_wraps_long_message(self):
        long_msg = "A" * 200
        timeline = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-03-19T15:24:17.000Z"]),
                "message": [long_msg],
                "raw_duration_ms": [float("nan")],
                "effective_duration_ms": [float("nan")],
            }
        )
        fig = build_chart(timeline)
        hover_text = fig.data[0].hovertext[0]
        # Long message should be split with <br> inside the bold tag
        assert "<br>" in hover_text.split("</b>")[0]

    def test_hover_uses_full_message_when_present(self):
        timeline = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    ["2026-03-19T15:24:17.000Z", "2026-03-19T15:24:18.000Z"]
                ),
                "message": ["Truncated msg", "Short"],
                "raw_full_message": ["The complete full message text", "Short"],
                "raw_duration_ms": [1000.0, float("nan")],
                "effective_duration_ms": [1000.0, float("nan")],
            }
        )
        fig = build_chart(timeline)
        hover_text = fig.data[0].hovertext[0]
        assert "The complete full message text" in hover_text
        assert "Truncated msg" not in hover_text

    def test_hover_falls_back_to_message_without_full_message(self):
        timeline = self._make_timeline()
        fig = build_chart(timeline)
        hover_text = fig.data[0].hovertext[0]
        assert "Event 0" in hover_text


# ===================================================================
# _fmt_dur
# ===================================================================


class TestFmtDur:
    """Tests for the _fmt_dur helper."""

    def test_normal_value(self):
        assert _fmt_dur(123.456) == "123.46 ms"

    def test_zero(self):
        assert _fmt_dur(0) == "0.00 ms"

    def test_nan_value(self):
        assert _fmt_dur(float("nan")) == "— (last event)"

    def test_none_value(self):
        assert _fmt_dur(None) == "— (last event)"

    def test_large_value(self):
        result = _fmt_dur(1234567.89)
        assert "1,234,567.89 ms" == result

    def test_small_value(self):
        assert _fmt_dur(0.001) == "0.00 ms"


# ===================================================================
# _fmt_pct
# ===================================================================


class TestFmtPct:
    """Tests for the _fmt_pct helper."""

    def test_normal_value(self):
        assert _fmt_pct(250, 1000) == "25.00%"

    def test_zero_total(self):
        assert _fmt_pct(100, 0) == "— (last event)"

    def test_nan_value(self):
        assert _fmt_pct(float("nan"), 1000) == "— (last event)"

    def test_full_percentage(self):
        assert _fmt_pct(500, 500) == "100.00%"

    def test_small_percentage(self):
        assert _fmt_pct(1, 10000) == "0.01%"


# ===================================================================
# _wrap_text
# ===================================================================


class TestWrapText:
    """Tests for the _wrap_text helper."""

    def test_short_text_unchanged(self):
        assert _wrap_text("hello world") == "hello world"

    def test_text_at_boundary_unchanged(self):
        text = "a" * 80
        assert _wrap_text(text) == text

    def test_long_text_wrapped(self):
        text = "word " * 30  # 150 chars
        result = _wrap_text(text.strip())
        assert "<br>" in result

    def test_no_spaces_hard_break(self):
        text = "a" * 200
        result = _wrap_text(text)
        assert "<br>" in result
        # First segment should be exactly 80 chars (default width)
        assert len(result.split("<br>")[0]) == 80

    def test_embedded_newlines_converted(self):
        text = "line one\nline two\nline three"
        result = _wrap_text(text)
        assert result == "line one<br>line two<br>line three"

    def test_tabs_converted_to_spaces(self):
        text = "key:\tvalue"
        result = _wrap_text(text)
        assert "\t" not in result
        assert "key:    value" == result

    def test_multiline_long_lines_wrapped(self):
        text = "short line\n" + "x " * 60  # second line is 120 chars
        result = _wrap_text(text)
        lines = result.split("<br>")
        assert lines[0] == "short line"
        assert len(lines) >= 3  # short + wrapped parts

    def test_truncation_at_max_lines(self):
        text = "\n".join(f"line {i}" for i in range(30))
        result = _wrap_text(text, max_lines=5)
        lines = result.split("<br>")
        assert len(lines) == 6  # 5 lines + "…"
        assert lines[-1] == "…"
