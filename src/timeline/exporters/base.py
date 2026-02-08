"""Abstract base class for exporters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from timeline.config import TimelineConfig
from timeline.models import DateRange, SourceFilter, Summary, TimelineEvent


class Exporter(ABC):
    """Base class for all output exporters."""

    @abstractmethod
    def export(
        self,
        events: list[TimelineEvent],
        summary: Summary | None,
        date_range: DateRange,
        config: TimelineConfig,
        source_filter: SourceFilter | None = None,
    ) -> None:
        """Export events and optional summary."""
        ...
