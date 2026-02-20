"""SQLite storage layer — raw events, timeline events, summaries."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from timeline.models import (
    DateRange,
    PeriodType,
    RawEvent,
    SourceFilter,
    Summary,
    TimelineEvent,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    event_timestamp TEXT,
    raw_data TEXT NOT NULL,
    event_hash TEXT UNIQUE NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_events(source);
CREATE INDEX IF NOT EXISTS idx_raw_hash ON raw_events(event_hash);
CREATE INDEX IF NOT EXISTS idx_raw_event_timestamp ON raw_events(event_timestamp);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_event_id INTEGER REFERENCES raw_events(id),
    timestamp TEXT NOT NULL,
    end_time TEXT,
    source TEXT NOT NULL,
    project TEXT,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    metadata TEXT,
    event_hash TEXT UNIQUE NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project);
CREATE INDEX IF NOT EXISTS idx_events_hash ON events(event_hash);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_start TEXT NOT NULL,
    date_end TEXT NOT NULL,
    period_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(date_start, date_end, period_type)
);
CREATE INDEX IF NOT EXISTS idx_summaries_period ON summaries(date_start, date_end, period_type);
"""


def _to_utc_iso(dt: datetime) -> str:
    """Normalize a datetime to UTC and return ISO string for consistent storage."""
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).isoformat()
    # Treat naive datetimes as UTC to avoid mixing naive/aware in queries
    return dt.replace(tzinfo=UTC).isoformat()


