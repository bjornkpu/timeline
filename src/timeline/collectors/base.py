"""Abstract base class for collectors."""

from __future__ import annotations

from abc import ABC, abstractmethod

from timeline.models import DateRange, RawEvent


class Collector(ABC):
    """Base class for all data source collectors."""

    @abstractmethod
    def collect(self, date_range: DateRange) -> list[RawEvent]:
        """Collect raw events from the source for the given date range."""
        ...

    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for this collector source."""
        ...

    def is_cheap(self) -> bool:
        """Whether this collector is cheap to re-run (local data vs API).

        Cheap collectors (git, browser, shell) are always re-scanned.
        Expensive collectors (Toggl, APIs) use cached raw data when available.
        """
        return True
