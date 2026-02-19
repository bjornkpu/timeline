"""Core data models for the timeline pipeline: raw → events → summaries."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Any, Self


class PeriodType(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


@dataclass(frozen=True)
class DateRange:
    """Inclusive date range for querying events."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            msg = f"start ({self.start}) must be <= end ({self.end})"
            raise ValueError(msg)

    @classmethod
    def for_date(cls, d: date) -> Self:
        return cls(start=d, end=d)

    @classmethod
    def today(cls) -> Self:
        return cls.for_date(date.today())

    @classmethod
    def yesterday(cls) -> Self:
        return cls.for_date(date.today() - timedelta(days=1))

    @classmethod
    def this_week(cls) -> Self:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        return cls(start=monday, end=sunday)

    @classmethod
    def for_week(cls, year: int, week: int) -> Self:
        """Create DateRange from ISO week number (Monday-Sunday).

        Args:
            year: Year (e.g., 2026)
            week: ISO week number (1-53)

        Example:
            >>> DateRange.for_week(2026, 8)  # Week 8 of 2026 (Feb 16-22)
        """
        jan_4 = date(year, 1, 4)
        week_1_monday = jan_4 - timedelta(days=jan_4.weekday())
        monday = week_1_monday + timedelta(weeks=week - 1)
        sunday = monday + timedelta(days=6)
        return cls(start=monday, end=sunday)

    @classmethod
    def parse_week(cls, week_str: str) -> Self:
        """Parse ISO week string: '2026-W08', 'W08' (current year), '8' (current year).

        Args:
            week_str: Week identifier

        Raises:
            ValueError: If format invalid

        Example:
            >>> DateRange.parse_week("8")  # Week 8 of current year
            >>> DateRange.parse_week("W08")  # Week 8 of current year
            >>> DateRange.parse_week("2026-W08")  # Week 8 of 2026
        """
        week_str = week_str.strip().upper()

        if week_str.isdigit():
            return cls.for_week(date.today().year, int(week_str))

        if week_str.startswith("W"):
            return cls.for_week(date.today().year, int(week_str[1:]))

        parts = week_str.split("-W")
        if len(parts) != 2:
            msg = f"Invalid week format: '{week_str}'. Use 'YYYY-Wnn', 'Wnn', or 'n'."
            raise ValueError(msg)
        return cls.for_week(int(parts[0]), int(parts[1]))

    @property
    def start_utc(self) -> datetime:
        return datetime.combine(self.start, datetime.min.time(), tzinfo=UTC)

    @property
    def end_utc(self) -> datetime:
        return datetime.combine(self.end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)

    @classmethod
    def last_n_months(cls, n: int) -> Self:
        today = date.today()
        start = date(today.year, today.month, 1)
        for _ in range(n):
            start = (start - timedelta(days=1)).replace(day=1)
        return cls(start=start, end=today - timedelta(days=1))

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def iter_days(self) -> Iterator[DateRange]:
        """Yield a single-day DateRange for each day in the range."""
        current = self.start
        while current <= self.end:
            yield DateRange.for_date(current)
            current += timedelta(days=1)


@dataclass
class RawEvent:
    """Raw collector output — source-specific, stored as-is."""

    source: str
    collected_at: datetime
    raw_data: dict[str, Any]
    event_timestamp: datetime | None = None  # actual event time from source
    event_hash: str = ""

    def __post_init__(self) -> None:
        if not self.event_hash:
            self.event_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Deterministic hash for idempotent storage."""
        canonical = json.dumps(
            {"source": self.source, "data": self.raw_data},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    id: int | None = field(default=None, repr=False)


@dataclass
class TimelineEvent:
    """Normalized, enriched timeline event — the core unit of the timeline."""

    timestamp: datetime  # UTC
    source: str
    category: str
    description: str
    project: str | None = None
    end_time: datetime | None = None  # UTC
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_event_id: int | None = None
    event_hash: str = ""

    def __post_init__(self) -> None:
        if not self.event_hash:
            self.event_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        canonical = json.dumps(
            {
                "timestamp": self.timestamp.isoformat(),
                "source": self.source,
                "description": self.description,
            },
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    id: int | None = field(default=None, repr=False)


@dataclass(frozen=True)
class SourceFilter:
    """Filter to include or exclude timeline events by source."""

    mode: str  # 'include' or 'exclude'
    sources: frozenset[str]  # source names to filter by

    def __init__(self, mode: str, sources: set[str] | list[str]) -> None:
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "sources", frozenset(sources))


@dataclass
class Summary:
    """LLM-generated summary for a time period."""

    date_start: date
    date_end: date
    period_type: PeriodType
    summary: str
    model: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: int | None = field(default=None, repr=False)
