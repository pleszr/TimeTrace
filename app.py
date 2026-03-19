"""
app.py — TimeTrace: a local log timeline visualizer.

A Streamlit app that reads a CSV file with timestamp and message columns,
lets users filter out unwanted log messages, recomputes durations, and
displays a horizontal timeline chart.

Installation:
    pip install -r requirements.txt

Run:
    streamlit run app.py

Assumptions:
    - CSV must contain 'timestamp' and 'message' columns (case-insensitive).
    - Timestamps should be parseable by pandas (ISO 8601 recommended).
    - All other columns are optional and preserved for debugging.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from parsing import parse_csv, detect_columns
from filters import apply_filters
from timeline import compute_durations_ms, build_timeline_data, build_chart


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="TimeTrace", layout="wide")
st.title("⏱️ TimeTrace")
st.caption("Upload a CSV log file → filter noise → visualize durations")


# ---------------------------------------------------------------------------
# File upload
# ---------------------------------------------------------------------------

MAX_UPLOAD_SIZE_MB = 50

uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"])

if uploaded_file is None:
    st.info("Please upload a CSV file to get started.")
    st.stop()

# Validate file size before processing
file_size_mb = uploaded_file.size / (1024 * 1024)
if file_size_mb > MAX_UPLOAD_SIZE_MB:
    st.error(f"File too large ({file_size_mb:.1f} MB). Maximum allowed size is {MAX_UPLOAD_SIZE_MB} MB.")
    st.stop()

# Read CSV
try:
    raw_df = pd.read_csv(uploaded_file)
except Exception:
    st.error("Failed to read the uploaded file. Please ensure it is a valid CSV.")
    st.stop()

if raw_df.empty:
    st.warning("The uploaded CSV is empty.")
    st.stop()

# Validate required columns
try:
    detect_columns(raw_df)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

# Parse into events
events, skipped_count = parse_csv(raw_df)

if events.empty:
    st.warning("No valid events found after parsing. All rows were skipped.")
    st.stop()

# Compute raw durations on the full parsed set
raw_durations = compute_durations_ms(events)
events["raw_duration_ms"] = raw_durations.values

# ---------------------------------------------------------------------------
# Sidebar — filter controls
# ---------------------------------------------------------------------------

st.sidebar.header("🔍 Filters")

# --- Substring exclude filters ---
st.sidebar.subheader("Exclude by substring")
if "substring_filters" not in st.session_state:
    st.session_state.substring_filters = [""]


def _add_substring():
    st.session_state.substring_filters.append("")


def _remove_substring(idx: int):
    st.session_state.substring_filters.pop(idx)


for i, val in enumerate(st.session_state.substring_filters):
    cols = st.sidebar.columns([4, 1])
    st.session_state.substring_filters[i] = cols[0].text_input(
        f"Substring {i + 1}",
        value=val,
        key=f"sub_{i}",
        label_visibility="collapsed",
        placeholder="e.g. took ms",
    )
    if len(st.session_state.substring_filters) > 1:
        cols[1].button("✕", key=f"sub_rm_{i}", on_click=_remove_substring, args=(i,))

st.sidebar.button("➕ Add substring filter", on_click=_add_substring)

# --- Regex exclude filters ---
st.sidebar.subheader("Exclude by regex")
if "regex_filters" not in st.session_state:
    st.session_state.regex_filters = [""]


def _add_regex():
    st.session_state.regex_filters.append("")


def _remove_regex(idx: int):
    st.session_state.regex_filters.pop(idx)


for i, val in enumerate(st.session_state.regex_filters):
    cols = st.sidebar.columns([4, 1])
    st.session_state.regex_filters[i] = cols[0].text_input(
        f"Regex {i + 1}",
        value=val,
        key=f"re_{i}",
        label_visibility="collapsed",
        placeholder=r"e.g. took ms: \d+",
    )
    if len(st.session_state.regex_filters) > 1:
        cols[1].button("✕", key=f"re_rm_{i}", on_click=_remove_regex, args=(i,))

st.sidebar.button("➕ Add regex filter", on_click=_add_regex)

# --- Raw-duration threshold ---
st.sidebar.subheader("Duration threshold")
max_raw = float(events["raw_duration_ms"].max()) if events["raw_duration_ms"].notna().any() else 1000.0
max_raw = max(max_raw, 1.0)
min_duration_ms = st.sidebar.slider(
    "Hide events shorter than (ms)",
    min_value=0.0,
    max_value=float(max_raw),
    value=0.0,
    step=max(0.1, float(max_raw) / 1000),
    help="Based on raw (pre-filter) duration. Useful for removing tiny log entries.",
)

# --- Max rows slider ---
st.sidebar.subheader("Display")
max_display_rows = st.sidebar.slider(
    "Max rows to display",
    min_value=10,
    max_value=max(len(events), 10),
    value=min(len(events), 200),
)

# --- Reset filters ---
def _reset_filters():
    st.session_state.substring_filters = [""]
    st.session_state.regex_filters = [""]


st.sidebar.button("🔄 Reset filters", on_click=_reset_filters)

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------

active_substrings = [s for s in st.session_state.substring_filters if s.strip()]
active_regexes = [r for r in st.session_state.regex_filters if r.strip()]

filtered_events = apply_filters(
    events,
    exclude_substrings=active_substrings if active_substrings else None,
    exclude_regexes=active_regexes if active_regexes else None,
    min_raw_duration_ms=min_duration_ms,
    raw_durations_ms=events["raw_duration_ms"],
)

# ---------------------------------------------------------------------------
# Build timeline
# ---------------------------------------------------------------------------

timeline = build_timeline_data(events, filtered_events)

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------

st.subheader("📊 Summary")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total CSV rows", len(raw_df))
m2.metric("Skipped rows", skipped_count)
m3.metric("Parsed events", len(events))
m4.metric("Kept events", len(filtered_events))
m5.metric("Filtered out", len(events) - len(filtered_events))

# ---------------------------------------------------------------------------
# Timeline chart
# ---------------------------------------------------------------------------

st.subheader("📈 Timeline")

display_timeline = timeline.head(max_display_rows)

if display_timeline.empty:
    st.info("All events were filtered out. Adjust your filters to see the timeline.")
else:
    fig = build_chart(display_timeline)
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Data tables
# ---------------------------------------------------------------------------

st.subheader("📋 Kept events")
if not timeline.empty:
    display_cols = ["timestamp", "message", "raw_duration_ms", "effective_duration_ms"]
    extra_cols = [c for c in timeline.columns if c.startswith("raw_") and c not in display_cols]
    st.dataframe(
        timeline[display_cols + extra_cols].head(max_display_rows),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No events to display.")

# Filtered-out rows
excluded = events[~events.index.isin(filtered_events.index)]
if not excluded.empty:
    with st.expander(f"🗑️ Filtered-out events ({len(excluded)})"):
        st.dataframe(
            excluded[["timestamp", "message", "raw_duration_ms"]],
            use_container_width=True,
            hide_index=True,
        )
