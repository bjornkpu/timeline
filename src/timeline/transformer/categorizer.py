"""Registry-based categorization rules for timeline events."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

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


@dataclass(frozen=True)
class CategorizationRule:
    """A pluggable categorization rule: matcher function + category name."""

    name: str
    matcher: Callable[[str], bool]
    category: str


class GitCommitCategorizer:
    """Categorize git commits: conventional commit → file types → fallback."""

    def __init__(self) -> None:
        """Initialize git commit categorizer."""
        pass

    def categorize(self, subject: str, files: list[dict]) -> str:
        """Apply cascading categorization strategy."""
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

    @staticmethod
    def _categorize_by_files(files: list[dict]) -> str | None:
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


class ShellCommandCategorizer:
    """Categorize shell commands using pre-sorted rules."""

    def __init__(self) -> None:
        """Initialize shell command categorizer with pre-sorted rules."""
        # Rules in priority order (first match wins)
        self._rules = [
            CategorizationRule(
                name="vcs",
                matcher=self._is_vcs_command,
                category="vcs",
            ),
            CategorizationRule(
                name="build",
                matcher=self._is_build_command,
                category="build",
            ),
            CategorizationRule(
                name="test",
                matcher=self._is_test_command,
                category="test",
            ),
            CategorizationRule(
                name="infra",
                matcher=self._is_infra_command,
                category="infra",
            ),
            CategorizationRule(
                name="editor",
                matcher=self._is_editor_command,
                category="editor",
            ),
            CategorizationRule(
                name="navigation",
                matcher=self._is_navigation_command,
                category="navigation",
            ),
            CategorizationRule(
                name="remote",
                matcher=self._is_remote_command,
                category="remote",
            ),
            CategorizationRule(
                name="fallback",
                matcher=lambda _: True,
                category="command",
            ),
        ]

    def categorize(self, command: str) -> str:
        """Apply rules in pre-sorted order, return first match."""
        for rule in self._rules:
            try:
                if rule.matcher(command):
                    return rule.category
            except Exception:
                continue
        return "command"

    @staticmethod
    def _is_vcs_command(command: str) -> bool:
        first_token = command.split()[0].lower() if command.split() else ""
        return first_token in ("git", "gh", "hub")

    @staticmethod
    def _is_build_command(command: str) -> bool:
        first_token = command.split()[0].lower() if command.split() else ""
        return first_token in (
            "npm",
            "yarn",
            "pnpm",
            "pip",
            "uv",
            "cargo",
            "dotnet",
            "nuget",
            "mvn",
        )

    @staticmethod
    def _is_test_command(command: str) -> bool:
        first_token = command.split()[0].lower() if command.split() else ""
        return first_token in ("pytest", "jest", "vitest", "dotnet") and "test" in command.lower()

    @staticmethod
    def _is_infra_command(command: str) -> bool:
        first_token = command.split()[0].lower() if command.split() else ""
        return first_token in ("docker", "docker-compose", "kubectl", "terraform", "az", "aws")

    @staticmethod
    def _is_editor_command(command: str) -> bool:
        first_token = command.split()[0].lower() if command.split() else ""
        return first_token in ("code", "vim", "nvim", "nano", "notepad")

    @staticmethod
    def _is_navigation_command(command: str) -> bool:
        first_token = command.split()[0].lower() if command.split() else ""
        return first_token in (
            "cd",
            "ls",
            "dir",
            "pwd",
            "z",
            "cat",
            "Get-ChildItem",
            "Set-Location",
        )

    @staticmethod
    def _is_remote_command(command: str) -> bool:
        first_token = command.split()[0].lower() if command.split() else ""
        return first_token in ("ssh", "scp", "rsync")


class BrowserDomainCategorizer:
    """Categorize browser visits using domain rule registry."""

    def __init__(self) -> None:
        """Initialize browser domain categorizer with pre-sorted rules."""
        # Rules in priority order (first match wins)
        self._rules = [
            CategorizationRule(
                name="development",
                matcher=self._is_development_domain,
                category="development",
            ),
            CategorizationRule(
                name="reference",
                matcher=self._is_reference_domain,
                category="reference",
            ),
            CategorizationRule(
                name="communication",
                matcher=self._is_communication_domain,
                category="communication",
            ),
            CategorizationRule(
                name="planning",
                matcher=self._is_planning_domain,
                category="planning",
            ),
            CategorizationRule(
                name="cloud",
                matcher=self._is_cloud_domain,
                category="cloud",
            ),
            CategorizationRule(
                name="ai",
                matcher=self._is_ai_domain,
                category="ai",
            ),
            CategorizationRule(
                name="search",
                matcher=self._is_search_domain,
                category="search",
            ),
            CategorizationRule(
                name="documents",
                matcher=self._is_documents_domain,
                category="documents",
            ),
            CategorizationRule(
                name="fallback",
                matcher=lambda _: True,
                category="browsing",
            ),
        ]

    def categorize(self, domain: str, url: str = "") -> str:
        """Apply rules in pre-sorted order, return first match."""
        for rule in self._rules:
            try:
                if rule.matcher(domain):
                    return rule.category
            except Exception:
                continue
        return "browsing"

    @staticmethod
    def _is_development_domain(domain: str) -> bool:
        d = domain.lower()
        return any(
            s in d
            for s in (
                "github.com",
                "gitlab.com",
                "bitbucket.org",
                "dev.azure.com",
                "stackoverflow.com",
                "stackexchange.com",
            )
        )

    @staticmethod
    def _is_reference_domain(domain: str) -> bool:
        d = domain.lower()
        return any(
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
        )

    @staticmethod
    def _is_communication_domain(domain: str) -> bool:
        d = domain.lower()
        return any(
            s in d
            for s in (
                "teams.microsoft.com",
                "slack.com",
                "discord.com",
                "outlook.office",
                "mail.",
                "gmail.com",
            )
        )

    @staticmethod
    def _is_planning_domain(domain: str) -> bool:
        d = domain.lower()
        return any(
            s in d
            for s in (
                "jira.",
                "atlassian.",
                "trello.com",
                "linear.app",
                "notion.so",
                "asana.com",
            )
        )

    @staticmethod
    def _is_cloud_domain(domain: str) -> bool:
        d = domain.lower()
        return any(
            s in d
            for s in (
                "portal.azure.com",
                "console.aws.amazon.com",
                "console.cloud.google.com",
            )
        )

    @staticmethod
    def _is_ai_domain(domain: str) -> bool:
        d = domain.lower()
        return any(
            s in d for s in ("claude.ai", "chatgpt.com", "chat.openai.com", "copilot.microsoft.com")
        )

    @staticmethod
    def _is_search_domain(domain: str) -> bool:
        d = domain.lower()
        return any(s in d for s in ("google.com/search", "bing.com/search", "duckduckgo.com"))

    @staticmethod
    def _is_documents_domain(domain: str) -> bool:
        d = domain.lower()
        return "sharepoint.com" in d or "onedrive.live.com" in d
