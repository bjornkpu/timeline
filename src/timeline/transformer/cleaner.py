"""Description cleaning and normalization for timeline events."""

from __future__ import annotations

import re

# Conventional commit prefixes
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


class DescriptionCleaner:
    """Clean and normalize event descriptions."""

    def clean(self, subject: str) -> str:
        """Strip conventional commit prefix from description."""
        match = CONVENTIONAL_COMMIT_RE.match(subject)
        if match:
            return match.group("desc").strip()
        return subject.strip()
