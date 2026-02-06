"""Tests for stdout exporter — verify output formatting."""

from datetime import date

from timeline.config import TimelineConfig
from timeline.exporters.stdout import StdoutExporter
from timeline.models import DateRange, PeriodType, Summary, TimelineEvent


def _capture_export(
    events: list[TimelineEvent],
    summary: Summary | None = None,
    group_by: str = "flat",
) -> str:
    """Helper to capture stdout exporter output."""
    config = TimelineConfig()
    config.stdout.group_by = group_by

    exporter = StdoutExporter()

    import io
    from unittest.mock import patch

    buf = io.StringIO()
    with patch("click.echo", side_effect=lambda msg="", **kw: buf.write(str(msg) + "\n")):
        dr = DateRange.for_date(date(2026, 2, 6))
        exporter.export(events, summary, dr, config)

    return buf.getvalue()


class TestFlatExport:
    def test_empty_events(self):
        output = _capture_export([])
        assert "(no events)" in output

    def test_single_event(self, sample_timeline_events):
        output = _capture_export([sample_timeline_events[0]])
        assert "2026-02-06" in output
        assert "auth token refresh" in output
        assert "[git]" in output
        assert "Customer Platform" in output

    def test_multiple_events_chronological(self, sample_timeline_events):
        output = _capture_export(sample_timeline_events)
        # All events should appear
        assert "auth token refresh" in output
        assert "update README" in output
        assert "update deployment config" in output

    def test_shows_stats(self, sample_timeline_events):
        output = _capture_export([sample_timeline_events[0]])
        assert "+60" in output
        assert "-15" in output

    def test_shows_category_badge(self, sample_timeline_events):
        output = _capture_export([sample_timeline_events[0]])
        assert "[bugfix]" in output

    def test_shows_projects(self, sample_timeline_events):
        output = _capture_export(sample_timeline_events)
        assert "Customer Platform" in output
        assert "Internal Tooling" in output

    def test_shows_summary_when_present(self, sample_timeline_events):
        summary = Summary(
            date_start=date(2026, 2, 6),
            date_end=date(2026, 2, 6),
            period_type=PeriodType.DAY,
            summary="Productive day focused on auth fixes",
            model="claude-opus-4-6",
        )
        output = _capture_export(sample_timeline_events, summary=summary)
        assert "Summary" in output
        assert "Productive day focused on auth fixes" in output


class TestPeriodExport:
    def test_morning_afternoon_split(self, sample_timeline_events):
        output = _capture_export(sample_timeline_events, group_by="period")
        assert "Morning" in output
        assert "Afternoon" in output


class TestHourExport:
    def test_hour_blocks(self, sample_timeline_events):
        output = _capture_export(sample_timeline_events, group_by="hour")
        # Should have hour separators
        assert ":00" in output
