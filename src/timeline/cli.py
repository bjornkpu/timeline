"""CLI interface for timeline — click-based commands."""

from __future__ import annotations

import asyncio
from datetime import date

import click

from timeline.config import TimelineConfig, generate_config_toml
from timeline.config.models import TimelineConfig as TimelineConfigModel
from timeline.models import DateRange, SourceFilter
from timeline.pipeline import Pipeline

AVAILABLE_SOURCES = {"browser", "calendar", "git", "shell", "windows_events"}


def parse_date_arg(value: str) -> DateRange:
    """Parse a date argument into a DateRange.

    Supports: 'today', 'yesterday', 'YYYY-MM-DD'
    """
    value = value.strip().lower()
    if value == "today":
        return DateRange.today()
    if value == "yesterday":
        return DateRange.yesterday()
    try:
        d = date.fromisoformat(value)
        return DateRange.for_date(d)
    except ValueError:
        msg = f"Invalid date: '{value}'. Use 'today', 'yesterday', or YYYY-MM-DD."
        raise click.BadParameter(msg) from None


def parse_week_arg(value: str) -> DateRange:
    """Parse week argument into DateRange.

    Supports: 'this-week', '2026-W08', 'W08', '8'
    """
    value = value.strip().lower()

    if value == "this-week":
        return DateRange.this_week()

    try:
        return DateRange.parse_week(value)
    except ValueError as e:
        msg = f"Invalid week: '{value}'. Use 'this-week', '8', 'W08', or '2026-W08'."
        raise click.BadParameter(msg) from e


def parse_source_arg(value: str) -> set[str]:
    """Parse comma-separated source names and validate against AVAILABLE_SOURCES."""
    sources = {s.strip().lower() for s in value.split(",")}
    invalid = sources - AVAILABLE_SOURCES
    if invalid:
        msg = (
            f"Invalid source(s): {', '.join(sorted(invalid))}. "
            f"Available sources: {', '.join(sorted(AVAILABLE_SOURCES))}"
        )
        raise click.BadParameter(msg)
    return sources


def _build_source_filter(include: str | None, exclude: str | None) -> SourceFilter | None:
    """Build SourceFilter from include/exclude flags. Validates mutual exclusivity."""
    if include and exclude:
        msg = "Cannot use both --include and --exclude"
        raise click.UsageError(msg)
    if include:
        sources = parse_source_arg(include)
        return SourceFilter(mode="include", sources=sources)
    if exclude:
        sources = parse_source_arg(exclude)
        return SourceFilter(mode="exclude", sources=sources)
    return None


@click.group()
@click.version_option(package_name="timeline")
def cli() -> None:
    """Timeline — local-first daily activity timeline for developers.

    Aggregates your git commits, browser history, calendar, and more
    into a chronological timeline of your workday.

    Run 'timeline init' to set up your configuration.
    """


@cli.command()
def init() -> None:
    """Create default configuration at ~/.timeline/config.toml."""
    from pathlib import Path

    config_path = Path.home() / ".timeline" / "config.toml"
    if config_path.exists() and not click.confirm(
        f"Config already exists at {config_path}. Overwrite?"
    ):
        return

    config = TimelineConfigModel()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(generate_config_toml(config))

    click.echo(f"✓ Config created at: {config_path}")
    click.echo("Edit to customize collectors, project mapping, etc.")


@cli.command()
def reset() -> None:
    """Delete the timeline database and start fresh."""
    config = _load_config()
    db_path = config.db_path
    if not db_path.exists():
        click.echo(f"No database at {db_path}")
        return
    if click.confirm(f"Delete {db_path}? This removes all collected data."):
        db_path.unlink()
        click.echo("Database deleted. Run 'timeline run' to start fresh.")


@cli.command()
@click.argument("date_str", default="today")
@click.option("--quick", is_flag=True, help="Skip LLM summarization")
@click.option("--refresh", is_flag=True, help="Force re-collect from API sources")
@click.option(
    "--include",
    type=str,
    default=None,
    help="Show only these sources (csv). Browser, calendar, git, shell, windows_events",
)
@click.option(
    "--exclude",
    type=str,
    default=None,
    help="Hide these sources (csv). Browser, calendar, git, shell, windows_events",
)
def run(
    date_str: str, quick: bool, refresh: bool, include: str | None, exclude: str | None
) -> None:
    """Full pipeline: collect, transform, summarize, and show.

    DATE can be 'today', 'yesterday', or YYYY-MM-DD.
    """
    config = _load_config()

    date_range = parse_date_arg(date_str)
    source_filter = _build_source_filter(include, exclude)
    pipeline = Pipeline(config)
    try:
        asyncio.run(
            pipeline.run(date_range, quick=quick, refresh=refresh, source_filter=source_filter)
        )
    finally:
        pipeline.close()


@cli.command()
@click.argument("date_str", default="today")
@click.option("--refresh", is_flag=True, help="Force re-collect from API sources")
def collect(date_str: str, refresh: bool) -> None:
    """Collect raw events from all enabled sources.

    DATE can be 'today', 'yesterday', or YYYY-MM-DD.
    """
    config = _load_config()

    date_range = parse_date_arg(date_str)
    pipeline = Pipeline(config)
    try:
        asyncio.run(pipeline.collect(date_range, refresh=refresh))
    finally:
        pipeline.close()


@cli.command()
@click.argument("date_str", default="today")
def transform(date_str: str) -> None:
    """Transform raw events into normalized timeline events.

    DATE can be 'today', 'yesterday', or YYYY-MM-DD.
    """
    date_range = parse_date_arg(date_str)
    config = _load_config()
    pipeline = Pipeline(config)
    try:
        pipeline.transform(date_range)
    finally:
        pipeline.close()


