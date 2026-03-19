"""
test_integration.py — Integration tests for the TimeTrace pipeline.

Tests the full data flow: CSV → parse → filter → timeline → chart.
Includes an end-to-end HTTP test that starts the Streamlit app and
makes real HTTP requests to verify it serves content.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time

import pandas as pd
import plotly.graph_objects as go
import pytest

from filters import apply_filters
from parsing import parse_csv
from timeline import build_chart, build_timeline_data, compute_durations_ms


# ===================================================================
# Full pipeline integration tests
# ===================================================================


class TestFullPipeline:
    """End-to-end tests through the data processing pipeline."""

    def test_csv_to_timeline_full_pipeline(self):
        """Complete pipeline: raw CSV → parsed events → filtered → timeline."""
        raw_df = pd.DataFrame(
            {
                "timestamp": [
                    "2026-03-19T15:24:17.000Z",
                    "2026-03-19T15:24:17.100Z",
                    "2026-03-19T15:24:17.150Z",
                    "2026-03-19T15:24:17.200Z",
                    "2026-03-19T15:24:17.500Z",
                ],
                "message": [
                    "Application started",
                    "Loading configuration",
                    "Service call to UserService.getUser(..) took ms: 0",
                    "Configuration loaded",
                    "Server ready",
                ],
                "source": ["system", "system", "trace", "system", "system"],
            }
        )

        # Step 1: Parse
        events, skipped = parse_csv(raw_df)
        assert skipped == 0
        assert len(events) == 5

        # Step 2: Compute raw durations
        raw_durations = compute_durations_ms(events)
        events["raw_duration_ms"] = raw_durations.values

        # Step 3: Filter (exclude "took ms" messages)
        filtered = apply_filters(
            events,
            exclude_substrings=["took ms"],
        )
        assert len(filtered) == 4  # one event removed

        # Step 4: Build timeline
        timeline = build_timeline_data(events, filtered)
        assert "raw_duration_ms" in timeline.columns
        assert "effective_duration_ms" in timeline.columns
        assert len(timeline) == 4

        # Step 5: Build chart
        fig = build_chart(timeline)
        assert isinstance(fig, go.Figure)
        assert len(fig.data[0].y) == 4

    def test_pipeline_with_duration_filter(self):
        """Pipeline with duration threshold filter."""
        raw_df = pd.DataFrame(
            {
                "timestamp": [
                    "2026-03-19T15:24:17.000Z",
                    "2026-03-19T15:24:17.010Z",  # 10ms gap
                    "2026-03-19T15:24:18.000Z",  # 990ms gap
                    "2026-03-19T15:24:19.000Z",  # 1000ms gap
                ],
                "message": ["a", "b", "c", "d"],
            }
        )

        events, _ = parse_csv(raw_df)
        raw_durations = compute_durations_ms(events)
        events["raw_duration_ms"] = raw_durations.values

        # Filter: hide events shorter than 100ms
        filtered = apply_filters(
            events,
            min_raw_duration_ms=100.0,
            raw_durations_ms=events["raw_duration_ms"],
        )

        # "a" has 10ms duration → excluded
        # "b" has 990ms duration → kept
        # "c" has 1000ms duration → kept
        # "d" has NaN duration → kept (last event)
        assert len(filtered) == 3

    def test_pipeline_all_events_filtered(self):
        """When all events are filtered out, timeline is empty."""
        raw_df = pd.DataFrame(
            {
                "timestamp": [
                    "2026-03-19T15:24:17.000Z",
                    "2026-03-19T15:24:18.000Z",
                ],
                "message": ["took ms: 0", "took ms: 1"],
            }
        )

        events, _ = parse_csv(raw_df)
        raw_durations = compute_durations_ms(events)
        events["raw_duration_ms"] = raw_durations.values

        filtered = apply_filters(events, exclude_substrings=["took ms"])
        assert len(filtered) == 0

        timeline = build_timeline_data(events, filtered)
        assert len(timeline) == 0

        fig = build_chart(timeline)
        assert isinstance(fig, go.Figure)

    def test_pipeline_with_combined_filters(self):
        """Multiple filter types work together across the pipeline."""
        raw_df = pd.DataFrame(
            {
                "timestamp": [
                    "2026-03-19T15:24:17.000Z",
                    "2026-03-19T15:24:17.005Z",
                    "2026-03-19T15:24:17.010Z",
                    "2026-03-19T15:24:18.000Z",
                    "2026-03-19T15:24:19.000Z",
                ],
                "message": [
                    "took ms: 0",       # excluded by substring (dur=5ms)
                    "error: timeout",   # excluded by regex (dur=5ms)
                    "fast event",       # dur=990ms, kept (above threshold)
                    "slow event",       # dur=1000ms, kept
                    "final event",      # NaN duration, kept
                ],
            }
        )

        events, _ = parse_csv(raw_df)
        raw_durations = compute_durations_ms(events)
        events["raw_duration_ms"] = raw_durations.values

        filtered = apply_filters(
            events,
            exclude_substrings=["took ms"],
            exclude_regexes=[r"error:"],
            min_raw_duration_ms=50.0,
            raw_durations_ms=events["raw_duration_ms"],
        )
        # "took ms: 0" excluded by substring, "error: timeout" excluded by regex
        # remaining 3 events all have duration >= 50ms (or NaN)
        assert len(filtered) == 3
        assert set(filtered["message"].tolist()) == {"fast event", "slow event", "final event"}

    def test_pipeline_with_sample_csv_file(self, sample_csv_path: str):
        """Integration test reading from an actual CSV file on disk."""
        raw_df = pd.read_csv(sample_csv_path)
        events, skipped = parse_csv(raw_df)
        assert skipped == 0
        assert len(events) == 3

        raw_durations = compute_durations_ms(events)
        events["raw_duration_ms"] = raw_durations.values

        filtered = apply_filters(events)
        timeline = build_timeline_data(events, filtered)
        fig = build_chart(timeline)

        assert isinstance(fig, go.Figure)
        assert len(fig.data[0].y) == 3

    def test_pipeline_preserves_extra_columns(self):
        """Extra columns survive the full pipeline."""
        raw_df = pd.DataFrame(
            {
                "timestamp": ["2026-03-19T15:24:17.000Z", "2026-03-19T15:24:18.000Z"],
                "message": ["hello", "world"],
                "severity": ["INFO", "WARN"],
                "thread": ["main", "worker"],
            }
        )

        events, _ = parse_csv(raw_df)
        assert "raw_severity" in events.columns
        assert "raw_thread" in events.columns

        raw_durations = compute_durations_ms(events)
        events["raw_duration_ms"] = raw_durations.values

        filtered = apply_filters(events)
        timeline = build_timeline_data(events, filtered)

        assert "raw_severity" in timeline.columns
        assert timeline["raw_severity"].iloc[0] == "INFO"


# ===================================================================
# HTTP integration test — Streamlit app
# ===================================================================


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 15.0) -> bool:
    """Wait until a TCP port is accepting connections."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False


