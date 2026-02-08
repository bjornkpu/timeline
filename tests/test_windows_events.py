"""Tests for Windows event log collector."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from timeline.collectors.windows_events import WindowsEventLogCollector
from timeline.config import WindowsEventLogCollectorConfig
from timeline.models import DateRange


@pytest.fixture
def collector() -> WindowsEventLogCollector:
    """Create a Windows event log collector for testing."""
    config = WindowsEventLogCollectorConfig(enabled=True)
    return WindowsEventLogCollector(config)


class TestWindowsEventLogCollector:
    """Test suite for WindowsEventLogCollector."""

    def test_source_name(self, collector: WindowsEventLogCollector) -> None:
        """Test that source name is correct."""
        assert collector.source_name() == "windows_events"

    def test_is_cheap(self, collector: WindowsEventLogCollector) -> None:
        """Test that collector is marked as cheap (local data)."""
        assert collector.is_cheap() is True

    def test_collect_returns_empty_on_wevtutil_failure(
        self, collector: WindowsEventLogCollector
    ) -> None:
        """Test that collect returns empty list if wevtutil fails."""
        with patch.object(collector, "_query_event_log", return_value=""):
            date_range = DateRange.today()
            events = collector.collect(date_range)
            assert events == []

    def test_collect_returns_empty_on_parse_error(
        self, collector: WindowsEventLogCollector
    ) -> None:
        """Test that collect returns empty list if XML parsing fails."""
        with patch.object(collector, "_query_event_log", return_value="invalid xml"):
            date_range = DateRange.today()
            events = collector.collect(date_range)
            assert events == []

    def test_collect_silent_fail_on_exception(self, collector: WindowsEventLogCollector) -> None:
        """Test that collect returns empty list on any exception."""
        with patch.object(collector, "_query_event_log", side_effect=RuntimeError("test")):
            date_range = DateRange.today()
            events = collector.collect(date_range)
            assert events == []


class TestEventLogParsing:
    """Test XML parsing of event log output."""

    def test_parse_xml_events_empty_output(self, collector: WindowsEventLogCollector) -> None:
        """Test parsing empty XML output."""
        date_range = DateRange.today()
        events = collector._parse_xml_events("", date_range)
        assert events == []

    def test_parse_xml_events_single_logon(self, collector: WindowsEventLogCollector) -> None:
        """Test parsing a single logon event."""
        today = datetime.now(UTC).date()
        timestamp = (
            datetime.combine(today, datetime.min.time(), tzinfo=UTC)
            .replace(hour=14, minute=30)
            .isoformat()
        )
        xml = _make_event_xml(
            event_id="7001",
            timestamp=timestamp.replace("+00:00", "Z"),
            session_id="0",
        )
        date_range = DateRange.today()
        events = collector._parse_xml_events(xml, date_range)

        assert len(events) == 1
        assert events[0].source == "windows_events"
        assert events[0].raw_data["event_type"] == "logon"
        assert events[0].raw_data["event_id"] == 7001
        assert events[0].event_timestamp is not None

    def test_parse_xml_events_single_logoff(self, collector: WindowsEventLogCollector) -> None:
        """Test parsing a single logoff event."""
        today = datetime.now(UTC).date()
        timestamp = (
            datetime.combine(today, datetime.min.time(), tzinfo=UTC)
            .replace(hour=15, minute=30)
            .isoformat()
        )
        xml = _make_event_xml(
            event_id="7002",
            timestamp=timestamp.replace("+00:00", "Z"),
            session_id="0",
        )
        date_range = DateRange.today()
        events = collector._parse_xml_events(xml, date_range)

        assert len(events) == 1
        assert events[0].raw_data["event_type"] == "logoff"
        assert events[0].raw_data["event_id"] == 7002

    def test_parse_xml_events_filters_by_event_id(
        self, collector: WindowsEventLogCollector
    ) -> None:
        """Test that only EventID 7001/7002 are included."""
        xml = _make_event_xml(
            event_id="999",
            timestamp="2025-02-08T14:30:00Z",
            session_id="0",
        )
        date_range = DateRange.today()
        events = collector._parse_xml_events(xml, date_range)

        assert events == []

    def test_parse_xml_events_filters_by_session_id(
        self, collector: WindowsEventLogCollector
    ) -> None:
        """Test that RDP sessions (TSId > 1) are filtered."""
        today = datetime.now(UTC).date()
        timestamp = (
            datetime.combine(today, datetime.min.time(), tzinfo=UTC)
            .replace(hour=14, minute=30)
            .isoformat()
        )
        xml = _make_event_xml(
            event_id="7001",
            timestamp=timestamp.replace("+00:00", "Z"),
            session_id="6",  # RDP session (TSId=6), should be filtered
        )
        date_range = DateRange.today()
        events = collector._parse_xml_events(xml, date_range)

        assert events == []

    def test_parse_xml_events_filters_by_date_range(
        self, collector: WindowsEventLogCollector
    ) -> None:
        """Test that events outside date range are filtered."""
        xml = _make_event_xml(
            event_id="7001",
            timestamp="2025-02-08T14:30:00Z",
            session_id="0",
        )
        # Query for a different day
        date_range = DateRange(
            start=datetime(2025, 2, 9, tzinfo=UTC).date(),
            end=datetime(2025, 2, 9, tzinfo=UTC).date(),
        )
        events = collector._parse_xml_events(xml, date_range)

        assert events == []

    def test_parse_xml_events_multiple_events(self, collector: WindowsEventLogCollector) -> None:
        """Test parsing multiple events."""
        today = datetime.now(UTC).date()
        ts1 = (
            datetime.combine(today, datetime.min.time(), tzinfo=UTC)
            .replace(hour=8, minute=0)
            .isoformat()
        )
        ts2 = (
            datetime.combine(today, datetime.min.time(), tzinfo=UTC)
            .replace(hour=17, minute=0)
            .isoformat()
        )
        xml1 = _make_event_xml(
            event_id="7001",
            timestamp=ts1.replace("+00:00", "Z"),
            session_id="0",
        )
        xml2 = _make_event_xml(
            event_id="7002",
            timestamp=ts2.replace("+00:00", "Z"),
            session_id="0",
        )
        xml = xml1.replace("<root>", "").replace("</root>", "") + xml2.replace(
            "<root>", ""
        ).replace("</root>", "")
        xml = f"<root>{xml}</root>"

        date_range = DateRange.today()
        events = collector._parse_xml_events(xml, date_range)

        assert len(events) == 2
        assert events[0].raw_data["event_type"] == "logon"
        assert events[1].raw_data["event_type"] == "logoff"

    def test_parse_xml_events_missing_time_created(
        self, collector: WindowsEventLogCollector
    ) -> None:
        """Test that events without TimeCreated are skipped."""
        xml = """<root><Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
            <System>
                <EventID>7001</EventID>
            </System>
        </Event></root>"""
        date_range = DateRange.today()
        events = collector._parse_xml_events(xml, date_range)

        assert events == []

    def test_parse_xml_events_invalid_timestamp(self, collector: WindowsEventLogCollector) -> None:
        """Test that events with invalid timestamps are skipped."""
        xml = """<root><Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
            <System>
                <EventID>7001</EventID>
                <TimeCreated SystemTime="not-a-valid-timestamp"/>
            </System>
        </Event></root>"""
        date_range = DateRange.today()
        events = collector._parse_xml_events(xml, date_range)

        assert events == []


class TestSessionIdExtraction:
    """Test SessionID extraction from different event formats."""

    def test_extract_session_id_from_event_data(self, collector: WindowsEventLogCollector) -> None:
        """Test extracting SessionID from EventData element."""
        xml = """<root><Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
            <System>
                <EventID>7001</EventID>
                <TimeCreated SystemTime="2025-02-08T14:30:00Z"/>
            </System>
            <EventData>
                <Data Name="SessionID">0</Data>
            </EventData>
        </Event></root>"""

        ns = {"event": "http://schemas.microsoft.com/win/2004/08/events/event"}
        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml)
        event_elem = root.find(".//event:Event", ns)
        assert event_elem is not None
        session_id = collector._extract_session_id(event_elem, ns)

        assert session_id == "0"

    def test_extract_session_id_empty_returns_empty_string(
        self, collector: WindowsEventLogCollector
    ) -> None:
        """Test that missing SessionID returns empty string."""
        xml = """<root><Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
            <System>
                <EventID>7001</EventID>
            </System>
            <EventData/>
        </Event></root>"""

        ns = {"event": "http://schemas.microsoft.com/win/2004/08/events/event"}
        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml)
        event_elem = root.find(".//event:Event", ns)
        assert event_elem is not None
        session_id = collector._extract_session_id(event_elem, ns)

        assert session_id == ""


class TestQueryEventLog:
    """Test wevtutil command execution."""

    def test_query_event_log_success(self, collector: WindowsEventLogCollector) -> None:
        """Test successful wevtutil execution."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="<Event/>")
            result = collector._query_event_log(DateRange.today())
            assert result == "<Event/>"

    def test_query_event_log_command_not_found(self, collector: WindowsEventLogCollector) -> None:
        """Test that FileNotFoundError (wevtutil not available) returns empty string."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = collector._query_event_log(DateRange.today())
            assert result == ""

    def test_query_event_log_timeout(self, collector: WindowsEventLogCollector) -> None:
        """Test that timeout returns empty string."""
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
            result = collector._query_event_log(DateRange.today())
            assert result == ""

    def test_query_event_log_nonzero_return_code(self, collector: WindowsEventLogCollector) -> None:
        """Test that non-zero return code returns empty string."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = collector._query_event_log(DateRange.today())
            assert result == ""


# Helper function to generate test XML
def _make_event_xml(
    event_id: str,
    timestamp: str,
    session_id: str,
) -> str:
    """Generate a minimal Event XML element for testing."""
    return f"""<root><Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
    <System>
        <EventID>{event_id}</EventID>
        <TimeCreated SystemTime="{timestamp}"/>
    </System>
    <EventData>
        <Data Name="SessionID">{session_id}</Data>
    </EventData>
</Event></root>"""
