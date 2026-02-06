"""Shell history collector — reads timestamped JSONL from PSReadLine hook."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from timeline.collectors.base import Collector
from timeline.config import ShellCollectorConfig
from timeline.models import DateRange, RawEvent


class ShellCollector(Collector):
    def __init__(self, config: ShellCollectorConfig) -> None:
        self._config = config

    def source_name(self) -> str:
        return "shell"

    def is_cheap(self) -> bool:
        return True

    def collect(self, date_range: DateRange) -> list[RawEvent]:
        log_path = Path(self._config.history_path).expanduser()
        if not log_path.exists():
            return []

        now = datetime.now(UTC)
        events: list[RawEvent] = []
        start = date_range.start_utc
        end = date_range.end_utc

        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue

            entry = self._parse_line(line)
            if entry is None:
                continue

            # Parse timestamp and filter by date range
            try:
                ts = datetime.fromisoformat(entry["timestamp"])
                # Normalize to UTC for comparison
                ts_utc = ts.astimezone(UTC)
            except (KeyError, ValueError):
                continue

            if ts_utc < start or ts_utc >= end:
                continue

            events.append(
                RawEvent(
                    source="shell",
                    collected_at=now,
                    raw_data=entry,
                    event_timestamp=ts_utc,
                )
            )

        return events

    def _parse_line(self, line: str) -> dict | None:
        """Parse a single JSONL line."""
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None
