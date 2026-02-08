"""Windows event log collector — reads logon/logoff events from System log."""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from timeline.collectors.base import Collector
from timeline.config import WindowsEventLogCollectorConfig
from timeline.models import DateRange, RawEvent


class WindowsEventLogCollector(Collector):
    """Collects logon/logoff events from Windows System event log."""

    def __init__(self, config: WindowsEventLogCollectorConfig) -> None:
        self._config = config

    def source_name(self) -> str:
        return "windows_events"

    def is_cheap(self) -> bool:
        return True  # Local event log, no API calls

    def collect(self, date_range: DateRange) -> list[RawEvent]:
        """Collect logon/logoff events from Windows System event log.

        Returns empty list if wevtutil fails or is unavailable.
        """
        try:
            xml_output = self._query_event_log(date_range)
            if not xml_output:
                return []
            return self._parse_xml_events(xml_output, date_range)
        except Exception:
            # Silent fail: wevtutil not available, permission issues, parse errors
            return []

    def _query_event_log(self, date_range: DateRange) -> str:
        """Query Windows System event log for EventID 7001 (logon) and 7002 (logoff).

        Uses wevtutil CLI. Returns raw XML string or empty string on failure.
        """
        try:
            # Query System log for EventID 7001/7002 as XML
            result = subprocess.run(
                ["wevtutil", "qe", "System"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return ""
            return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            # wevtutil not found or timed out
            return ""

    def _parse_xml_events(self, xml_output: str, date_range: DateRange) -> list[RawEvent]:
        """Parse wevtutil XML output and filter by EventID 7001/7002 and SessionID=0."""
        events: list[RawEvent] = []
        now = datetime.now(UTC)
        start_utc = date_range.start_utc
        end_utc = date_range.end_utc

        # wevtutil outputs multiple <Event> elements concatenated (not wrapped in root)
        # Wrap them in a root element to parse as valid XML
        xml_wrapped = f"<root>{xml_output}</root>"

        try:
            root = ET.fromstring(xml_wrapped)
        except ET.ParseError:
            return []

        ns = {"event": "http://schemas.microsoft.com/win/2004/08/events/event"}

        for event_elem in root.findall(".//event:Event", ns):
            system = event_elem.find("event:System", ns)
            if system is None:
                continue

            # Extract EventID
            event_id_elem = system.find("event:EventID", ns)
            if event_id_elem is None or event_id_elem.text not in ("7001", "7002"):
                continue

            # Extract TimeCreated
            time_created_elem = system.find("event:TimeCreated", ns)
            if time_created_elem is None or "SystemTime" not in time_created_elem.attrib:
                continue

            try:
                ts_str = time_created_elem.attrib["SystemTime"]
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                ts_utc = ts.astimezone(UTC)
            except (ValueError, KeyError):
                continue

            # Filter by date range
            if ts_utc < start_utc or ts_utc >= end_utc:
                continue

            # Extract SessionID from EventData (try both old and new formats)
            session_id = self._extract_session_id(event_elem, ns)
            if session_id != "0":
                # Only include console sessions (SessionID=0)
                continue

            event_id = event_id_elem.text
            event_type = "logon" if event_id == "7001" else "logoff"

            events.append(
                RawEvent(
                    source="windows_events",
                    collected_at=now,
                    raw_data={
                        "event_type": event_type,
                        "event_id": int(event_id),
                        "timestamp": ts_utc.isoformat(),
                    },
                    event_timestamp=ts_utc,
                )
            )

        return events

    def _extract_session_id(self, event_elem: ET.Element, ns: dict[str, str]) -> str:
        """Extract SessionID from EventData or ReplacementStrings.

        EventID 7001/7002 store SessionID in different places depending on
        Windows version and provider. Return "0" if not found (to exclude).
        """
        # Try EventData with Data[@Name="SessionID"]
        event_data = event_elem.find("event:EventData", ns)
        if event_data is not None:
            for data_elem in event_data.findall("event:Data", ns):
                if data_elem.get("Name") == "SessionID" and data_elem.text:
                    return data_elem.text.strip()

        # Try ReplacementStrings (older format)
        replacement_strings = event_elem.find("event:ReplacementStrings", ns)
        if replacement_strings is not None:
            strings = replacement_strings.findall("event:String", ns)
            if strings and strings[0].text:
                # First string might be SessionID in some cases
                # For safety, only accept if it looks like a valid SessionID (0-9)
                text = strings[0].text.strip()
                if text.isdigit():
                    return text

        # Default: return empty (will be filtered out, excluding non-console sessions)
        return ""
