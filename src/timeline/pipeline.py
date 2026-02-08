"""Pipeline orchestrator — collect → transform → summarize → export."""

from __future__ import annotations

from collections.abc import Sequence

import click

from timeline.collectors.base import Collector
from timeline.collectors.browser import BrowserCollector
from timeline.collectors.git import GitCollector
from timeline.collectors.shell import ShellCollector
from timeline.collectors.windows_events import WindowsEventLogCollector
from timeline.config import TimelineConfig
from timeline.exporters.base import Exporter
from timeline.exporters.stdout import StdoutExporter
from timeline.models import DateRange, PeriodType
from timeline.store import TimelineStore
from timeline.summarizer import Summarizer
from timeline.transformer import Transformer


class Pipeline:
    def __init__(self, config: TimelineConfig) -> None:
        self._config = config
        self._store = TimelineStore(config.db_path)
        self._transformer = Transformer(config)
        self._summarizer = Summarizer(config)
        self._collectors = self._build_collectors()
        self._exporters = self._build_exporters()

    def _build_collectors(self) -> Sequence[Collector]:
        collectors: list[Collector] = []
        if self._config.git.enabled:
            collectors.append(GitCollector(self._config.git))
        if self._config.shell.enabled:
            collectors.append(ShellCollector(self._config.shell))
        if self._config.browser.enabled:
            collectors.append(BrowserCollector(self._config.browser))
        if self._config.windows_events.enabled:
            collectors.append(WindowsEventLogCollector(self._config.windows_events))
        return collectors

    def _build_exporters(self) -> Sequence[Exporter]:
        exporters: list[Exporter] = []
        if self._config.stdout.enabled:
            exporters.append(StdoutExporter())
        return exporters

    def run(
        self,
        date_range: DateRange,
        quick: bool = False,
        refresh: bool = False,
    ) -> None:
        """Full pipeline: collect → transform → summarize → export."""
        self.collect(date_range, refresh=refresh)
        self.transform(date_range)
        if not quick:
            self.summarize(date_range, refresh=refresh)
        self.show(date_range)

    def collect(self, date_range: DateRange, refresh: bool = False) -> None:
        """Run all enabled collectors and store raw events."""
        for collector in self._collectors:
            source = collector.source_name()

            # Skip expensive collectors if we already have data (unless --refresh)
            if not collector.is_cheap() and not refresh and self._store.has_raw(date_range, source):
                click.echo(f"  [{source}] Using cached data (use --refresh to re-collect)")
                continue

            # Force refresh: delete existing raw data first
            if refresh and not collector.is_cheap():
                deleted = self._store.delete_raw(date_range, source)
                if deleted:
                    click.echo(f"  [{source}] Cleared {deleted} cached events")

            click.echo(f"  [{source}] Collecting...")
            raw_events = collector.collect(date_range)
            count = self._store.save_raw(raw_events)
            click.echo(f"  [{source}] {len(raw_events)} found, {count} new")

    def transform(self, date_range: DateRange) -> None:
        """Transform raw events into timeline events."""
        # Delete existing events for re-transformation
        self._store.delete_events(date_range)

        raw_events = self._store.get_raw(date_range)
        events = self._transformer.transform(raw_events)
        count = self._store.save_events(events)
        click.echo(f"  Transformed {count} events")

    def summarize(self, date_range: DateRange, refresh: bool = False) -> None:
        """Generate LLM summary from events, skip if already cached."""
        if not self._config.summarizer.enabled:
            return

        if not refresh:
            existing = self._store.get_summary(date_range, PeriodType.DAY)
            if existing:
                click.echo("  Summary cached (use --refresh to regenerate)")
                return

        events = self._store.get_events(date_range)
        summary = self._summarizer.summarize(events, date_range, PeriodType.DAY)
        if summary:
            self._store.save_summary(summary)
            click.echo("  Summary generated")

    def show(self, date_range: DateRange, group_by: str | None = None) -> None:
        """Display timeline from stored data."""
        events = self._store.get_events(date_range)
        summary = self._store.get_summary(date_range, PeriodType.DAY)

        # Allow overriding group_by for display
        original_group_by = self._config.stdout.group_by
        if group_by:
            self._config.stdout.group_by = group_by

        for exporter in self._exporters:
            exporter.export(events, summary, date_range, self._config)

        if group_by:
            self._config.stdout.group_by = original_group_by

    def backfill(
        self,
        date_range: DateRange,
        force: bool = False,
        include_api: bool = False,
    ) -> None:
        """Backfill historical data for a date range.

        Iterates day-by-day, collecting and transforming.
        Skips days that already have data unless --force.
        Skips API collectors unless --include-api.
        """
        total_days = date_range.days
        total_events = 0

        click.echo(
            f"Backfilling {total_days} days: "
            f"{date_range.start.isoformat()} → {date_range.end.isoformat()}"
        )
        click.echo()

        for i, day_range in enumerate(date_range.iter_days(), 1):
            day_str = day_range.start.isoformat()
            day_name = day_range.start.strftime("%a")
            prefix = f"  [{i}/{total_days}] {day_str} ({day_name})"

            # Skip if already has events and not forcing
            existing = self._store.get_events(day_range)
            if not force and existing:
                click.echo(f"{prefix} — {len(existing)} events (cached, skipping)")
                total_events += len(existing)
                continue

            # Collect — filter collectors based on include_api
            day_events = 0
            for collector in self._collectors:
                if not include_api and not collector.is_cheap():
                    continue

                raw = collector.collect(day_range)
                self._store.save_raw(raw)
                day_events += len(raw)

            # Transform
            self._store.delete_events(day_range)
            raw_events = self._store.get_raw(day_range)
            events = self._transformer.transform(raw_events)
            self._store.save_events(events)

            if events:
                click.echo(f"{prefix} — {len(events)} events")
            else:
                click.echo(click.style(f"{prefix} — no events", dim=True))

            total_events += len(events)

        click.echo()
        click.echo(f"  Backfill complete: {total_events} total events across {total_days} days")

    def close(self) -> None:
        self._store.close()
