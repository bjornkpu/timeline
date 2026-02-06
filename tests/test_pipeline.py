"""Tests for the pipeline orchestrator."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from timeline.models import DateRange, RawEvent
from timeline.pipeline import Pipeline


class TestPipelineCaching:
    """Test that expensive collectors use caching correctly."""

    def test_cheap_collector_always_runs(self, config):
        """Git (cheap) should always collect, even if data exists."""
        pipeline = Pipeline(config)
        dr = DateRange.for_date(date(2026, 2, 6))

        # Pre-populate raw data
        pipeline._store.save_raw(
            [
                RawEvent(
                    source="git",
                    collected_at=datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
                    raw_data={"hash": "existing"},
                    event_timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
                )
            ]
        )

        # Mock the git collector to track if it was called
        mock_collector = MagicMock()
        mock_collector.source_name.return_value = "git"
        mock_collector.is_cheap.return_value = True
        mock_collector.collect.return_value = []
        pipeline._collectors = [mock_collector]

        pipeline.collect(dr)
        mock_collector.collect.assert_called_once()

    def test_expensive_collector_uses_cache(self, config):
        """Expensive collectors should skip if raw data exists."""
        pipeline = Pipeline(config)
        dr = DateRange.for_date(date(2026, 2, 6))

        # Pre-populate raw data for "toggl"
        pipeline._store.save_raw(
            [
                RawEvent(
                    source="toggl",
                    collected_at=datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
                    raw_data={"id": "existing"},
                    event_timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
                )
            ]
        )

        mock_collector = MagicMock()
        mock_collector.source_name.return_value = "toggl"
        mock_collector.is_cheap.return_value = False
        pipeline._collectors = [mock_collector]

        pipeline.collect(dr)
        mock_collector.collect.assert_not_called()

    def test_expensive_collector_refresh_forces_recollect(self, config):
        """--refresh should force expensive collectors to re-collect."""
        pipeline = Pipeline(config)
        dr = DateRange.for_date(date(2026, 2, 6))

        pipeline._store.save_raw(
            [
                RawEvent(
                    source="toggl",
                    collected_at=datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
                    raw_data={"id": "existing"},
                    event_timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
                )
            ]
        )

        mock_collector = MagicMock()
        mock_collector.source_name.return_value = "toggl"
        mock_collector.is_cheap.return_value = False
        mock_collector.collect.return_value = []
        pipeline._collectors = [mock_collector]

        pipeline.collect(dr, refresh=True)
        mock_collector.collect.assert_called_once()


class TestPipelineTransform:
    def test_transform_clears_old_events(self, config, sample_raw_git_events):
        """Transform should delete existing events before re-creating."""
        pipeline = Pipeline(config)
        dr = DateRange.for_date(date(2026, 2, 6))

        pipeline._store.save_raw(sample_raw_git_events)
        pipeline.transform(dr)

        events_first = pipeline._store.get_events(dr)
        assert len(events_first) > 0

        # Re-transform — should not duplicate
        pipeline.transform(dr)
        events_second = pipeline._store.get_events(dr)
        assert len(events_second) == len(events_first)
