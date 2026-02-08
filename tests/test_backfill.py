"""Tests for backfill functionality."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest

from timeline.models import DateRange
from timeline.pipeline import Pipeline


class TestDateRangeIterDays:
    def test_single_day(self):
        dr = DateRange.for_date(date(2026, 2, 6))
        days = list(dr.iter_days())
        assert len(days) == 1
        assert days[0].start == date(2026, 2, 6)

    def test_multi_day(self):
        dr = DateRange(start=date(2026, 2, 3), end=date(2026, 2, 7))
        days = list(dr.iter_days())
        assert len(days) == 5
        assert days[0].start == date(2026, 2, 3)
        assert days[4].start == date(2026, 2, 7)

    def test_week(self):
        dr = DateRange(start=date(2026, 2, 2), end=date(2026, 2, 8))
        days = list(dr.iter_days())
        assert len(days) == 7

    def test_last_n_months(self):
        dr = DateRange.last_n_months(1)
        assert dr.days >= 28
        assert dr.end == date.today() - __import__("datetime").timedelta(days=1)


class TestBackfill:
    @pytest.mark.asyncio
    async def test_backfill_collects_each_day(self, config):
        """Backfill should call collector for each day in range."""
        pipeline = Pipeline(config)
        dr = DateRange(start=date(2026, 2, 3), end=date(2026, 2, 5))

        mock_collector = MagicMock()
        mock_collector.source_name.return_value = "git"
        mock_collector.is_cheap.return_value = True
        mock_collector.collect.return_value = []
        pipeline._collectors = [mock_collector]

        await pipeline.backfill(dr)

        # Should be called 3 times (Feb 3, 4, 5)
        assert mock_collector.collect.call_count == 3

    @pytest.mark.asyncio
    async def test_backfill_skips_days_with_existing_data(self, config):
        """Days that already have events should be skipped."""
        pipeline = Pipeline(config)

        # Pre-populate Feb 4 with an event
        from timeline.models import TimelineEvent

        pipeline._store.save_events(
            [
                TimelineEvent(
                    timestamp=datetime(2026, 2, 4, 9, 0, tzinfo=UTC),
                    source="git",
                    category="code",
                    description="existing work",
                )
            ]
        )

        dr = DateRange(start=date(2026, 2, 3), end=date(2026, 2, 5))

        mock_collector = MagicMock()
        mock_collector.source_name.return_value = "git"
        mock_collector.is_cheap.return_value = True
        mock_collector.collect.return_value = []
        pipeline._collectors = [mock_collector]

        await pipeline.backfill(dr, force=False)

        # Feb 4 skipped, so only 2 calls (Feb 3 and Feb 5)
        assert mock_collector.collect.call_count == 2

    @pytest.mark.asyncio
    async def test_backfill_force_recollects(self, config):
        """--force should re-collect even days with existing data."""
        pipeline = Pipeline(config)

        from timeline.models import TimelineEvent

        pipeline._store.save_events(
            [
                TimelineEvent(
                    timestamp=datetime(2026, 2, 4, 9, 0, tzinfo=UTC),
                    source="git",
                    category="code",
                    description="existing work",
                )
            ]
        )

        dr = DateRange(start=date(2026, 2, 3), end=date(2026, 2, 5))

        mock_collector = MagicMock()
        mock_collector.source_name.return_value = "git"
        mock_collector.is_cheap.return_value = True
        mock_collector.collect.return_value = []
        pipeline._collectors = [mock_collector]

        await pipeline.backfill(dr, force=True)

        # All 3 days collected
        assert mock_collector.collect.call_count == 3

    @pytest.mark.asyncio
    async def test_backfill_skips_api_collectors_by_default(self, config):
        """API collectors should be skipped unless --include-api."""
        pipeline = Pipeline(config)
        dr = DateRange.for_date(date(2026, 2, 6))

        cheap_collector = MagicMock()
        cheap_collector.source_name.return_value = "git"
        cheap_collector.is_cheap.return_value = True
        cheap_collector.collect.return_value = []

        expensive_collector = MagicMock()
        expensive_collector.source_name.return_value = "toggl"
        expensive_collector.is_cheap.return_value = False
        expensive_collector.collect.return_value = []

        pipeline._collectors = [cheap_collector, expensive_collector]

        await pipeline.backfill(dr, include_api=False)
        cheap_collector.collect.assert_called_once()
        expensive_collector.collect.assert_not_called()

    @pytest.mark.asyncio
    async def test_backfill_includes_api_when_flagged(self, config):
        """--include-api should run API collectors too."""
        pipeline = Pipeline(config)
        dr = DateRange.for_date(date(2026, 2, 6))

        expensive_collector = MagicMock()
        expensive_collector.source_name.return_value = "toggl"
        expensive_collector.is_cheap.return_value = False
        expensive_collector.collect.return_value = []

        pipeline._collectors = [expensive_collector]

        await pipeline.backfill(dr, include_api=True)
        expensive_collector.collect.assert_called_once()
