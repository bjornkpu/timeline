"""Configuration dataclasses for Timeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, tzinfo
from pathlib import Path


def _get_user_home() -> Path:
    """Get the actual user's home directory, even when running as admin.

    When running in an admin terminal, USERPROFILE points to admin user's home.
    This function detects the original user from environment and returns their home.
    """
    # Try to get original user from USERNAME env var (preserved in admin terminals)
    username = os.environ.get("USERNAME")
    if username:
        user_home = Path("C:") / "Users" / username
        if user_home.exists():
            return user_home

    # Fallback to standard home
    return Path.home()


DEFAULT_CONFIG_DIR = _get_user_home() / ".timeline"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"
DEFAULT_DB_PATH = DEFAULT_CONFIG_DIR / "timeline.db"
DEFAULT_SHELL_HISTORY_PATH = DEFAULT_CONFIG_DIR / "shell_history.jsonl"


@dataclass
class GitAuthor:
    """Git author configuration."""

    email: str
    name: str | None = None


@dataclass
class GitCollectorConfig:
    """Git collector configuration."""

    enabled: bool = True
    authors: list[GitAuthor] = field(default_factory=list)
    repos: list[str] = field(default_factory=list)


@dataclass
class BrowserCollectorConfig:
    """Browser collector configuration."""

    enabled: bool = False
    places_path: str = ""
    skip_domains: list[str] = field(default_factory=list)
    domain_mapping: dict[str, str] = field(default_factory=dict)


@dataclass
class ShellCollectorConfig:
    """Shell collector configuration."""

    enabled: bool = False
    history_path: str = str(DEFAULT_SHELL_HISTORY_PATH)


@dataclass
class WindowsEventLogCollectorConfig:
    """Windows Event Log collector configuration."""

    enabled: bool = False


@dataclass
class StdoutExporterConfig:
    """Stdout exporter configuration."""

    enabled: bool = True
    group_by: str = "flat"


@dataclass
class SummarizerConfig:
    """Summarizer configuration."""

    enabled: bool = False
    model: str = ""


def _system_timezone() -> tzinfo:
    """Detect system timezone."""
    from datetime import datetime

    local_tz = datetime.now(UTC).astimezone().tzinfo
    return local_tz if local_tz is not None else UTC


@dataclass
class TimelineConfig:
    """Main Timeline configuration."""

    db_path: Path = field(default_factory=lambda: DEFAULT_DB_PATH)
    timezone: tzinfo = field(default_factory=_system_timezone)
    work_hours_start: str = "08:00"
    work_hours_end: str = "17:00"
    lunch_boundary: str = "12:00"
    project_mapping: dict[str, str] = field(default_factory=dict)
    git: GitCollectorConfig = field(default_factory=GitCollectorConfig)
    shell: ShellCollectorConfig = field(default_factory=ShellCollectorConfig)
    browser: BrowserCollectorConfig = field(default_factory=BrowserCollectorConfig)
    windows_events: WindowsEventLogCollectorConfig = field(
        default_factory=WindowsEventLogCollectorConfig
    )
    stdout: StdoutExporterConfig = field(default_factory=StdoutExporterConfig)
    summarizer: SummarizerConfig = field(default_factory=SummarizerConfig)
