"""Tests for Calendar collector using COM/MAPI."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from timeline.collectors.calendar import CalendarCollector
from timeline.config import CalendarCollectorConfig
from timeline.models import DateRange


class TestCalendarCollector:
    """Test Calendar collector functionality."""

    def setup_method(self) -> None:
        """Initialize test collector."""
        self.config = CalendarCollectorConfig(
            enabled=True,
            users=[],  # Not used for COM
        )
        self.collector = CalendarCollector(self.config)

    def test_source_name(self) -> None:
        """Test source identifier."""
        assert self.collector.source_name() == "calendar"

    def test_is_cheap(self) -> None:
        """Test that calendar is marked as cheap."""
        assert self.collector.is_cheap() is True

    @pytest.mark.asyncio
    async def test_collect_with_no_outlook(self) -> None:
        """Test graceful fallback when Outlook not available."""
        with patch("timeline.collectors.calendar.win32com.client.Dispatch") as mock_dispatch:
            mock_dispatch.side_effect = Exception("Outlook not available")
            dr = DateRange.for_date(datetime.now().date())
            events = await self.collector.collect(dr)
            assert events == []

    @pytest.mark.asyncio
    async def test_collect_graceful_fallback(self) -> None:
        """Test that collection gracefully handles errors (no outlook)."""
        with patch("timeline.collectors.calendar.win32com.client.Dispatch") as mock_dispatch:
            mock_dispatch.side_effect = Exception("Outlook error")
            dr = DateRange.for_date(datetime.now().date())
            events = await self.collector.collect(dr)
            # Should return empty list, not crash
            assert events == []

    def test_item_to_raw_event(self) -> None:
        """Test conversion of Outlook item to RawEvent."""
        mock_item = MagicMock()
        mock_item.Subject = "Team Meeting"
        mock_item.Start = datetime(2026, 2, 6, 9, 0, 0)
        mock_item.End = datetime(2026, 2, 6, 10, 0, 0)
        mock_item.Location = "Conference Room"
        mock_item.Organizer = "alice@example.com"
        mock_item.Body = "Discussion"

        raw_event = CalendarCollector._item_to_raw_event(mock_item)

        assert raw_event is not None
        assert raw_event.source == "calendar"
        assert raw_event.raw_data["subject"] == "Team Meeting"
        assert raw_event.raw_data["location"] == "Conference Room"

    def test_item_to_raw_event_missing_subject(self) -> None:
        """Test that items without subject are skipped."""
        mock_item = MagicMock()
        mock_item.Subject = ""
        mock_item.Start = datetime(2026, 2, 6, 9, 0, 0)

        raw_event = CalendarCollector._item_to_raw_event(mock_item)
        assert raw_event is None

    def test_item_to_raw_event_no_start(self) -> None:
        """Test that items without start time are skipped."""
        mock_item = MagicMock()
        mock_item.Subject = "Meeting"
        mock_item.Start = None

        raw_event = CalendarCollector._item_to_raw_event(mock_item)
        assert raw_event is None


# @pytest.mark.integration
class TestCalendarIntegration:
    """Integration tests that actually call Outlook COM (run with: pytest -m integration)."""

    def setup_method(self) -> None:
        """Initialize test collector."""
        self.config = CalendarCollectorConfig(enabled=True, users=[])
        self.collector = CalendarCollector(self.config)

    @pytest.mark.asyncio
    async def test_collect_real_events(self) -> None:
        """Collect actual calendar events from Outlook to verify timezone handling."""
        from datetime import date

        # Collect events for today (Feb 9, 2026 - Monday)
        today = date.today()
        dr = DateRange.for_date(today)

        events = await self.collector.collect(dr)

        # Print events for manual verification
        print(f"\n\n=== Collected {len(events)} events for {today} ===")
        for event in events:
            print(f"Subject: {event.raw_data.get('subject')}")
            print(f"  Start: {event.raw_data.get('start')}")
            print(f"  End: {event.raw_data.get('end')}")
            print(f"  Event timestamp: {event.event_timestamp}")
            print(f"  Mailbox: {event.raw_data.get('mailbox')}")
            print()

        # Basic assertions
        if events:
            assert all(e.source == "calendar" for e in events)
            assert all(e.event_timestamp is not None for e in events)
            assert all("subject" in e.raw_data for e in events)
