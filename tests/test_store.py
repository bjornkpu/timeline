"""Tests for SQLite storage layer."""

from datetime import UTC, date, datetime

from timeline.models import DateRange, PeriodType, RawEvent, Summary, TimelineEvent
from timeline.store import TimelineStore


class TestRawEventStorage:
    def test_save_and_retrieve(self, store: TimelineStore):
        event = RawEvent(
            source="git",
            collected_at=datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
            raw_data={"hash": "abc123", "message": "fix bug"},
            event_timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
        )
        count = store.save_raw([event])
        assert count == 1

        dr = DateRange.for_date(date(2026, 2, 6))
        results = store.get_raw(dr)
        assert len(results) == 1
        assert results[0].source == "git"
        assert results[0].raw_data["hash"] == "abc123"

    def test_idempotent_insert(self, store: TimelineStore):
        event = RawEvent(
            source="git",
            collected_at=datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
            raw_data={"hash": "abc123", "message": "fix bug"},
            event_timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
        )
        store.save_raw([event])
        store.save_raw([event])  # duplicate

        dr = DateRange.for_date(date(2026, 2, 6))
        results = store.get_raw(dr)
        assert len(results) == 1

    def test_filter_by_source(self, store: TimelineStore):
        now = datetime(2026, 2, 6, 12, 0, tzinfo=UTC)
        ts = datetime(2026, 2, 6, 9, 0, tzinfo=UTC)
        store.save_raw(
            [
                RawEvent(source="git", collected_at=now, raw_data={"id": "1"}, event_timestamp=ts),
                RawEvent(
                    source="browser", collected_at=now, raw_data={"id": "2"}, event_timestamp=ts
                ),
            ]
        )

        dr = DateRange.for_date(date(2026, 2, 6))
        git_events = store.get_raw(dr, source="git")
        assert len(git_events) == 1
        assert git_events[0].source == "git"

    def test_has_raw(self, store: TimelineStore):
        dr = DateRange.for_date(date(2026, 2, 6))
        assert not store.has_raw(dr, "git")

        store.save_raw(
            [
                RawEvent(
                    source="git",
                    collected_at=datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
                    raw_data={"id": "1"},
                    event_timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
                )
            ]
        )
        assert store.has_raw(dr, "git")
        assert not store.has_raw(dr, "browser")

    def test_delete_raw(self, store: TimelineStore):
        now = datetime(2026, 2, 6, 12, 0, tzinfo=UTC)
        ts = datetime(2026, 2, 6, 9, 0, tzinfo=UTC)
        store.save_raw(
            [
                RawEvent(source="git", collected_at=now, raw_data={"id": "1"}, event_timestamp=ts),
                RawEvent(
                    source="toggl", collected_at=now, raw_data={"id": "2"}, event_timestamp=ts
                ),
            ]
        )

        dr = DateRange.for_date(date(2026, 2, 6))
        deleted = store.delete_raw(dr, "toggl")
        assert deleted == 1
        assert store.has_raw(dr, "git")
        assert not store.has_raw(dr, "toggl")

    def test_queries_by_event_timestamp_not_collected_at(self, store: TimelineStore):
        """Events collected today for yesterday should be found when querying yesterday."""
        store.save_raw(
            [
                RawEvent(
                    source="git",
                    collected_at=datetime(2026, 2, 7, 12, 0, tzinfo=UTC),  # collected today
                    raw_data={"hash": "abc123"},
                    event_timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),  # happened yesterday
                )
            ]
        )
        yesterday = DateRange.for_date(date(2026, 2, 6))
        today = DateRange.for_date(date(2026, 2, 7))

        assert len(store.get_raw(yesterday)) == 1
        assert len(store.get_raw(today)) == 0


class TestEventStorage:
    def test_save_and_retrieve(self, store: TimelineStore):
        event = TimelineEvent(
            timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
            source="git",
            category="bugfix",
            description="fix auth",
            project="Customer Platform",
        )
        count = store.save_events([event])
        assert count == 1

        dr = DateRange.for_date(date(2026, 2, 6))
        results = store.get_events(dr)
        assert len(results) == 1
        assert results[0].description == "fix auth"
        assert results[0].project == "Customer Platform"

    def test_idempotent_insert(self, store: TimelineStore):
        event = TimelineEvent(
            timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
            source="git",
            category="bugfix",
            description="fix auth",
        )
        store.save_events([event])
        store.save_events([event])

        dr = DateRange.for_date(date(2026, 2, 6))
        results = store.get_events(dr)
        assert len(results) == 1

    def test_filter_by_project(self, store: TimelineStore):
        store.save_events(
            [
                TimelineEvent(
                    timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
                    source="git",
                    category="bugfix",
                    description="fix auth",
                    project="Customer Platform",
                ),
                TimelineEvent(
                    timestamp=datetime(2026, 2, 6, 10, 0, tzinfo=UTC),
                    source="git",
                    category="chore",
                    description="update deps",
                    project="Internal Tooling",
                ),
            ]
        )

        dr = DateRange.for_date(date(2026, 2, 6))
        results = store.get_events(dr, project="Customer Platform")
        assert len(results) == 1
        assert results[0].project == "Customer Platform"

    def test_ordered_by_timestamp(self, store: TimelineStore):
        store.save_events(
            [
                TimelineEvent(
                    timestamp=datetime(2026, 2, 6, 15, 0, tzinfo=UTC),
                    source="git",
                    category="code",
                    description="afternoon work",
                ),
                TimelineEvent(
                    timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
                    source="git",
                    category="code",
                    description="morning work",
                ),
            ]
        )

        dr = DateRange.for_date(date(2026, 2, 6))
        results = store.get_events(dr)
        assert results[0].description == "morning work"
        assert results[1].description == "afternoon work"

    def test_delete_events(self, store: TimelineStore):
        store.save_events(
            [
                TimelineEvent(
                    timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
                    source="git",
                    category="code",
                    description="work",
                ),
            ]
        )
        dr = DateRange.for_date(date(2026, 2, 6))
        deleted = store.delete_events(dr)
        assert deleted == 1
        assert store.get_events(dr) == []


class TestSummaryStorage:
    def test_save_and_retrieve(self, store: TimelineStore):
        summary = Summary(
            date_start=date(2026, 2, 6),
            date_end=date(2026, 2, 6),
            period_type=PeriodType.DAY,
            summary="Worked on auth fixes and documentation",
            model="claude-opus-4-6",
        )
        store.save_summary(summary)

        dr = DateRange.for_date(date(2026, 2, 6))
        result = store.get_summary(dr, PeriodType.DAY)
        assert result is not None
        assert result.summary == "Worked on auth fixes and documentation"

    def test_upsert_summary(self, store: TimelineStore):
        """Re-running summarizer should update existing summary."""
        dr = DateRange.for_date(date(2026, 2, 6))

        store.save_summary(
            Summary(
                date_start=date(2026, 2, 6),
                date_end=date(2026, 2, 6),
                period_type=PeriodType.DAY,
                summary="First version",
                model="claude-opus-4-6",
            )
        )
        store.save_summary(
            Summary(
                date_start=date(2026, 2, 6),
                date_end=date(2026, 2, 6),
                period_type=PeriodType.DAY,
                summary="Updated version",
                model="claude-opus-4-6",
            )
        )

        result = store.get_summary(dr, PeriodType.DAY)
        assert result is not None
        assert result.summary == "Updated version"

    def test_no_summary(self, store: TimelineStore):
        dr = DateRange.for_date(date(2026, 2, 6))
        assert store.get_summary(dr, PeriodType.DAY) is None
