"""Main transformer orchestrator - dispatches to source-specific parsers."""

from __future__ import annotations

from timeline.config import TimelineConfig
from timeline.models import RawEvent, TimelineEvent
from timeline.transformer.categorizer import (
    BrowserDomainCategorizer,
    GitCommitCategorizer,
    ShellCommandCategorizer,
)
from timeline.transformer.cleaner import DescriptionCleaner
from timeline.transformer.parser import Parser
from timeline.transformer.projector import ProjectMapper


class Transformer:
    """Orchestrate transformation of raw events to timeline events."""

    def __init__(
        self,
        config: TimelineConfig,
        git_categorizer: GitCommitCategorizer | None = None,
        shell_categorizer: ShellCommandCategorizer | None = None,
        browser_categorizer: BrowserDomainCategorizer | None = None,
        project_mapper: ProjectMapper | None = None,
        description_cleaner: DescriptionCleaner | None = None,
    ) -> None:
        """Initialize transformer with config and optional dependency overrides."""
        self._config = config
        self._parser = Parser()
        self._git_cat = git_categorizer or GitCommitCategorizer()
        self._shell_cat = shell_categorizer or ShellCommandCategorizer()
        self._browser_cat = browser_categorizer or BrowserDomainCategorizer()
        self._project_mapper = project_mapper or ProjectMapper(config)
        self._cleaner = description_cleaner or DescriptionCleaner()

    def transform(self, raw_events: list[RawEvent]) -> list[TimelineEvent]:
        """Transform raw events into normalized timeline events."""
        events: list[TimelineEvent] = []
        for raw in raw_events:
            transformed = self._transform_event(raw)
            if transformed:
                events.append(transformed)
        return events

    def _transform_event(self, raw: RawEvent) -> TimelineEvent | None:
        """Dispatch to source-specific transformer."""
        if raw.source == "git":
            return self._parser.parse_git(
                raw,
                self._config,
                self._git_cat,
                self._project_mapper,
                self._cleaner,
            )
        if raw.source == "shell":
            return self._parser.parse_shell(
                raw,
                self._config,
                self._shell_cat,
                self._project_mapper,
            )
        if raw.source == "browser":
            return self._parser.parse_browser(
                raw,
                self._config,
                self._browser_cat,
            )
        if raw.source == "windows_events":
            return self._parser.parse_windows_events(
                raw,
                self._config,
            )
        if raw.source == "calendar":
            return self._parser.parse_calendar(
                raw,
                self._config,
            )
        return None
