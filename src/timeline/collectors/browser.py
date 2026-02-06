"""Browser history collector — reads Firefox/Zen places.sqlite."""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from timeline.collectors.base import Collector
from timeline.config import BrowserCollectorConfig
from timeline.models import DateRange, RawEvent

# Firefox visit types
# 1=link click, 2=typed URL, 3=bookmark, 4=embed, 5=permanent redirect,
# 6=temporary redirect, 7=download, 8=framed link, 9=reload
# We only care about intentional visits
# URLs to skip — internal browser pages and noise
SKIP_URL_PREFIXES = (
    "about:",
    "moz-extension://",
    "chrome://",
    "resource://",
    "blob:",
    "data:",
)


class BrowserCollector(Collector):
    def __init__(self, config: BrowserCollectorConfig) -> None:
        self._config = config

    def source_name(self) -> str:
        return "browser"

    def is_cheap(self) -> bool:
        return True

    def collect(self, date_range: DateRange) -> list[RawEvent]:
        db_path = Path(self._config.places_path).expanduser()
        if not db_path.exists():
            return []

        # Copy the database — Firefox/Zen locks it while running
        try:
            tmp_dir = Path(tempfile.mkdtemp())
            tmp_path = tmp_dir / "places_copy.sqlite"
            shutil.copy2(db_path, tmp_path)
        except (OSError, PermissionError):
            return []

        try:
            return self._query_visits(tmp_path, date_range)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _query_visits(self, db_path: Path, date_range: DateRange) -> list[RawEvent]:
        """Query places.sqlite for visits in date range."""
        now = datetime.now(UTC)

        # Firefox stores visit_date as microseconds since Unix epoch
        start_us = int(date_range.start_utc.timestamp() * 1_000_000)
        end_us = int(date_range.end_utc.timestamp() * 1_000_000)

        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
        except sqlite3.Error:
            return []

        try:
            rows = conn.execute(
                """
                SELECT
                    h.visit_date,
                    h.visit_type,
                    h.from_visit,
                    p.url,
                    p.title,
                    p.visit_count,
                    p.description,
                    p.site_name
                FROM moz_historyvisits h
                JOIN moz_places p ON h.place_id = p.id
                WHERE h.visit_date >= ? AND h.visit_date < ?
                  AND h.visit_type IN (1, 2, 3)
                ORDER BY h.visit_date
                """,
                (start_us, end_us),
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            conn.close()

        events: list[RawEvent] = []
        for row in rows:
            url = row["url"] or ""

            # Skip internal/noise URLs
            if any(url.startswith(prefix) for prefix in SKIP_URL_PREFIXES):
                continue

            ts = datetime.fromtimestamp(row["visit_date"] / 1_000_000, tz=UTC)

            parsed = urlparse(url)
            domain = parsed.netloc or ""

            raw_data = {
                "url": url,
                "title": row["title"] or "",
                "domain": domain,
                "visit_type": row["visit_type"],
                "visit_count": row["visit_count"] or 0,
                "description": row["description"] or "",
                "site_name": row["site_name"] or "",
                "timestamp": ts.isoformat(),
            }

            events.append(
                RawEvent(
                    source="browser",
                    collected_at=now,
                    raw_data=raw_data,
                    event_timestamp=ts,
                )
            )

        return events
