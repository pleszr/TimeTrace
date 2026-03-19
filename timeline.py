"""
timeline.py — Duration calculation and Plotly chart construction for TimeTrace.

Computes raw and effective durations, builds a horizontal bar timeline chart
inspired by Chrome DevTools Network tab.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def compute_durations_ms(events: pd.DataFrame) -> pd.Series:
    """Compute forward-looking durations in milliseconds.

    duration[i] = timestamp[i+1] - timestamp[i]
    The last event gets NaN.
    """
    ts = pd.to_datetime(events["timestamp"])
    deltas = ts.diff().shift(-1)
    return deltas.dt.total_seconds() * 1000


def build_timeline_data(
    raw_events: pd.DataFrame,
    filtered_events: pd.DataFrame,
) -> pd.DataFrame:
    """Attach raw_duration_ms and effective_duration_ms to filtered events."""
    result = filtered_events.copy()

    # Raw durations computed on the full event set, then mapped to filtered rows
    raw_dur = compute_durations_ms(raw_events)
    raw_dur.index = raw_events.index
    result["raw_duration_ms"] = result.index.map(raw_dur)

    # Effective durations computed on filtered set only
    result = result.reset_index(drop=True)
    result["effective_duration_ms"] = compute_durations_ms(result)

    return result


def build_chart(timeline: pd.DataFrame) -> go.Figure:
    """Create a horizontal bar chart showing the event timeline.

    X-axis = relative time from first event (ms)
    Y-axis = one row per event (labelled by truncated message)
    """
    if timeline.empty:
        fig = go.Figure()
        fig.update_layout(title="No events to display")
        return fig

    first_ts = pd.to_datetime(timeline["timestamp"].iloc[0])
    offsets_ms = (
        (pd.to_datetime(timeline["timestamp"]) - first_ts).dt.total_seconds() * 1000
    )

    # Bar widths: use effective duration, fallback to small value for last event
    widths = timeline["effective_duration_ms"].fillna(0).clip(lower=0)
    # Give the last event a minimal visible width if zero
    if len(widths) > 0 and widths.iloc[-1] == 0:
        # Use 1% of total span or 10ms, whichever is larger
        total_span = offsets_ms.iloc[-1] if len(offsets_ms) > 1 else 10
        widths.iloc[-1] = max(total_span * 0.01, 10)

    # Truncate message labels for Y-axis readability
    labels = timeline["message"].str[:80]
    # Add row numbers for uniqueness
    labels = [f"{i + 1}. {lbl}" for i, lbl in enumerate(labels)]

    # Build hover text
    hover_texts = []
    for _, row in timeline.iterrows():
        ts_str = str(row["timestamp"])
        eff = row["effective_duration_ms"]
        raw = row.get("raw_duration_ms")
        parts = [
            f"<b>{row['message']}</b>",
            f"Timestamp: {ts_str}",
            f"Effective duration: {_fmt_dur(eff)}",
            f"Raw duration: {_fmt_dur(raw)}",
        ]
        # Include any raw_ columns for debugging
        for col in timeline.columns:
            if col.startswith("raw_") and col not in ("raw_duration_ms",):
                parts.append(f"{col}: {row[col]}")
        hover_texts.append("<br>".join(parts))

    fig = go.Figure(
        go.Bar(
            y=labels,
            x=widths,
            base=offsets_ms,
            orientation="h",
            marker_color="steelblue",
            hovertext=hover_texts,
            hoverinfo="text",
        )
    )

    fig.update_layout(
        title="TimeTrace Timeline",
        xaxis_title="Time offset (ms)",
        yaxis_title="Events",
        yaxis=dict(autorange="reversed"),
        height=max(400, len(timeline) * 28 + 100),
        margin=dict(l=20, r=20, t=50, b=40),
        hoverlabel=dict(align="left"),
    )

    return fig


def _fmt_dur(value) -> str:
    """Format a duration value for display."""
    if pd.isna(value):
        return "— (last event)"
    return f"{value:,.2f} ms"
