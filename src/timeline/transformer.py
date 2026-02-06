"""Transform raw events into normalized timeline events.

Handles:
- Source-specific parsing (git, browser, etc.)
- Cascading categorization
- Project name mapping
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath

from timeline.config import TimelineConfig
from timeline.models import RawEvent, TimelineEvent

# Conventional commit prefixes → categories
CONVENTIONAL_COMMIT_MAP: dict[str, str] = {
    "feat": "feature",
    "fix": "bugfix",
    "docs": "docs",
    "style": "style",
    "refactor": "refactor",
    "perf": "performance",
    "test": "test",
    "build": "build",
    "ci": "ci",
    "chore": "chore",
    "revert": "revert",
}

CONVENTIONAL_COMMIT_RE = re.compile(
    r"^(?P<type>" + "|".join(CONVENTIONAL_COMMIT_MAP.keys()) + r")(?:\(.+?\))?!?:\s*(?P<desc>.+)",
    re.IGNORECASE,
)

# File extension → category for fallback categorization
DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
CONFIG_EXTENSIONS = {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".env"}
TEST_PATTERNS = {"test_", "_test.", "tests/", "test/", "spec/", ".spec.", ".test."}
CI_PATTERNS = {".github/", "Dockerfile", "docker-compose", ".gitlab-ci", "Jenkinsfile"}


class Transformer:
    def __init__(self, config: TimelineConfig) -> None:
        self._config = config

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
            return self._transform_git(raw)
        if raw.source == "shell":
            return self._transform_shell(raw)
        if raw.source == "browser":
            return self._transform_browser(raw)
        return None

    def _transform_git(self, raw: RawEvent) -> TimelineEvent | None:
        """Transform a raw git commit into a timeline event."""
        data = raw.raw_data
        try:
            timestamp = datetime.fromisoformat(data["timestamp"])
        except (KeyError, ValueError):
            return None

        subject = data.get("subject", "")
        files = data.get("files", [])
        repo_name = data.get("repo_name", "unknown")

        # Cascading categorization
        category = self._categorize_git_commit(subject, files)

        # Clean description — strip conventional commit prefix
        description = self._clean_description(subject)

        # Project mapping
        project = self._map_project(repo_name, data.get("repo_path", ""))

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

    def _transform_shell(self, raw: RawEvent) -> TimelineEvent | None:
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
        category = self._categorize_shell_command(command)
        project = self._map_project_from_cwd(cwd)

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

    def _categorize_shell_command(self, command: str) -> str:
        """Categorize shell command by first token / known patterns."""
        first_token = command.split()[0].lower() if command.split() else ""

        # Version control
        if first_token in ("git", "gh", "hub"):
            return "vcs"
        # Package management / build
        if first_token in ("npm", "yarn", "pnpm", "pip", "uv", "cargo", "dotnet", "nuget", "mvn"):
            return "build"
        # Testing
        if first_token in ("pytest", "jest", "vitest", "dotnet") and "test" in command.lower():
            return "test"
        # Docker / infra
        if first_token in ("docker", "docker-compose", "kubectl", "terraform", "az", "aws"):
            return "infra"
        # Editors
        if first_token in ("code", "vim", "nvim", "nano", "notepad"):
            return "editor"
        # Navigation / file ops
        if first_token in ("cd", "ls", "dir", "pwd", "z", "cat", "Get-ChildItem", "Set-Location"):
            return "navigation"
        # SSH / remote
        if first_token in ("ssh", "scp", "rsync"):
            return "remote"

        return "command"

    def _map_project_from_cwd(self, cwd: str) -> str | None:
        """Try to map a working directory to a project name."""
        if not cwd:
            return None
        # Check project mapping against cwd path
        for pattern, project_name in self._config.project_mapping.items():
            if pattern in cwd:
                return project_name
        # Fallback: extract last meaningful directory segment
        # e.g. C:\Users\bjopunsv\Dev\customer-api → customer-api
        parts = cwd.replace("\\", "/").rstrip("/").split("/")
        if parts:
            return parts[-1]
        return None

    def _transform_browser(self, raw: RawEvent) -> TimelineEvent | None:
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
        if any(skip in domain for skip in self._config.browser.skip_domains):
            return None

        category = self._categorize_browser_visit(domain, url)
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

    def _categorize_browser_visit(self, domain: str, url: str) -> str:
        """Categorize browser visit by domain patterns."""
        d = domain.lower()

        # Development / code
        if any(
            s in d
            for s in (
                "github.com",
                "gitlab.com",
                "bitbucket.org",
                "dev.azure.com",
                "stackoverflow.com",
                "stackexchange.com",
            )
        ):
            return "development"

        # Documentation / reference
        if any(
            s in d
            for s in (
                "docs.",
                "wiki.",
                "learn.microsoft.com",
                "developer.mozilla.org",
                "devdocs.io",
                "readthedocs.io",
                "man7.org",
            )
        ):
            return "reference"

        # Communication
        if any(
            s in d
            for s in (
                "teams.microsoft.com",
                "slack.com",
                "discord.com",
                "outlook.office",
                "mail.",
                "gmail.com",
            )
        ):
            return "communication"

        # Project management
        if any(
            s in d
            for s in (
                "jira.",
                "atlassian.",
                "trello.com",
                "linear.app",
                "notion.so",
                "asana.com",
            )
        ):
            return "planning"

        # Cloud / infra
        if any(
            s in d
            for s in (
                "portal.azure.com",
                "console.aws.amazon.com",
                "console.cloud.google.com",
            )
        ):
            return "cloud"

        # AI / LLM tools
        if any(
            s in d for s in ("claude.ai", "chatgpt.com", "chat.openai.com", "copilot.microsoft.com")
        ):
            return "ai"

        # Search
        if any(s in d for s in ("google.com/search", "bing.com/search", "duckduckgo.com")):
            return "search"

        # SharePoint / OneDrive
        if "sharepoint.com" in d or "onedrive.live.com" in d:
            return "documents"

        return "browsing"

    def _categorize_git_commit(self, subject: str, files: list[dict]) -> str:
        """Cascading categorization: conventional commit → file types → fallback."""
        # 1. Conventional commit prefix
        match = CONVENTIONAL_COMMIT_RE.match(subject)
        if match:
            commit_type = match.group("type").lower()
            return CONVENTIONAL_COMMIT_MAP.get(commit_type, "commit")

        # 2. File type analysis
        if files:
            category = self._categorize_by_files(files)
            if category:
                return category

        # 3. Fallback
        return "commit"

    def _categorize_by_files(self, files: list[dict]) -> str | None:
        """Categorize commit based on files changed."""
        if not files:
            return None

        file_paths = [f.get("path", "") for f in files]
        categories: set[str] = set()

        for path in file_paths:
            path_lower = path.lower()
            p = PurePosixPath(path_lower)

            if any(pattern in path_lower for pattern in CI_PATTERNS):
                categories.add("ci")
            elif any(pattern in path_lower for pattern in TEST_PATTERNS):
                categories.add("test")
            elif p.suffix in DOC_EXTENSIONS:
                categories.add("docs")
            elif p.suffix in CONFIG_EXTENSIONS:
                categories.add("config")
            else:
                categories.add("code")

        # If all files are one category, use it
        if len(categories) == 1:
            return categories.pop()

        # Mixed — default to "code" if code is in the mix
        if "code" in categories:
            return "code"

        return None

    def _clean_description(self, subject: str) -> str:
        """Strip conventional commit prefix from description."""
        match = CONVENTIONAL_COMMIT_RE.match(subject)
        if match:
            return match.group("desc").strip()
        return subject.strip()

    def _map_project(self, repo_name: str, repo_path: str) -> str:
        """Map repo to project name using config mappings, fallback to repo name."""
        for pattern, project_name in self._config.project_mapping.items():
            if pattern in repo_name or pattern in repo_path:
                return project_name
        return repo_name
