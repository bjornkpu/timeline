"""Tests for core data models."""

from datetime import UTC, date, datetime, timedelta

import pytest

from timeline.models import DateRange, PeriodType, RawEvent, Summary, TimelineEvent


class TestDateRange:
    def test_for_date(self):
        dr = DateRange.for_date(date(2026, 2, 6))
        assert dr.start == date(2026, 2, 6)
        assert dr.end == date(2026, 2, 6)
        assert dr.days == 1

    def test_today(self):
        dr = DateRange.today()
        assert dr.start == date.today()
        assert dr.end == date.today()

    def test_yesterday(self):
        dr = DateRange.yesterday()
        assert dr.start == date.today() - timedelta(days=1)

    def test_this_week(self):
        dr = DateRange.this_week()
        assert dr.start.weekday() == 0  # Monday
        assert dr.days == 7

    def test_invalid_range(self):
        with pytest.raises(ValueError, match="start.*must be <= end"):
            DateRange(start=date(2026, 2, 7), end=date(2026, 2, 6))

    def test_start_utc(self):
        dr = DateRange.for_date(date(2026, 2, 6))
        assert dr.start_utc == datetime(2026, 2, 6, 0, 0, 0, tzinfo=UTC)

    def test_end_utc(self):
        dr = DateRange.for_date(date(2026, 2, 6))
        # end_utc is exclusive: start of next day
        assert dr.end_utc == datetime(2026, 2, 7, 0, 0, 0, tzinfo=UTC)

    def test_multi_day_range(self):
        dr = DateRange(start=date(2026, 2, 3), end=date(2026, 2, 7))
        assert dr.days == 5


class TestRawEvent:
    def test_hash_deterministic(self):
        e1 = RawEvent(
            source="git",
            collected_at=datetime(2026, 2, 6, tzinfo=UTC),
            raw_data={"hash": "abc123", "message": "fix bug"},
        )
        e2 = RawEvent(
            source="git",
            collected_at=datetime(2026, 2, 6, tzinfo=UTC),
            raw_data={"hash": "abc123", "message": "fix bug"},
        )
        assert e1.event_hash == e2.event_hash

    def test_hash_different_data(self):
        e1 = RawEvent(
            source="git",
            collected_at=datetime(2026, 2, 6, tzinfo=UTC),
            raw_data={"hash": "abc123"},
        )
        e2 = RawEvent(
            source="git",
            collected_at=datetime(2026, 2, 6, tzinfo=UTC),
            raw_data={"hash": "def456"},
        )
        assert e1.event_hash != e2.event_hash

    def test_hash_ignores_collected_at(self):
        """Hash is based on source + data, not collection time."""
        e1 = RawEvent(
            source="git",
            collected_at=datetime(2026, 2, 6, 10, 0, tzinfo=UTC),
            raw_data={"hash": "abc123"},
        )
        e2 = RawEvent(
            source="git",
            collected_at=datetime(2026, 2, 6, 15, 0, tzinfo=UTC),
            raw_data={"hash": "abc123"},
        )
        assert e1.event_hash == e2.event_hash


class TestTimelineEvent:
    def test_hash_deterministic(self):
        e1 = TimelineEvent(
            timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
            source="git",
            category="bugfix",
            description="fix auth",
        )
        e2 = TimelineEvent(
            timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
            source="git",
            category="bugfix",
            description="fix auth",
        )
        assert e1.event_hash == e2.event_hash

    def test_hash_uses_timestamp_source_description(self):
        """Different category/project should NOT change hash."""
        e1 = TimelineEvent(
            timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
            source="git",
            category="bugfix",
            description="fix auth",
            project="ProjectA",
        )
        e2 = TimelineEvent(
            timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
            source="git",
            category="feature",
            description="fix auth",
            project="ProjectB",
        )
        assert e1.event_hash == e2.event_hash


class TestSummary:
    def test_creation(self):
        s = Summary(
            date_start=date(2026, 2, 6),
            date_end=date(2026, 2, 6),
            period_type=PeriodType.DAY,
            summary="Worked on auth fixes",
            model="claude-opus-4-6",
        )
        assert s.period_type == PeriodType.DAY
        assert s.created_at is not None
