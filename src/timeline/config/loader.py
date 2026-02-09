"""Load and validate Timeline configuration from TOML files."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from timeline.config.models import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_SHELL_HISTORY_PATH,
    BrowserCollectorConfig,
    CalendarCollectorConfig,
    GitAuthor,
    GitCollectorConfig,
    ShellCollectorConfig,
    StdoutExporterConfig,
    SummarizerConfig,
    TimelineConfig,
    WindowsEventLogCollectorConfig,
    _system_timezone,
)
from timeline.config.validation import ConfigValidator


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> TimelineConfig:
    """Load config from TOML file, validate, and return."""
    if not path.exists():
        msg = f"Config not found at {path}. Run 'timeline init' to create one."
        raise FileNotFoundError(msg)

    with open(path, "rb") as f:
        data = tomllib.load(f)

    config = _from_dict(data)

    # Validate configuration
    validator = ConfigValidator()
    errors = validator.validate(config)
    if errors:
        error_msgs = "\n".join(f"  {e.path}: {e.message}" for e in errors)
        msg = f"Config validation failed:\n{error_msgs}"
        raise ValueError(msg)

    return config


def _from_dict(data: dict[str, Any]) -> TimelineConfig:
    """Convert TOML dict to TimelineConfig dataclass."""
    general = data.get("general", {})
    projects = data.get("projects", {})
    git_data = data.get("collectors", {}).get("git", {})
    shell_data = data.get("collectors", {}).get("shell", {})
    browser_data = data.get("collectors", {}).get("browser", {})
    windows_events_data = data.get("collectors", {}).get("windows_events", {})
    calendar_data = data.get("collectors", {}).get("calendar", {})
    stdout_data = data.get("exporters", {}).get("stdout", {})
    summarizer_data = data.get("summarizer", {})

    tz_str = general.get("timezone", "")
    tz = ZoneInfo(tz_str) if tz_str else _system_timezone()

    db_path_str = general.get("db_path", str(DEFAULT_DB_PATH))
    db_path = Path(db_path_str).expanduser()

    authors = [GitAuthor(email=a["email"], name=a.get("name")) for a in git_data.get("authors", [])]

    return TimelineConfig(
        db_path=db_path,
        timezone=tz,
        work_hours_start=general.get("work_hours", {}).get("start", "08:00"),
        work_hours_end=general.get("work_hours", {}).get("end", "17:00"),
        lunch_boundary=general.get("lunch_boundary", "12:00"),
        project_mapping=projects.get("mapping", {}),
        git=GitCollectorConfig(
            enabled=git_data.get("enabled", True),
            authors=authors,
            repos=git_data.get("repos", []),
        ),
        shell=ShellCollectorConfig(
            enabled=shell_data.get("enabled", False),
            history_path=shell_data.get("history_path", str(DEFAULT_SHELL_HISTORY_PATH)),
        ),
        browser=BrowserCollectorConfig(
            enabled=browser_data.get("enabled", False),
            places_path=browser_data.get("places_path", ""),
            skip_domains=browser_data.get("skip_domains", []),
            domain_mapping=browser_data.get("domain_mapping", {}),
        ),
        windows_events=WindowsEventLogCollectorConfig(
            enabled=windows_events_data.get("enabled", False),
        ),
        calendar=CalendarCollectorConfig(
            enabled=calendar_data.get("enabled", False),
            users=calendar_data.get("users", []),
            mailboxes=calendar_data.get("mailboxes", []),
            calendar_names=calendar_data.get("calendar_names", []),
            exclude_subjects=calendar_data.get("exclude_subjects", []),
        ),
        stdout=StdoutExporterConfig(
            enabled=stdout_data.get("enabled", True),
            group_by=stdout_data.get("group_by", "flat"),
        ),
        summarizer=SummarizerConfig(
            enabled=summarizer_data.get("enabled", False),
            model=summarizer_data.get("model", ""),
        ),
    )
