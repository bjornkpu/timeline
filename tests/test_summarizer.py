"""Tests for the LLM summarizer."""

from __future__ import annotations

import subprocess
from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from timeline.config import SummarizerConfig, TimelineConfig
from timeline.models import DateRange, PeriodType, TimelineEvent
from timeline.summarizer import Summarizer, _format_events


@pytest.fixture
def enabled_config(tmp_path) -> TimelineConfig:
    """Config with summarizer enabled."""
    return TimelineConfig(
        db_path=tmp_path / "test.db",
        summarizer=SummarizerConfig(enabled=True),
    )


@pytest.fixture
def date_range_today() -> DateRange:
    return DateRange.for_date(date(2026, 2, 6))


@pytest.fixture
def events() -> list[TimelineEvent]:
    return [
        TimelineEvent(
            timestamp=datetime(2026, 2, 6, 8, 12, 0, tzinfo=UTC),
            source="git",
            category="bugfix",
            description="auth token refresh",
            project="Customer Platform",
            metadata={"insertions": 60, "deletions": 15},
        ),
        TimelineEvent(
            timestamp=datetime(2026, 2, 6, 10, 15, 0, tzinfo=UTC),
            source="git",
            category="docs",
            description="update README",
            project="Customer Platform",
            metadata={"insertions": 45, "deletions": 10},
        ),
        TimelineEvent(
            timestamp=datetime(2026, 2, 6, 13, 30, 0, tzinfo=UTC),
            source="shell",
            category="command",
            description="pytest tests/",
            project=None,
        ),
    ]


class TestFormatEvents:
    def test_formats_basic_event(self, events, enabled_config) -> None:
        result = _format_events(events[:1], enabled_config)
        assert "[git]" in result
        assert "(bugfix)" in result
        assert "Customer Platform:" in result
        assert "auth token refresh" in result
        assert "+60/-15" in result

    def test_formats_event_without_project(self, events, enabled_config) -> None:
        result = _format_events(events[2:], enabled_config)
        assert "unknown:" in result
        assert "pytest tests/" in result

    def test_no_git_stats_for_non_git(self, events, enabled_config) -> None:
        result = _format_events(events[2:], enabled_config)
        assert "+0/-0" not in result


class TestSummarizer:
    def test_disabled_returns_none(self, tmp_path, events, date_range_today) -> None:
        config = TimelineConfig(
            db_path=tmp_path / "test.db",
            summarizer=SummarizerConfig(enabled=False),
        )
        summarizer = Summarizer(config)
        assert summarizer.summarize(events, date_range_today) is None

    def test_empty_events_returns_none(self, enabled_config, date_range_today) -> None:
        summarizer = Summarizer(enabled_config)
        assert summarizer.summarize([], date_range_today) is None

    @patch("timeline.summarizer._run_claude")
    def test_successful_summarization(
        self, mock_run, enabled_config, events, date_range_today
    ) -> None:
        mock_run.return_value = "Spent the day fixing auth bugs and updating docs."

        summarizer = Summarizer(enabled_config)
        result = summarizer.summarize(events, date_range_today)

        assert result is not None
        assert result.summary == "Spent the day fixing auth bugs and updating docs."
        assert result.model == ""
        assert result.period_type == PeriodType.DAY
        assert result.date_start == date(2026, 2, 6)
        assert result.date_end == date(2026, 2, 6)

        # Verify claude was called with correct args
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "3 events" in call_args[0][0]  # prompt
        assert len(call_args[0][1]) > 0  # system prompt

    @patch("timeline.summarizer._run_claude")
    def test_cli_error_returns_none(
        self, mock_run, enabled_config, events, date_range_today
    ) -> None:
        mock_run.side_effect = RuntimeError("claude CLI exited 1: connection failed")

        summarizer = Summarizer(enabled_config)
        result = summarizer.summarize(events, date_range_today)
        assert result is None

    @patch("timeline.summarizer._run_claude")
    def test_timeout_returns_none(self, mock_run, enabled_config, events, date_range_today) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)

        summarizer = Summarizer(enabled_config)
        result = summarizer.summarize(events, date_range_today)
        assert result is None

    @patch("timeline.summarizer._run_claude")
    def test_claude_not_found_returns_none(
        self, mock_run, enabled_config, events, date_range_today
    ) -> None:
        mock_run.side_effect = FileNotFoundError("claude not found")

        summarizer = Summarizer(enabled_config)
        result = summarizer.summarize(events, date_range_today)
        assert result is None

    @patch("timeline.summarizer._run_claude")
    def test_empty_response_returns_none(
        self, mock_run, enabled_config, events, date_range_today
    ) -> None:
        mock_run.return_value = ""

        summarizer = Summarizer(enabled_config)
        result = summarizer.summarize(events, date_range_today)
        assert result is None