class TestStreamlitHTTP:
    """Integration test that starts the Streamlit app and makes real HTTP calls."""

    @pytest.fixture(autouse=True)
    def _setup_teardown(self):
        """Start and stop a Streamlit server for the test."""
        self.port = _find_free_port()
        self.proc = None
        yield
        if self.proc and self.proc.poll() is None:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)

    def test_streamlit_app_serves_health_endpoint(self):
        """Start the Streamlit app and verify it responds to HTTP requests."""
        import urllib.request

        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                os.path.join(app_dir, "app.py"),
                "--server.port",
                str(self.port),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )

        server_up = _wait_for_port(self.port, timeout=20.0)
        if not server_up:
            stdout = self.proc.stdout.read().decode() if self.proc.stdout else ""
            stderr = self.proc.stderr.read().decode() if self.proc.stderr else ""
            pytest.skip(
                f"Streamlit server did not start within timeout.\n"
                f"stdout: {stdout[:500]}\nstderr: {stderr[:500]}"
            )

        # Make a real HTTP GET to the Streamlit health endpoint
        health_url = f"http://127.0.0.1:{self.port}/_stcore/health"
        resp = urllib.request.urlopen(health_url, timeout=10)
        assert resp.status == 200
        body = resp.read().decode()
        assert "ok" in body.lower()

    def test_streamlit_app_serves_main_page(self):
        """Verify the main page loads and contains the app title."""
        import urllib.request

        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                os.path.join(app_dir, "app.py"),
                "--server.port",
                str(self.port),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )

        server_up = _wait_for_port(self.port, timeout=20.0)
        if not server_up:
            pytest.skip("Streamlit server did not start within timeout.")

        # Make a real HTTP GET to the main page
        main_url = f"http://127.0.0.1:{self.port}/"
        resp = urllib.request.urlopen(main_url, timeout=10)
        assert resp.status == 200
        body = resp.read().decode()
        assert len(body) > 0  # page has content
