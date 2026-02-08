"""Terminal/stdout exporter — display timeline in the terminal."""

from __future__ import annotations

import click

from timeline.config import TimelineConfig
from timeline.exporters.base import Exporter
from timeline.models import DateRange, SourceFilter, Summary, TimelineEvent

# Default color scheme — source name colors
SOURCE_COLORS: dict[str, str] = {
    "git": "cyan",
    "browser": "magenta",
    "activitywatch": "blue",
    "toggl": "yellow",
    "shell": "white",
    "calendar": "bright_magenta",
    "obsidian": "bright_blue",
}

# Category badge colors
CATEGORY_COLORS: dict[str, str] = {
    "feature": "green",
    "bugfix": "red",
    "refactor": "yellow",
    "test": "cyan",
    "docs": "blue",
    "chore": "white",
    "ci": "magenta",
    "config": "white",
    "code": "bright_white",
    "build": "yellow",
    "performance": "bright_green",
    "style": "bright_blue",
    "revert": "bright_red",
}


class StdoutExporter(Exporter):
    def export(
        self,
        events: list[TimelineEvent],
        summary: Summary | None,
        date_range: DateRange,
        config: TimelineConfig,
        source_filter: SourceFilter | None = None,
    ) -> None:
        group_by = config.stdout.group_by
        if group_by == "hour":
            self._export_by_hour(events, summary, date_range, config, source_filter)
        elif group_by == "period":
            self._export_by_period(events, summary, date_range, config, source_filter)
        else:
            self._export_flat(events, summary, date_range, config, source_filter)

    def _export_flat(
        self,
        events: list[TimelineEvent],
        summary: Summary | None,
        date_range: DateRange,
        config: TimelineConfig,
        source_filter: SourceFilter | None = None,
    ) -> None:
        """Flat chronological timeline."""
        self._print_header(date_range, events, config, source_filter)

        if not events:
            click.echo(click.style("  (no events)", dim=True))
        else:
            for event in events:
                self._print_event(event, config)

        self._print_summary(summary)

    def _export_by_hour(
        self,
        events: list[TimelineEvent],
        summary: Summary | None,
        date_range: DateRange,
        config: TimelineConfig,
        source_filter: SourceFilter | None = None,
    ) -> None:
        """Events grouped by hour blocks."""
        self._print_header(date_range, events, config, source_filter)

        if not events:
            click.echo(click.style("  (no events)", dim=True))
            self._print_summary(summary)
            return

        # Group by hour
        hours: dict[int, list[TimelineEvent]] = {}
        for event in events:
            local_time = event.timestamp.astimezone(config.timezone)
            hour = local_time.hour
            hours.setdefault(hour, []).append(event)

        if events:
            first_local = events[0].timestamp.astimezone(config.timezone)
            last_local = events[-1].timestamp.astimezone(config.timezone)
            start_hour = first_local.hour
            end_hour = last_local.hour
        else:
            start_hour, end_hour = 8, 17

        for h in range(start_hour, end_hour + 1):
            click.echo(click.style(f"  {h:02d}:00 ", bold=True) + click.style("─" * 40, dim=True))
            if h in hours:
                for event in hours[h]:
                    self._print_event(event, config)
            else:
                click.echo(click.style("    (no activity)", dim=True))
            click.echo()

        self._print_summary(summary)

    def _export_by_period(
        self,
        events: list[TimelineEvent],
        summary: Summary | None,
        date_range: DateRange,
        config: TimelineConfig,
        source_filter: SourceFilter | None = None,
    ) -> None:
        """Events split into morning/afternoon by lunch boundary."""
        self._print_header(date_range, events, config, source_filter)

        if not events:
            click.echo(click.style("  (no events)", dim=True))
            self._print_summary(summary)
            return

        lunch_hour = int(config.lunch_boundary.split(":")[0])
        lunch_minute = (
            int(config.lunch_boundary.split(":")[1]) if ":" in config.lunch_boundary else 0
        )

        morning: list[TimelineEvent] = []
        afternoon: list[TimelineEvent] = []

        for event in events:
            local_time = event.timestamp.astimezone(config.timezone)
            if local_time.hour < lunch_hour or (
                local_time.hour == lunch_hour and local_time.minute < lunch_minute
            ):
                morning.append(event)
            else:
                afternoon.append(event)

        click.echo(click.style(f"  Morning (before {config.lunch_boundary})", bold=True))
        click.echo(click.style(f"  {'─' * 40}", dim=True))
        if morning:
            for event in morning:
                self._print_event(event, config)
        else:
            click.echo(click.style("    (no activity)", dim=True))
        click.echo()

        click.echo(click.style(f"  Afternoon (after {config.lunch_boundary})", bold=True))
        click.echo(click.style(f"  {'─' * 40}", dim=True))
        if afternoon:
            for event in afternoon:
                self._print_event(event, config)
        else:
            click.echo(click.style("    (no activity)", dim=True))

        self._print_summary(summary)

    def _print_header(
        self,
        date_range: DateRange,
        events: list[TimelineEvent],
        config: TimelineConfig,
        source_filter: SourceFilter | None = None,
    ) -> None:
        """Print date header with workday info."""
        if date_range.days == 1:
            day = date_range.start
            day_name = day.strftime("%A")
            header = f"{day.isoformat()} — {day_name}"
        else:
            header = f"{date_range.start.isoformat()} to {date_range.end.isoformat()}"

        click.echo()
        click.echo(click.style(f"  {header}", bold=True))
        click.echo(click.style(f"  {'═' * len(header)}", dim=True))

        # Show filter info if applied
        if source_filter:
            sources_str = ", ".join(sorted(source_filter.sources))
            if source_filter.mode == "include":
                click.echo(click.style(f"  Showing: {sources_str} only", dim=True))
            else:  # exclude
                click.echo(click.style(f"  Excluding: {sources_str}", dim=True))

        # Infer workday boundaries from events
        if events:
            first_local = events[0].timestamp.astimezone(config.timezone)
            last_local = events[-1].timestamp.astimezone(config.timezone)
            click.echo(
                click.style("  First activity: ", dim=True)
                + click.style(first_local.strftime("%H:%M"), bold=True)
                + click.style("  Last activity: ", dim=True)
                + click.style(last_local.strftime("%H:%M"), bold=True)
            )

        # Collect unique projects
        projects = {e.project for e in events if e.project}
        if projects:
            click.echo(
                click.style("  Projects: ", dim=True)
                + click.style(", ".join(sorted(projects)), fg="bright_white")
            )

        click.echo()

    def _print_event(self, event: TimelineEvent, config: TimelineConfig) -> None:
        """Print a single event line with colors."""
        local_time = event.timestamp.astimezone(config.timezone)
        time_str = local_time.strftime("%H:%M")

        project = event.project or "unknown"
        desc = event.description

        # Source with color
        source_color = SOURCE_COLORS.get(event.source, "white")
        source_styled = click.style(f"[{event.source}]", fg=source_color)

        # Stats with green/red
        stats = ""
        if event.source == "git":
            ins = event.metadata.get("insertions", 0)
            dels = event.metadata.get("deletions", 0)
            if ins or dels:
                ins_styled = click.style(f"+{ins}", fg="green")
                dels_styled = click.style(f"-{dels}", fg="red")
                stats = f" ({ins_styled}/{dels_styled})"

        # Category badge with color
        category_badge = ""
        if event.category != "commit":
            cat_color = CATEGORY_COLORS.get(event.category, "white")
            category_badge = " " + click.style(f"[{event.category}]", fg=cat_color)

        time_styled = click.style(time_str, dim=True)
        project_styled = click.style(project, fg="bright_white", bold=True)

        click.echo(
            f"    {time_styled}  {source_styled} {project_styled} — {desc}{stats}{category_badge}"
        )

    def _print_summary(self, summary: Summary | None) -> None:
        """Print summary section if available."""
        if summary:
            click.echo()
            click.echo(click.style(f"  {'─' * 40}", dim=True))
            click.echo(click.style("  Summary", bold=True))
            click.echo(click.style(f"  {'─' * 40}", dim=True))
            click.echo(f"  {summary.summary}")
        click.echo()