@cli.command()
@click.argument("date_str", default="today")
def summarize(date_str: str) -> None:
    """Generate LLM summary from timeline events.

    DATE can be 'today', 'yesterday', or YYYY-MM-DD.
    """
    date_range = parse_date_arg(date_str)
    config = _load_config()
    pipeline = Pipeline(config)
    try:
        pipeline.summarize(date_range)
    finally:
        pipeline.close()


@cli.command()
@click.argument("week_str", default="this-week")
@click.option("--refresh", is_flag=True, help="Force regenerate from daily summaries")
def summarize_week(week_str: str, refresh: bool) -> None:
    """Generate weekly summary from daily summaries.

    WEEK can be 'this-week', '8' (week number), 'W08', or '2026-W08'.

    Aggregates all daily summaries for that week into a single weekly summary.
    Requires daily summaries to exist — run 'timeline run' for each day first.

    Examples:

        timeline summarize-week                # Current week

        timeline summarize-week 8              # Week 8 of current year

        timeline summarize-week 2026-W08       # Specific week
    """
    date_range = parse_week_arg(week_str)
    config = _load_config()
    pipeline = Pipeline(config)
    try:
        pipeline.summarize_week(date_range, refresh=refresh)
    finally:
        pipeline.close()


@cli.command()
@click.argument("date_str", default="today")
@click.option(
    "--group-by",
    type=click.Choice(["flat", "hour", "period"]),
    default=None,
    help="How to group events in the display",
)
@click.option(
    "--include",
    type=str,
    default=None,
    help="Show only these sources (csv). Browser, calendar, git, shell, windows_events",
)
@click.option(
    "--exclude",
    type=str,
    default=None,
    help="Hide these sources (csv). Browser, calendar, git, shell, windows_events",
)
def show(
    date_str: str,
    group_by: str | None,
    include: str | None,
    exclude: str | None,
) -> None:
    """Display timeline from stored data.

    DATE can be 'today', 'yesterday', or YYYY-MM-DD.
    """
    date_range = parse_date_arg(date_str)
    source_filter = _build_source_filter(include, exclude)
    config = _load_config()
    pipeline = Pipeline(config)
    try:
        pipeline.show(date_range, group_by=group_by, source_filter=source_filter)
    finally:
        pipeline.close()


@cli.command()
@click.argument("start_date")
@click.argument("end_date", required=False)
@click.option("--months", type=int, default=None, help="Backfill last N months instead of dates")
@click.option("--force", is_flag=True, help="Re-collect days that already have data")
@click.option("--include-api", is_flag=True, help="Include API-based collectors (rate limited)")
def backfill(
    start_date: str | None,
    end_date: str | None,
    months: int | None,
    force: bool,
    include_api: bool,
) -> None:
    """Load historical data for a date range.

    Examples:

        timeline backfill 2026-01-01              # Jan 1 to yesterday

        timeline backfill 2026-01-01 2026-01-31   # specific range

        timeline backfill --months 3 _            # last 3 months
    """

    if months is not None:
        date_range = DateRange.last_n_months(months)
    elif start_date:
        try:
            start = date.fromisoformat(start_date)
        except ValueError:
            raise click.BadParameter(f"Invalid start date: {start_date}") from None

        if end_date:
            try:
                end = date.fromisoformat(end_date)
            except ValueError:
                raise click.BadParameter(f"Invalid end date: {end_date}") from None
        else:
            end = date.today()

        date_range = DateRange(start=start, end=end)
    else:
        msg = "Provide start date or --months"
        raise click.UsageError(msg)

    config = _load_config()
    pipeline = Pipeline(config)
    try:
        asyncio.run(pipeline.backfill(date_range, force=force, include_api=include_api))
    finally:
        pipeline.close()


@cli.command()
def list_calendars() -> None:
    """List available Outlook calendars.

    Helps you find calendar names to use in config.toml.
    Shows calendars from all configured email accounts.
    """
    try:
        import win32com.client
    except ImportError as e:
        raise click.ClickException("pywin32 not installed. Run: uv pip install pywin32") from e

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mapi = outlook.GetNamespace("MAPI")

        click.echo("Available Outlook Mailboxes & Calendars:\n")

        found_calendars = False

        # Iterate through all mailboxes
        for i in range(1, mapi.Folders.Count + 1):
            mailbox = mapi.Folders(i)
            click.echo(f"[MAILBOX] {mailbox.Name}")

            calendar_folder = None
            for folder in mailbox.Folders:
                if folder.Name == "Calendar":
                    calendar_folder = folder
                    break

            if not calendar_folder:
                click.echo("  (No calendar folder found)")
                continue

            found_calendars = True
            click.echo(f"  [MAIN] {calendar_folder.Name} ({calendar_folder.Items.Count} items)")

            if calendar_folder.Folders.Count > 0:
                for subfolder in calendar_folder.Folders:
                    click.echo(f"    [SUB] {subfolder.Name} ({subfolder.Items.Count} items)")

            click.echo()

        if not found_calendars:
            raise click.ClickException("No calendars found. Add email accounts to Outlook first.")

        click.echo("=" * 50)
        click.echo("Configuration for ~/.timeline/config.toml:")
        click.echo("\n[collectors.calendar]")
        click.echo("enabled = true")
        click.echo('calendar_names = ["Calendar"]')
        click.echo("\nNote: Currently only reads from first mailbox.")
        click.echo("To include Enova calendar, add the Enova account to Outlook.")

    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Error reading calendars: {e}") from None


def _load_config() -> TimelineConfig:
    """Load config, with helpful error message if missing."""
    from pathlib import Path

    from timeline.config import load_config

    try:
        config_path = Path.home() / ".timeline" / "config.toml"
        return load_config(config_path)
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from None
