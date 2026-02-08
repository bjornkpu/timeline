"""Tests for Calendar event parser."""

from __future__ import annotations

from datetime import UTC, datetime

from timeline.config import TimelineConfig
from timeline.models import RawEvent
from timeline.transformer.parser import Parser


class TestCalendarParser:
    """Test calendar event parsing."""

    def setup_method(self) -> None:
        """Initialize parser and config."""
        self.parser = Parser()
        self.config = TimelineConfig()

    def test_parse_calendar_basic(self) -> None:
        """Test basic calendar event parsing."""
        raw = RawEvent(
            source="calendar",
            collected_at=datetime(2026, 2, 6, 12, 0, 0, tzinfo=UTC),
            raw_data={
                "subject": "Team Standup",
                "start_iso": "2026-02-06T09:00:00+01:00",
                "end_iso": "2026-02-06T09:30:00+01:00",
                "organizer_name": "Alice",
                "organizer_email": "alice@example.com",
                "location": "Teams",
                "account_email": "user@example.com",
                "is_recurring": False,
            },
            event_timestamp=datetime(2026, 2, 6, 8, 0, 0, tzinfo=UTC),
        )

        event = self.parser.parse_calendar(raw, self.config)

        assert event is not None
        assert event.source == "calendar"
        assert event.category == "calendar"
        assert event.description == "Team Standup"
        assert event.project == "user@example.com"
        assert event.end_time == datetime(2026, 2, 6, 8, 30, 0, tzinfo=UTC)
        assert event.metadata["organizer_name"] == "Alice"
        assert event.metadata["location"] == "Teams"

    def test_parse_calendar_missing_subject(self) -> None:
        """Test that events without subject are skipped."""
        raw = RawEvent(
            source="calendar",
            collected_at=datetime(2026, 2, 6, 12, 0, 0, tzinfo=UTC),
            raw_data={
                "subject": "",
                "start_iso": "2026-02-06T09:00:00+01:00",
                "end_iso": "2026-02-06T09:30:00+01:00",
                "account_email": "user@example.com",
            },
            event_timestamp=datetime(2026, 2, 6, 8, 0, 0, tzinfo=UTC),
        )

        event = self.parser.parse_calendar(raw, self.config)

        assert event is None

    def test_parse_calendar_missing_start_time(self) -> None:
        """Test that events without start time are skipped."""
        raw = RawEvent(
            source="calendar",
            collected_at=datetime(2026, 2, 6, 12, 0, 0, tzinfo=UTC),
            raw_data={
                "subject": "Meeting",
                "start_iso": "invalid-date",
                "end_iso": "2026-02-06T09:30:00+01:00",
                "account_email": "user@example.com",
            },
            event_timestamp=datetime(2026, 2, 6, 8, 0, 0, tzinfo=UTC),
        )

        event = self.parser.parse_calendar(raw, self.config)

        assert event is None

    def test_parse_calendar_with_end_time(self) -> None:
        """Test that end_time is properly extracted."""
        raw = RawEvent(
            source="calendar",
            collected_at=datetime(2026, 2, 6, 12, 0, 0, tzinfo=UTC),
            raw_data={
                "subject": "Long Meeting",
                "start_iso": "2026-02-06T14:00:00+01:00",
                "end_iso": "2026-02-06T16:00:00+01:00",
                "account_email": "user@example.com",
                "organizer_name": "",
                "organizer_email": "",
                "location": "",
                "is_recurring": False,
            },
            event_timestamp=datetime(2026, 2, 6, 13, 0, 0, tzinfo=UTC),
        )

        event = self.parser.parse_calendar(raw, self.config)

        assert event is not None
        assert event.end_time == datetime(2026, 2, 6, 15, 0, 0, tzinfo=UTC)

    def test_parse_calendar_without_end_time(self) -> None:
        """Test handling when end_iso is missing."""
        raw = RawEvent(
            source="calendar",
            collected_at=datetime(2026, 2, 6, 12, 0, 0, tzinfo=UTC),
            raw_data={
                "subject": "Quick Sync",
                "start_iso": "2026-02-06T09:00:00+01:00",
                "account_email": "user@example.com",
                "organizer_name": "",
                "organizer_email": "",
                "location": "",
                "is_recurring": False,
            },
            event_timestamp=datetime(2026, 2, 6, 8, 0, 0, tzinfo=UTC),
        )

        event = self.parser.parse_calendar(raw, self.config)

        assert event is not None
        assert event.end_time is None

    def test_parse_calendar_recurring_event(self) -> None:
        """Test parsing recurring event occurrence."""
        raw = RawEvent(
            source="calendar",
            collected_at=datetime(2026, 2, 6, 12, 0, 0, tzinfo=UTC),
            raw_data={
                "subject": "Weekly Standup",
                "start_iso": "2026-02-06T09:00:00+01:00",
                "end_iso": "2026-02-06T09:30:00+01:00",
                "is_recurring": True,
                "account_email": "user@example.com",
                "organizer_name": "Manager",
                "organizer_email": "",
                "location": "Teams",
            },
            event_timestamp=datetime(2026, 2, 6, 8, 0, 0, tzinfo=UTC),
        )

        event = self.parser.parse_calendar(raw, self.config)

        assert event is not None
        assert event.description == "Weekly Standup"
        assert event.metadata["is_recurring"] is True

    def test_parse_calendar_no_project_when_email_empty(self) -> None:
        """Test that project is None when account_email is empty."""
        raw = RawEvent(
            source="calendar",
            collected_at=datetime(2026, 2, 6, 12, 0, 0, tzinfo=UTC),
            raw_data={
                "subject": "Meeting",
                "start_iso": "2026-02-06T09:00:00+01:00",
                "end_iso": "2026-02-06T10:00:00+01:00",
                "account_email": "",
                "organizer_name": "",
                "organizer_email": "",
                "location": "",
                "is_recurring": False,
            },
            event_timestamp=datetime(2026, 2, 6, 8, 0, 0, tzinfo=UTC),
        )

        event = self.parser.parse_calendar(raw, self.config)

        assert event is not None
        assert event.project is None

    def test_parse_calendar_category_always_calendar(self) -> None:
        """Test that category is always 'calendar' regardless of subject."""
        subjects = [
            "Team Meeting",
            "1:1 with Manager",
            "Bug Triage",
        ]

        for subject in subjects:
            raw = RawEvent(
                source="calendar",
                collected_at=datetime(2026, 2, 6, 12, 0, 0, tzinfo=UTC),
                raw_data={
                    "subject": subject,
                    "start_iso": "2026-02-06T09:00:00+01:00",
                    "end_iso": "2026-02-06T10:00:00+01:00",
                    "account_email": "user@example.com",
                    "organizer_name": "",
                    "organizer_email": "",
                    "location": "",
                    "is_recurring": False,
                },
                event_timestamp=datetime(2026, 2, 6, 8, 0, 0, tzinfo=UTC),
            )

            event = self.parser.parse_calendar(raw, self.config)

            assert event is not None
            assert event.category == "calendar", f"Failed for subject: {subject}"
