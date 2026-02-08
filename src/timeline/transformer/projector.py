"""Project name mapping for timeline events."""

from __future__ import annotations

from timeline.config import TimelineConfig


class ProjectMapper:
    """Map repository/directory names to project names."""

    def __init__(self, config: TimelineConfig) -> None:
        """Initialize project mapper with config."""
        self._config = config

    def map_from_repo(self, repo_name: str, repo_path: str) -> str:
        """Map repo to project name using config, fallback to repo name."""
        for pattern, project_name in self._config.project_mapping.items():
            if pattern in repo_name or pattern in repo_path:
                return project_name
        return repo_name

    def map_from_cwd(self, cwd: str) -> str | None:
        """Try to map a working directory to a project name."""
        if not cwd:
            return None

        # Check against project mapping
        for pattern, project_name in self._config.project_mapping.items():
            if pattern in cwd:
                return project_name

        # Fallback: extract last directory segment
        parts = cwd.replace("\\", "/").rstrip("/").split("/")
        return parts[-1] if parts else None
