"""CLI interface for timeline — click-based commands."""

from __future__ import annotations

from datetime import date

import click

from timeline.config import DEFAULT_CONFIG_PATH, TimelineConfig, interactive_init
from timeline.models import DateRange
from timeline.pipeline import Pipeline


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
    """Interactively create configuration at ~/.timeline/config.toml."""
    if DEFAULT_CONFIG_PATH.exists() and not click.confirm(
        f"Config already exists at {DEFAULT_CONFIG_PATH}. Overwrite?"
    ):
        return
    interactive_init()


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
def run(date_str: str, quick: bool, refresh: bool) -> None:
    """Full pipeline: collect, transform, summarize, and show.

    DATE can be 'today', 'yesterday', or YYYY-MM-DD.
    """
    date_range = parse_date_arg(date_str)
    config = _load_config()
    pipeline = Pipeline(config)
    try:
        pipeline.run(date_range, quick=quick, refresh=refresh)
    finally:
        pipeline.close()


@cli.command()
@click.argument("date_str", default="today")
@click.option("--refresh", is_flag=True, help="Force re-collect from API sources")
def collect(date_str: str, refresh: bool) -> None:
    """Collect raw events from all enabled sources.

    DATE can be 'today', 'yesterday', or YYYY-MM-DD.
    """
    date_range = parse_date_arg(date_str)
    config = _load_config()
    pipeline = Pipeline(config)
    try:
        pipeline.collect(date_range, refresh=refresh)
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
@click.argument("date_str", default="today")
@click.option(
    "--group-by",
    type=click.Choice(["flat", "hour", "period"]),
    default=None,
    help="How to group events in the display",
)
def show(date_str: str, group_by: str | None) -> None:
    """Display timeline from stored data.

    DATE can be 'today', 'yesterday', or YYYY-MM-DD.
    """
    date_range = parse_date_arg(date_str)
    config = _load_config()
    pipeline = Pipeline(config)
    try:
        pipeline.show(date_range, group_by=group_by)
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
    from datetime import timedelta

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
        pipeline.backfill(date_range, force=force, include_api=include_api)
    finally:
        pipeline.close()


def _load_config() -> TimelineConfig:
    """Load config, with helpful error message if missing."""
    try:
        return TimelineConfig.load()
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from None
