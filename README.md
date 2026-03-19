# TimeTrace

Lightweight Python Streamlit app to visualize time spent from log data entries.

## Features

- **CSV Upload** — Upload any CSV with `timestamp` and `message` columns (case-insensitive, any column order).
- **Substring Filters** — Exclude log messages containing specific text.
- **Regex Filters** — Exclude log messages matching regex patterns.
- **Duration Threshold** — Hide events shorter than N milliseconds (based on raw pre-filter duration).
- **Timeline Chart** — Horizontal bar chart (Plotly) showing event durations, inspired by Chrome DevTools Network tab.
- **Dual Duration Model** — Raw durations (from full sequence) and effective durations (from filtered sequence) computed separately.
- **Summary Metrics** — Total rows, skipped rows, parsed/kept/filtered counts.
- **Data Tables** — Kept events table and expandable filtered-out events section.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
streamlit run app.py
```

Then open the URL shown in your terminal (typically `http://localhost:8501`).

## CSV Format

The only required columns are:

| Column      | Description                          |
|-------------|--------------------------------------|
| `timestamp` | Datetime value (ISO 8601 recommended)|
| `message`   | Log message text                     |

- Column matching is case-insensitive.
- All other columns are optional and preserved for display.
- Rows with empty messages or unparseable timestamps are skipped.

## File Structure

| File           | Purpose                                      |
|----------------|----------------------------------------------|
| `app.py`       | Streamlit UI, layout, and wiring             |
| `parsing.py`   | CSV reading, column detection, event parsing |
| `filters.py`   | Substring, regex, and duration filtering     |
| `timeline.py`  | Duration calculation and Plotly chart builder |

## Testing

```bash
pip install pytest pytest-cov
python -m pytest tests/ --cov=parsing --cov=filters --cov=timeline
```

All 88 tests pass with 100% coverage across `parsing.py`, `filters.py`, and `timeline.py`.

## Assumptions

- Timestamps should be parseable by pandas (ISO 8601 like `2026-03-19T15:24:17.539Z` works best).
- UTC is assumed when timezone info is present; naive timestamps are coerced to UTC.
- Duration of an event = time to the next *kept* event's timestamp.
- The last event in a sequence has no measurable duration (shown as open-ended).
- Filtering is applied before effective duration calculation.

## Common Issues

| Problem | Solution |
|---------|----------|
| "Missing required columns" error | Ensure your CSV has `timestamp` and `message` columns (case-insensitive). |
| All rows skipped after parsing | Check that timestamps are in a format pandas can parse (ISO 8601 recommended). |
| File too large error | The upload limit is 50 MB. Split large files or pre-filter before uploading. |
| Regex filter has no effect | Patterns longer than 500 characters are silently rejected (ReDoS protection). Invalid regex syntax is also ignored. |
| Timeline shows no bars | All events were filtered out — try resetting filters with the 🔄 button in the sidebar. |
| Duration column shows "—" | The last event in a sequence has no next event, so its duration is undefined. |
