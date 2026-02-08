"""Source-specific event parsing for timeline events."""

from __future__ import annotations

from datetime import datetime

from timeline.config import TimelineConfig
from timeline.models import RawEvent, TimelineEvent
from timeline.transformer.categorizer import (
    BrowserDomainCategorizer,
    GitCommitCategorizer,
    ShellCommandCategorizer,
)
from timeline.transformer.cleaner import DescriptionCleaner
from timeline.transformer.projector import ProjectMapper


class Parser:
    """Parse source-specific raw events into timeline events."""

    def parse_git(
        self,
        raw: RawEvent,
        config: TimelineConfig,
        git_cat: GitCommitCategorizer,
        project_mapper: ProjectMapper,
        cleaner: DescriptionCleaner,
    ) -> TimelineEvent | None:
        """Transform a raw git commit into a timeline event."""
        data = raw.raw_data
        try:
            timestamp = datetime.fromisoformat(data["timestamp"])
        except (KeyError, ValueError):
            return None

        subject = data.get("subject", "")
        files = data.get("files", [])
        repo_name = data.get("repo_name", "unknown")

        category = git_cat.categorize(subject, files)
        description = cleaner.clean(subject)
        project = project_mapper.map_from_repo(repo_name, data.get("repo_path", ""))

        # Build metadata
        total_insertions = sum(f.get("insertions", 0) for f in files)
        total_deletions = sum(f.get("deletions", 0) for f in files)
        file_paths = [f.get("path", "") for f in files]

        metadata = {
            "commit_hash": data.get("hash", ""),
            "author_email": data.get("author_email", ""),
            "author_name": data.get("author_name", ""),
            "repo_name": repo_name,
            "repo_path": data.get("repo_path", ""),
            "branch": data.get("refs", ""),
            "files_changed": file_paths,
            "insertions": total_insertions,
            "deletions": total_deletions,
        }

        return TimelineEvent(
            timestamp=timestamp,
            source="git",
            category=category,
            description=description,
            project=project,
            metadata=metadata,
            raw_event_id=raw.id,
        )

    def parse_shell(
        self,
        raw: RawEvent,
        config: TimelineConfig,
        shell_cat: ShellCommandCategorizer,
        project_mapper: ProjectMapper,
    ) -> TimelineEvent | None:
        """Transform a raw shell command into a timeline event."""
        data = raw.raw_data
        try:
            timestamp = datetime.fromisoformat(data["timestamp"])
        except (KeyError, ValueError):
            return None

        command = data.get("command", "").strip()
        if not command:
            return None

        cwd = data.get("cwd", "")
        category = shell_cat.categorize(command)
        project = project_mapper.map_from_cwd(cwd)

        metadata = {
            "command": command,
            "cwd": cwd,
            "shell": data.get("shell", ""),
            "pid": data.get("pid", ""),
        }

        return TimelineEvent(
            timestamp=timestamp,
            source="shell",
            category=category,
            description=command,
            project=project,
            metadata=metadata,
            raw_event_id=raw.id,
        )

    def parse_browser(
        self,
        raw: RawEvent,
        config: TimelineConfig,
        browser_cat: BrowserDomainCategorizer,
    ) -> TimelineEvent | None:
        """Transform a raw browser visit into a timeline event."""
        data = raw.raw_data
        try:
            timestamp = datetime.fromisoformat(data["timestamp"])
        except (KeyError, ValueError):
            return None

        url = data.get("url", "")
        title = data.get("title", "")
        domain = data.get("domain", "")
        site_name = data.get("site_name", "")

        # Skip configured domains (substring match for consistency with categorization)
        if any(skip in domain for skip in config.browser.skip_domains):
            return None

        category = browser_cat.categorize(domain, url)
        description = title if title else domain
        project = None  # Browser events are cross-cutting; project mapping unreliable

        metadata = {
            "url": url,
            "title": title,
            "domain": domain,
            "site_name": site_name,
            "visit_type": data.get("visit_type", 0),
            "visit_count": data.get("visit_count", 0),
        }

        return TimelineEvent(
            timestamp=timestamp,
            source="browser",
            category=category,
            description=description,
            project=project,
            metadata=metadata,
            raw_event_id=raw.id,
        )

    def parse_windows_events(
        self,
        raw: RawEvent,
        config: TimelineConfig,
    ) -> TimelineEvent | None:
        """Transform a Windows event log entry into a timeline event.

        Handles logon/logoff (7001/7002) events from System log.
        """
        data = raw.raw_data
        try:
            timestamp = datetime.fromisoformat(data["timestamp"])
        except (KeyError, ValueError):
            return None

        event_type = data.get("event_type", "")

        # Map event types to categories
        category_map = {
            "logon": "active",
            "logoff": "afk",
        }

        if event_type not in category_map:
            return None

        category = category_map[event_type]
        description = f"Workstation {event_type}"

        metadata = {
            "event_type": event_type,
            "event_id": data.get("event_id", ""),
        }

        return TimelineEvent(
            timestamp=timestamp,
            source="windows_events",
            category=category,
            description=description,
            project=None,
            metadata=metadata,
            raw_event_id=raw.id,
        )

    def parse_calendar(
        self,
        raw: RawEvent,
        config: TimelineConfig,
    ) -> TimelineEvent | None:
        """Transform a raw calendar event into a timeline event."""
        data = raw.raw_data

        # Support both old Graph API format and new COM format
        try:
            # New COM format: "start" key
            if "start" in data:
                timestamp = datetime.fromisoformat(data["start"])
            # Old Graph format: "start_iso" key
            else:
                timestamp = datetime.fromisoformat(data["start_iso"])
        except (KeyError, ValueError):
            return None

        subject = data.get("subject", "").strip()
        if not subject:
            return None

        # Extract end time if available
        end_time = None
        try:
            # New COM format
            end_str = data.get("end") or data.get("end_iso")
            if end_str:
                end_time = datetime.fromisoformat(end_str)
        except ValueError:
            pass

        # Extract project from mailbox/calendar name
        # For COM: use mailbox name (Crayon, Enova, etc)
        # For Graph: use account email
        mailbox = data.get("mailbox", "")
        account_email = data.get("account_email", "")

        # Extract company name from mailbox (before @)
        if mailbox:
            project = (
                mailbox.split("@")[1].split(".")[0].capitalize() if "@" in mailbox else mailbox
            )
        else:
            project = account_email if account_email else None

        category = data.get("organizer", "").strip() or "calendar"

        metadata = {
            "organizer": data.get("organizer", ""),
            "organizer_name": data.get("organizer_name", ""),
            "organizer_email": data.get("organizer_email", ""),
            "location": data.get("location", ""),
            "is_recurring": data.get("is_recurring", False),
        }

        return TimelineEvent(
            timestamp=timestamp,
            source="calendar",
            category=category,
            description=subject,
            project=project,
            end_time=end_time,
            metadata=metadata,
            raw_event_id=raw.id,
        )
