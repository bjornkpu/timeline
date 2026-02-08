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
        if self._config.calendar_names:
            # Collect from specified calendars in ALL mailboxes
            try:
                for i in range(1, mapi.Folders.Count + 1):
                    mailbox = mapi.Folders(i)
                    for folder in mailbox.Folders:
                        if folder.Name in self._config.calendar_names:
                            calendars_to_collect.append(folder)
            except Exception as e:
                click.echo(
                    click.style(
                        f"⚠️  Calendar: Could not find specified calendars: {e}",
                        fg="yellow",
                    ),
                    err=True,
                )
        else:
            # Use default calendar from each mailbox
            try:
                for i in range(1, mapi.Folders.Count + 1):
                    mailbox = mapi.Folders(i)
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
                items.IncludeRecurrences = True  # Expand recurring events

                # Manual filtering instead of Restrict() for reliability
                # Use UTC timezone for comparison
                start_dt = datetime.combine(date_range.start, time.min, tzinfo=UTC)
                end_dt = datetime.combine(date_range.end + timedelta(days=1), time.min, tzinfo=UTC)

                for i in range(1, items.Count + 1):
                    try:
                        item = items(i)

                        # Skip items without start time
                        if not hasattr(item, "Start") or not item.Start:
                            continue

                        # Convert COM datetime to Python datetime if needed
                        item_start = item.Start
                        if not isinstance(item_start, datetime):
                            item_start = datetime(
                                item_start.year,
                                item_start.month,
                                item_start.day,
                                item_start.hour,
                                item_start.minute,
                                item_start.second,
                            )

                        # Filter by date range
                        if not (start_dt <= item_start < end_dt):
                            continue

                        # Skip items without subject
                        if (
                            not hasattr(item, "Subject")
                            or not item.Subject
                            or not item.Subject.strip()
                        ):
                            continue

                        # Skip items marked as free time
                        if hasattr(item, "BusyStatus") and item.BusyStatus == 0:  # 0 = olFree
                            continue

                        raw_event = self._item_to_raw_event(item, mailbox_name)
                        if raw_event:
                            events.append(raw_event)

                    except Exception:
                        # Skip problematic items
                        pass

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
            start = item.Start if hasattr(item, "Start") else None
            location = item.Location if hasattr(item, "Location") else ""

            # Skip if no subject or start time
            if not start:
                return None

            if not subject or not str(subject).strip():
                return None

            # Convert COM datetime to Python datetime
            if isinstance(start, str):
                start_dt = datetime.fromisoformat(start)
            else:
                # COM date object
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
            end = item.End if hasattr(item, "End") else start
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
