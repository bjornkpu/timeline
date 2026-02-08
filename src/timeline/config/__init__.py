"""Configuration management for Timeline."""

from __future__ import annotations

from timeline.config.loader import load_config
from timeline.config.models import (
    BrowserCollectorConfig,
    CalendarCollectorConfig,
    GitAuthor,
    GitCollectorConfig,
    ShellCollectorConfig,
    StdoutExporterConfig,
    SummarizerConfig,
    TimelineConfig,
    WindowsEventLogCollectorConfig,
)
from timeline.config.serializer import generate_config_toml

__all__ = [
    "TimelineConfig",
    "GitAuthor",
    "GitCollectorConfig",
    "BrowserCollectorConfig",
    "ShellCollectorConfig",
    "WindowsEventLogCollectorConfig",
    "CalendarCollectorConfig",
    "StdoutExporterConfig",
    "SummarizerConfig",
    "load_config",
    "generate_config_toml",
]