class TimelineStore:
    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            if self._db_path != ":memory:":
                Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        conn = self._conn
        if conn is None:
            return
        conn.executescript(SCHEMA)
        self._migrate(conn)
        conn.commit()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Apply schema migrations for existing databases."""
        # Check if event_timestamp column exists on raw_events
        cursor = conn.execute("PRAGMA table_info(raw_events)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "event_timestamp" not in columns:
            conn.execute("ALTER TABLE raw_events ADD COLUMN event_timestamp TEXT")
            # Backfill from raw_data JSON where possible
            rows = conn.execute("SELECT id, raw_data FROM raw_events").fetchall()
            for row in rows:
                try:
                    data = json.loads(row["raw_data"])
                    ts = data.get("timestamp")
                    if ts:
                        conn.execute(
                            "UPDATE raw_events SET event_timestamp = ? WHERE id = ?",
                            (ts, row["id"]),
                        )
                except (json.JSONDecodeError, KeyError):
                    pass

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # --- Raw events ---

    def save_raw(self, events: list[RawEvent]) -> int:
        """Insert raw events, skipping duplicates. Returns count of new inserts."""
        conn = self._connect()
        inserted = 0
        for event in events:
            try:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO raw_events "
                    "(source, collected_at, event_timestamp, raw_data, event_hash) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        event.source,
                        _to_utc_iso(event.collected_at),
                        _to_utc_iso(event.event_timestamp) if event.event_timestamp else None,
                        json.dumps(event.raw_data, default=str),
                        event.event_hash,
                    ),
                )
                if cursor.rowcount > 0:
                    inserted += 1
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        return inserted

    def get_raw(self, date_range: DateRange, source: str | None = None) -> list[RawEvent]:
        conn = self._connect()
        query = (
            "SELECT id, source, collected_at, event_timestamp, raw_data, event_hash "
            "FROM raw_events "
            "WHERE event_timestamp >= ? AND event_timestamp < ?"
        )
        params: list[str] = [
            date_range.start_utc.isoformat(),
            date_range.end_utc.isoformat(),
        ]
        if source:
            query += " AND source = ?"
            params.append(source)
        query += " ORDER BY event_timestamp"

        rows = conn.execute(query, params).fetchall()
        return [
            RawEvent(
                source=row["source"],
                collected_at=datetime.fromisoformat(row["collected_at"]),
                raw_data=json.loads(row["raw_data"]),
                event_timestamp=(
                    datetime.fromisoformat(row["event_timestamp"])
                    if row["event_timestamp"]
                    else None
                ),
                event_hash=row["event_hash"],
                id=row["id"],
            )
            for row in rows
        ]

    def has_raw(self, date_range: DateRange, source: str) -> bool:
        conn = self._connect()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM raw_events "
            "WHERE event_timestamp >= ? AND event_timestamp < ? AND source = ?",
            (
                date_range.start_utc.isoformat(),
                date_range.end_utc.isoformat(),
                source,
            ),
        ).fetchone()
        return row["cnt"] > 0 if row else False

    def delete_raw(self, date_range: DateRange, source: str) -> int:
        """Delete raw events for a source+date range. For --refresh."""
        conn = self._connect()
        cursor = conn.execute(
            "DELETE FROM raw_events "
            "WHERE event_timestamp >= ? AND event_timestamp < ? AND source = ?",
            (
                date_range.start_utc.isoformat(),
                date_range.end_utc.isoformat(),
                source,
            ),
        )
        conn.commit()
        return cursor.rowcount

    # --- Timeline events ---

    def save_events(self, events: list[TimelineEvent]) -> int:
        conn = self._connect()
        inserted = 0
        for event in events:
            try:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO events "
                    "(raw_event_id, timestamp, end_time, source, project, category, "
                    "description, metadata, event_hash) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.raw_event_id,
                        _to_utc_iso(event.timestamp),
                        _to_utc_iso(event.end_time) if event.end_time else None,
                        event.source,
                        event.project,
                        event.category,
                        event.description,
                        json.dumps(event.metadata, default=str),
                        event.event_hash,
                    ),
                )
                if cursor.rowcount > 0:
                    inserted += 1
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        return inserted

    def get_events(
        self,
        date_range: DateRange,
        source: str | None = None,
        project: str | None = None,
        source_filter: SourceFilter | None = None,
    ) -> list[TimelineEvent]:
        conn = self._connect()
        query = (
            "SELECT id, raw_event_id, timestamp, end_time, source, project, "
            "category, description, metadata, event_hash FROM events "
            "WHERE timestamp >= ? AND timestamp < ?"
        )
        params: list[str | int] = [
            date_range.start_utc.isoformat(),
            date_range.end_utc.isoformat(),
        ]
        if source:
            query += " AND source = ?"
            params.append(source)
        if project:
            query += " AND project = ?"
            params.append(project)
        if source_filter:
            sources_list = list(source_filter.sources)
            placeholders = ",".join(["?" for _ in sources_list])
            if source_filter.mode == "include":
                query += f" AND source IN ({placeholders})"
            else:  # exclude
                query += f" AND source NOT IN ({placeholders})"
            params.extend(sources_list)
        query += " ORDER BY timestamp"

        rows = conn.execute(query, params).fetchall()
        return [
            TimelineEvent(
                timestamp=datetime.fromisoformat(row["timestamp"]),
                source=row["source"],
                category=row["category"],
                description=row["description"],
                project=row["project"],
                end_time=(datetime.fromisoformat(row["end_time"]) if row["end_time"] else None),
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                raw_event_id=row["raw_event_id"],
                event_hash=row["event_hash"],
                id=row["id"],
            )
            for row in rows
        ]

    def delete_events(self, date_range: DateRange, source: str | None = None) -> int:
        """Delete events for re-transformation."""
        conn = self._connect()
        query = "DELETE FROM events WHERE timestamp >= ? AND timestamp < ?"
        params: list[str] = [
            date_range.start_utc.isoformat(),
            date_range.end_utc.isoformat(),
        ]
        if source:
            query += " AND source = ?"
            params.append(source)
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor.rowcount

    # --- Summaries ---

    def save_summary(self, summary: Summary) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT OR REPLACE INTO summaries "
            "(date_start, date_end, period_type, summary, model, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                summary.date_start.isoformat(),
                summary.date_end.isoformat(),
                summary.period_type.value,
                summary.summary,
                summary.model,
                summary.created_at.isoformat(),
            ),
        )
        conn.commit()

    def get_summary(self, date_range: DateRange, period_type: PeriodType) -> Summary | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT id, date_start, date_end, period_type, summary, model, created_at "
            "FROM summaries WHERE date_start = ? AND date_end = ? AND period_type = ?",
            (
                date_range.start.isoformat(),
                date_range.end.isoformat(),
                period_type.value,
            ),
        ).fetchone()
        if row is None:
            return None
        return Summary(
            date_start=datetime.fromisoformat(row["date_start"]).date()
            if "T" in row["date_start"]
            else datetime.strptime(row["date_start"], "%Y-%m-%d").date(),
            date_end=datetime.fromisoformat(row["date_end"]).date()
            if "T" in row["date_end"]
            else datetime.strptime(row["date_end"], "%Y-%m-%d").date(),
            period_type=PeriodType(row["period_type"]),
            summary=row["summary"],
            model=row["model"],
            created_at=datetime.fromisoformat(row["created_at"]),
            id=row["id"],
        )

    def get_summaries(
        self,
        date_range: DateRange,
        period_type: PeriodType,
    ) -> list[Summary]:
        """Get all summaries within date range for given period type.

        Returns summaries where date_start and date_end fall within the range.
        Ordered by date_start ascending.
        """
        conn = self._connect()
        rows = conn.execute(
            "SELECT id, date_start, date_end, period_type, summary, model, created_at "
            "FROM summaries "
            "WHERE period_type = ? AND date_start >= ? AND date_end <= ? "
            "ORDER BY date_start",
            (
                period_type.value,
                date_range.start.isoformat(),
                date_range.end.isoformat(),
            ),
        ).fetchall()

        return [
            Summary(
                date_start=datetime.fromisoformat(row["date_start"]).date()
                if "T" in row["date_start"]
                else datetime.strptime(row["date_start"], "%Y-%m-%d").date(),
                date_end=datetime.fromisoformat(row["date_end"]).date()
                if "T" in row["date_end"]
                else datetime.strptime(row["date_end"], "%Y-%m-%d").date(),
                period_type=PeriodType(row["period_type"]),
                summary=row["summary"],
                model=row["model"],
                created_at=datetime.fromisoformat(row["created_at"]),
                id=row["id"],
            )
            for row in rows
        ]

    def get_previous_summary(
        self,
        date_range: DateRange,
        period_type: PeriodType,
    ) -> Summary | None:
        """Get the most recent summary before the given date range for the period type.

        Returns the summary where date_end < date_range.start, ordered by date_end desc.
        """
        conn = self._connect()
        row = conn.execute(
            "SELECT id, date_start, date_end, period_type, summary, model, created_at "
            "FROM summaries "
            "WHERE period_type = ? AND date_end < ? "
            "ORDER BY date_end DESC "
            "LIMIT 1",
            (
                period_type.value,
                date_range.start.isoformat(),
            ),
        ).fetchone()
        if row is None:
            return None
        return Summary(
            date_start=datetime.fromisoformat(row["date_start"]).date()
            if "T" in row["date_start"]
            else datetime.strptime(row["date_start"], "%Y-%m-%d").date(),
            date_end=datetime.fromisoformat(row["date_end"]).date()
            if "T" in row["date_end"]
            else datetime.strptime(row["date_end"], "%Y-%m-%d").date(),
            period_type=PeriodType(row["period_type"]),
            summary=row["summary"],
            model=row["model"],
            created_at=datetime.fromisoformat(row["created_at"]),
            id=row["id"],
        )
