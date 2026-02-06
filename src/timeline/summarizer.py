"""LLM summarizer — generates summaries from timeline events.

Uses Claude Code in non-interactive mode.
Deferred implementation — stub for now.
"""

from __future__ import annotations

from timeline.config import TimelineConfig
from timeline.models import DateRange, PeriodType, Summary, TimelineEvent


class Summarizer:
    def __init__(self, config: TimelineConfig) -> None:
        self._config = config

    def summarize(
        self,
        events: list[TimelineEvent],
        date_range: DateRange,
        period_type: PeriodType = PeriodType.DAY,
    ) -> Summary | None:
        """Generate a summary for the given events.

        TODO: Implement LLM integration via Claude Code non-interactive mode.
        For now, returns None.
        """
        if not self._config.summarizer.enabled:
            return None

        # Placeholder — will pipe events through Claude Code
        return None
