"""Git commit collector — scans local repos for commits."""

from __future__ import annotations

import contextlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from timeline.collectors.base import Collector
from timeline.config import GitCollectorConfig
from timeline.models import DateRange, RawEvent

# Git log format: NUL-delimited fields to avoid escaping issues.
# %H  = commit hash
# %an = author name
# %ae = author email
# %aI = author date ISO 8601
# %s  = subject (first line of commit message)
# %b  = body
# %D  = ref names
# Fields separated by %x00 (NUL), body is last to allow newlines.
GIT_LOG_FIELDS = ("hash", "author_name", "author_email", "timestamp", "subject", "refs", "body")
GIT_LOG_FORMAT = "%H%x00%an%x00%ae%x00%aI%x00%s%x00%D%x00%b"

# Separator to split commits — unlikely to appear in commit messages
COMMIT_SEP = "---TIMELINE_COMMIT_SEP---"


class GitCollector(Collector):
    def __init__(self, config: GitCollectorConfig) -> None:
        self._config = config

    def source_name(self) -> str:
        return "git"

    def is_cheap(self) -> bool:
        return True

    def collect(self, date_range: DateRange) -> list[RawEvent]:
        all_events: list[RawEvent] = []
        seen_hashes: set[str] = set()
        now = datetime.now(UTC)

        for repo_path in self._config.repos:
            repo = Path(repo_path)
            if not (repo / ".git").exists():
                continue

            commits = self._collect_repo(repo, date_range)
            for commit in commits:
                commit_hash = commit["hash"]
                if commit_hash in seen_hashes:
                    continue
                seen_hashes.add(commit_hash)

                commit["repo_path"] = str(repo)
                commit["repo_name"] = repo.name

                # Parse the actual commit timestamp
                event_ts: datetime | None = None
                with contextlib.suppress(KeyError, ValueError):
                    event_ts = datetime.fromisoformat(commit["timestamp"])

                all_events.append(
                    RawEvent(
                        source="git",
                        collected_at=now,
                        raw_data=commit,
                        event_timestamp=event_ts,
                    )
                )

        return all_events

    def _collect_repo(self, repo: Path, date_range: DateRange) -> list[dict]:
        """Collect commits from a single repo via git log --all + reflog."""
        author_emails = {a.email for a in self._config.authors}
        commits: list[dict] = []
        seen: set[str] = set()

        # 1. git log --all (all local branches)
        log_commits = self._run_git_log(repo, date_range)
        for c in log_commits:
            if c["author_email"] in author_emails and c["hash"] not in seen:
                seen.add(c["hash"])
                commits.append(c)

        # 2. reflog for orphaned commits
        reflog_hashes = self._run_reflog(repo, date_range)
        orphaned = reflog_hashes - seen
        if orphaned:
            for commit_hash in orphaned:
                c = self._get_commit_details(repo, commit_hash)
                if c and c["author_email"] in author_emails:
                    seen.add(c["hash"])
                    commits.append(c)

        # 3. Enrich with numstat
        for c in commits:
            c["files"] = self._get_numstat(repo, c["hash"])

        return commits

    def _run_git_log(self, repo: Path, date_range: DateRange) -> list[dict]:
        """Run git log --all and parse output."""
        cmd = [
            "git",
            "log",
            "--all",
            f"--after={date_range.start_utc.isoformat()}",
            f"--before={date_range.end_utc.isoformat()}",
            f"--format={COMMIT_SEP}{GIT_LOG_FORMAT}",
        ]
        output = self._run_cmd(cmd, repo)
        return self._parse_log_output(output)

    def _run_reflog(self, repo: Path, date_range: DateRange) -> set[str]:
        """Get commit hashes from reflog in date range."""
        cmd = [
            "git",
            "reflog",
            f"--after={date_range.start_utc.isoformat()}",
            f"--before={date_range.end_utc.isoformat()}",
            "--format=%H",
        ]
        output = self._run_cmd(cmd, repo)
        return {line.strip() for line in output.splitlines() if line.strip()}

    def _get_commit_details(self, repo: Path, commit_hash: str) -> dict | None:
        """Get details for a single commit by hash."""
        cmd = [
            "git",
            "log",
            "-1",
            f"--format={GIT_LOG_FORMAT}",
            commit_hash,
        ]
        output = self._run_cmd(cmd, repo)
        if not output.strip():
            return None
        return self._parse_single_commit(output.strip())

    def _get_numstat(self, repo: Path, commit_hash: str) -> list[dict]:
        """Get file change stats for a commit."""
        cmd = ["git", "diff-tree", "--no-commit-id", "--numstat", "-r", commit_hash]
        output = self._run_cmd(cmd, repo)
        files = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                added = int(parts[0]) if parts[0] != "-" else 0
                deleted = int(parts[1]) if parts[1] != "-" else 0
                files.append(
                    {
                        "path": parts[2],
                        "insertions": added,
                        "deletions": deleted,
                    }
                )
        return files

    def _parse_log_output(self, output: str) -> list[dict]:
        """Parse git log output with commit separator."""
        commits = []
        for chunk in output.split(COMMIT_SEP):
            chunk = chunk.strip()
            if not chunk:
                continue
            parsed = self._parse_single_commit(chunk)
            if parsed:
                commits.append(parsed)
        return commits

    def _parse_single_commit(self, raw: str) -> dict | None:
        """Parse a single commit from NUL-delimited fields."""
        parts = raw.split("\x00")
        if len(parts) < len(GIT_LOG_FIELDS):
            return None
        return {field: parts[i].strip() for i, field in enumerate(GIT_LOG_FIELDS)}

    def _run_cmd(self, cmd: list[str], cwd: Path) -> str:
        """Run a git command and return stdout."""
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            return result.stdout or ""
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return ""
