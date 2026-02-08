"""Abstract base class for collectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from timeline.models import DateRange


class Collector(ABC):
    """Base class for all data source collectors."""

    @abstractmethod
    def collect(
        self, date_range: DateRange
    ) -> Any:  # list[RawEvent] or Coroutine[Any, Any, list[RawEvent]]
        """Collect raw events from the source for the given date range.

        Can be overridden as sync or async in subclasses.
        Returns: list[RawEvent] or coroutine that yields list[RawEvent]
        """
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
