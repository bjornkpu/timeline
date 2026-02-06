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
