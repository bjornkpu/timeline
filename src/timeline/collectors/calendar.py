"""Calendar collector using Outlook COM/MAPI."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any

import click
import win32com.client

from timeline.collectors.base import Collector
from timeline.config.models import CalendarCollectorConfig
from timeline.models import DateRange, RawEvent


class CalendarCollector(Collector):
    """Fetch calendar events from local Outlook via COM/MAPI.

    Reads events directly from Outlook's calendar using Windows COM
    interface. No authentication needed (uses Outlook's cached data).
    Requires Outlook to be running.
    """

    def __init__(self, config: CalendarCollectorConfig) -> None:
        """Initialize calendar collector.

        Args:
            config: Calendar collector configuration (emails not used for COM)
        """
        self._config = config

    def is_cheap(self) -> bool:
        """Local Outlook access is fast."""
        return True

    def source_name(self) -> str:
        """Source identifier for raw events."""
        return "calendar"

    async def collect(self, date_range: DateRange) -> list[RawEvent]:
        """Collect calendar events from Outlook.

        Reads from specified calendars (or default if none specified).

        Args:
            date_range: Date range to query (start and end inclusive)

        Returns:
            List of raw events from calendar(s)
        """
        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
        except Exception as e:
            click.echo(
                click.style(
                    f"⚠️  Calendar: Outlook not running or COM unavailable: {e}",
                    fg="yellow",
                ),
                err=True,
            )
            return []

        try:
            mapi = outlook.GetNamespace("MAPI")
        except Exception as e:
            click.echo(
                click.style(
                    f"⚠️  Calendar: Could not access Outlook: {e}",
                    fg="yellow",
                ),
                err=True,
            )
            return []

        events: list[RawEvent] = []

        # Determine which calendars to collect from
        calendars_to_collect = []

        # Filter mailboxes if specified in config
        try:
            for i in range(1, mapi.Folders.Count + 1):
                mailbox = mapi.Folders(i)
                mailbox_name = mailbox.Name

                # Skip mailbox if not in filter list (when filter is specified)
                if self._config.mailboxes and mailbox_name not in self._config.mailboxes:
                    click.echo(
                        click.style(
                            f"📅 Skipping mailbox: {mailbox_name} (not in configured mailboxes)",
                            fg="cyan",
                        ),
                        err=True,
                    )
                    continue

                # Collect from specified calendar names or default
                if self._config.calendar_names:
                    for folder in mailbox.Folders:
                        if folder.Name in self._config.calendar_names:
                            calendars_to_collect.append(folder)
                else:
                    # Use default calendar
                    for folder in mailbox.Folders:
                        if folder.Name == "Calendar":
                            calendars_to_collect.append(folder)
                            break
        except Exception as e:
            click.echo(
                click.style(
                    f"⚠️  Calendar: Could not access calendars: {e}",
                    fg="yellow",
                ),
                err=True,
            )

        # Collect events from all selected calendars
        for calendar in calendars_to_collect:
            try:
                # Get the mailbox (parent) name for project mapping
                mailbox_name = ""
                try:
                    mailbox_name = calendar.Parent.Name
                except Exception:
                    mailbox_name = "unknown"

                items = calendar.Items

                # MUST sort by Start before setting IncludeRecurrences per Microsoft docs
                items.Sort("[Start]")
                items.IncludeRecurrences = True  # Expand recurring events

                # Date range for filtering (in UTC for comparison with StartUTC)
                start_dt_utc = datetime.combine(date_range.start, time.min, tzinfo=UTC)
                end_dt_utc = datetime.combine(
                    date_range.end + timedelta(days=1), time.min, tzinfo=UTC
                )

                click.echo(
                    click.style(
                        f"📅 Calendar {calendar.Name}: Collecting from {date_range.start} to {date_range.end}",
                        fg="cyan",
                    ),
                    err=True,
                )

                # NOTE: Restrict() doesn't work with IncludeRecurrences (returns empty collection)
                # Must iterate and filter manually, but STOP once we pass the date range
                # Items are sorted by Start, so we can break early
                item_count = 0
                processed = 0
                max_items = 5000  # Reasonable cap for single-day collection
                consecutive_errors = 0
                max_consecutive_errors = 10  # Stop if we hit too many errors in a row
                items_past_range = 0  # Track items beyond our date range
                max_items_past_range = 50  # If we see many items past range, likely hit them all

                for i in range(1, items.Count + 1):
                    if item_count >= max_items:
                        click.echo(
                            click.style(
                                f"⚠️  Calendar {calendar.Name}: Hit safety cap of {max_items} items, "
                                f"may have missed events due to infinite recurring expansion",
                                fg="yellow",
                            ),
                            err=True,
                        )
                        break

                    if consecutive_errors >= max_consecutive_errors:
                        click.echo(
                            click.style(
                                f"⚠️  Calendar {calendar.Name}: Too many consecutive errors, stopping",
                                fg="yellow",
                            ),
                            err=True,
                        )
                        break

                    # If we've seen many items past our date range, we've probably collected everything
                    if items_past_range >= max_items_past_range:
                        break
                    try:
                        item = items(i)
                        item_count += 1
                        consecutive_errors = 0  # Reset error counter on success

                        # Skip items without start time
                        if not hasattr(item, "StartUTC") or not item.StartUTC:
                            continue

                        # Convert COM datetime to Python datetime
                        item_start = item.StartUTC
                        if not isinstance(item_start, datetime):
                            item_start = datetime(
                                item_start.year,
                                item_start.month,
                                item_start.day,
                                item_start.hour,
                                item_start.minute,
                                item_start.second,
                                tzinfo=UTC,
                            )

                        # Early exit: items are sorted, so once we pass end date, we're done
                        if item_start >= end_dt_utc:
                            items_past_range += 1
                            continue

                        # Filter by date range (both in UTC)
                        if item_start < start_dt_utc:
                            continue

                        # Skip items without subject
                        if (
                            not hasattr(item, "Subject")
                            or not item.Subject
                            or not item.Subject.strip()
                        ):
                            continue

                        # Skip items with excluded subjects
                        if (
                            self._config.exclude_subjects
                            and item.Subject in self._config.exclude_subjects
                        ):
                            continue

                        # Skip items marked as free time
                        # if hasattr(item, "BusyStatus") and item.BusyStatus == 0:  # 0 = olFree
                        #     continue

                        raw_event = self._item_to_raw_event(item, mailbox_name)
                        if raw_event:
                            events.append(raw_event)
                            processed += 1

                    except Exception:
                        # Skip problematic items but track consecutive failures
                        consecutive_errors += 1
                        pass

                click.echo(
                    click.style(
                        f"📅 Calendar {calendar.Name} ({mailbox_name}): Scanned {item_count} items, collected {processed} events",
                        fg="cyan",
                    ),
                    err=True,
                )

            except Exception as e:
                click.echo(
                    click.style(
                        f"⚠️  Calendar: Error reading {calendar.Name}: {e}",
                        fg="yellow",
                    ),
                    err=True,
                )

        return events

    @staticmethod
    def _item_to_raw_event(item: Any, calendar_name: str = "Calendar") -> RawEvent | None:
        """Convert Outlook calendar item to RawEvent.

        Args:
            item: Outlook calendar item
            calendar_name: Name of the calendar folder (for project mapping)

        Returns:
            RawEvent or None if conversion fails
        """
        try:
            subject = item.Subject if hasattr(item, "Subject") else "Unknown"
            start = item.StartUTC if hasattr(item, "StartUTC") else None
            location = item.Location if hasattr(item, "Location") else ""
            is_recurring = item.IsRecurring if hasattr(item, "IsRecurring") else False

            # Skip if no subject or start time
            if not start:
                return None

            if not subject or not str(subject).strip():
                return None

            # Convert COM datetime to Python datetime
            # COM datetimes from Outlook are in UTC
            if isinstance(start, str):
                start_dt = datetime.fromisoformat(start)
            else:
                start_dt = datetime(
                    start.year,
                    start.month,
                    start.day,
                    start.hour,
                    start.minute,
                    start.second,
                    tzinfo=UTC,
                )

            # Get end time if available
            # COM datetimes from Outlook are in UTC
            end = item.EndUTC if hasattr(item, "EndUTC") else start
            if end and not isinstance(end, str):
                end_dt = datetime(
                    end.year,
                    end.month,
                    end.day,
                    end.hour,
                    end.minute,
                    end.second,
                    tzinfo=UTC,
                )
            else:
                end_dt = start_dt + timedelta(hours=1)  # Default 1 hour

            # Get organizer/owner if available
            organizer = ""
            if hasattr(item, "Organizer"):
                organizer = str(item.Organizer)

            raw_data = {
                "subject": subject,
                "location": location,
                "organizer": organizer,
                "is_recurring": is_recurring,
                "mailbox": calendar_name,  # Add mailbox/calendar name for project mapping
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            }

            if hasattr(item, "Body"):
                raw_data["body"] = item.Body[:500] if item.Body else ""

            return RawEvent(
                source="calendar",
                collected_at=datetime.now(UTC),
                raw_data=raw_data,
                event_timestamp=start_dt,
            )

        except Exception:
            return None
