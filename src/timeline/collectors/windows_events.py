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
            # Collect logon/logoff from System log
            xml_output, _ = self._query_event_log(date_range, log="System")
            if not xml_output:
                return []

            return self._parse_xml_events(
                xml_output,
                date_range,
                event_ids=["7001", "7002"],
                event_type_map={"7001": "logon", "7002": "logoff"},
            )
        except Exception:
            # Silent fail: wevtutil not available, other errors
            return []

    def _query_event_log(self, date_range: DateRange, log: str = "System") -> tuple[str, bool]:
        """Query Windows event log for events.

        Uses wevtutil CLI. Returns (xml_output, access_denied) tuple.

        Args:
            date_range: Date range to query
            log: Event log name ("System" or "Security")

        Returns:
            Tuple of (xml_string, access_denied_flag)
        """
        try:
            result = subprocess.run(
                ["wevtutil", "qe", log],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                # Check if this is an access denied error
                if "Access Denied" in result.stderr or "denied" in result.stderr.lower():
                    return "", True
                return "", False
            return result.stdout, False
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            # wevtutil not found or timed out
            return "", False

    def _parse_xml_events(
        self,
        xml_output: str,
        date_range: DateRange,
        event_ids: list[str] | None = None,
        event_type_map: dict[str, str] | None = None,
    ) -> list[RawEvent]:
        """Parse wevtutil XML output and filter by EventID and date range.

        Args:
            xml_output: Raw XML from wevtutil
            date_range: Date range to filter by
            event_ids: EventIDs to include (default: ["7001", "7002"])
            event_type_map: Mapping of EventID to event_type (default: 7001→logon, 7002→logoff)
        """
        if event_ids is None:
            event_ids = ["7001", "7002"]
        if event_type_map is None:
            event_type_map = {"7001": "logon", "7002": "logoff"}

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
            if event_id_elem is None or event_id_elem.text not in event_ids:
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

            # For logon/logoff events (7001/7002), filter by SessionID
            # For lock/unlock events (4800/4801), no session filtering needed
            if event_id_elem.text in ("7001", "7002"):
                session_id = self._extract_session_id(event_elem, ns)
                if session_id and session_id not in ("0", "1", "6"):
                    # Skip other session types (7+, etc.)
                    continue

            event_id = event_id_elem.text
            event_type = event_type_map.get(event_id, "unknown")

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
        """Extract SessionID or TSId (Terminal Session ID) from EventData.

        EventID 7001/7002 store session info in different fields depending on
        Windows version and provider:
        - SessionID: older format
        - TSId (Terminal Session ID): newer format (0-1 = console, 6+ = RDP)

        Returns empty string if not found (will allow event through).
        """
        event_data = event_elem.find("event:EventData", ns)
        if event_data is not None:
            for data_elem in event_data.findall("event:Data", ns):
                name = data_elem.get("Name")
                text = data_elem.text

                # Try SessionID first (older Windows versions)
                if name == "SessionID" and text:
                    return text.strip()

                # Try TSId (Terminal Session ID, newer Windows versions)
                if name == "TSId" and text:
                    return text.strip()

        # Try ReplacementStrings (older format)
        replacement_strings = event_elem.find("event:ReplacementStrings", ns)
        if replacement_strings is not None:
            strings = replacement_strings.findall("event:String", ns)
            if strings and strings[0].text:
                # First string might be SessionID in some cases
                # For safety, only accept if it looks like a valid ID (numeric)
                text = strings[0].text.strip()
                if text.isdigit():
                    return text

        # Default: return empty string (will allow event through if not explicitly filtered)
        return ""
