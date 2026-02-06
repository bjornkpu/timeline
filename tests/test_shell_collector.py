"""Tests for shell history collector — JSONL parsing and date filtering."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from timeline.collectors.shell import ShellCollector
from timeline.config import ShellCollectorConfig
from timeline.models import DateRange, RawEvent


def _sample_jsonl() -> str:
    """Build sample JSONL test data."""
    lines = [
        _jsonl(
            "2026-02-05T09:00:00.0000000+01:00",
            "git status",
            "C:\\Users\\bjopunsv\\Dev\\project-a",
            1234,
        ),
        _jsonl(
            "2026-02-05T10:30:00.0000000+01:00",
            "uv run pytest",
            "C:\\Users\\bjopunsv\\Dev\\timeline",
            1234,
        ),
        _jsonl(
            "2026-02-05T14:00:00.0000000+01:00",
            "docker compose up -d",
            "C:\\Users\\bjopunsv\\Dev\\project-a",
            5678,
        ),
        _jsonl("2026-02-06T08:15:00.0000000+01:00", "cd Dev", "C:\\Users\\bjopunsv", 9012),
        "not valid json line",
        _jsonl(
            "2026-02-06T11:00:00.0000000+01:00",
            "kubectl get pods",
            "C:\\Users\\bjopunsv\\Dev\\infra",
            9012,
        ),
    ]
    return "\n".join(lines) + "\n"


def _jsonl(ts: str, cmd: str, cwd: str, pid: int) -> str:
    return json.dumps({"timestamp": ts, "command": cmd, "cwd": cwd, "shell": "pwsh", "pid": pid})


def _write_history(tmp_path, content: str | None = None) -> ShellCollector:
    if content is None:
        content = _sample_jsonl()
    """Create a shell collector with a temp history file."""
    history_path = tmp_path / "shell_history.jsonl"
    history_path.write_text(content, encoding="utf-8")
    config = ShellCollectorConfig(enabled=True, history_path=str(history_path))
    return ShellCollector(config)


class TestShellCollector:
    def test_source_name(self, tmp_path):
        collector = _write_history(tmp_path)
        assert collector.source_name() == "shell"

    def test_is_cheap(self, tmp_path):
        collector = _write_history(tmp_path)
        assert collector.is_cheap() is True

    def test_collects_events_for_date(self, tmp_path):
        collector = _write_history(tmp_path)
        dr = DateRange.for_date(date(2026, 2, 5))
        events = collector.collect(dr)
        assert len(events) == 3
        assert events[0].raw_data["command"] == "git status"
        assert events[1].raw_data["command"] == "uv run pytest"
        assert events[2].raw_data["command"] == "docker compose up -d"

    def test_filters_by_date(self, tmp_path):
        collector = _write_history(tmp_path)
        dr = DateRange.for_date(date(2026, 2, 6))
        events = collector.collect(dr)
        assert len(events) == 2
        assert events[0].raw_data["command"] == "cd Dev"
        assert events[1].raw_data["command"] == "kubectl get pods"

    def test_skips_malformed_lines(self, tmp_path):
        """Invalid JSON lines should be silently skipped."""
        collector = _write_history(tmp_path)
        # SAMPLE_JSONL has one invalid line — all valid ones should still parse
        dr = DateRange(start=date(2026, 2, 5), end=date(2026, 2, 6))
        events = collector.collect(dr)
        assert len(events) == 5

    def test_empty_file(self, tmp_path):
        collector = _write_history(tmp_path, content="")
        dr = DateRange.for_date(date(2026, 2, 5))
        events = collector.collect(dr)
        assert events == []

    def test_missing_file(self, tmp_path):
        config = ShellCollectorConfig(
            enabled=True,
            history_path=str(tmp_path / "nonexistent.jsonl"),
        )
        collector = ShellCollector(config)
        dr = DateRange.for_date(date(2026, 2, 5))
        events = collector.collect(dr)
        assert events == []

    def test_event_timestamp_set(self, tmp_path):
        collector = _write_history(tmp_path)
        dr = DateRange.for_date(date(2026, 2, 5))
        events = collector.collect(dr)
        assert events[0].event_timestamp is not None
        assert events[0].event_timestamp.tzinfo is not None

    def test_preserves_metadata(self, tmp_path):
        collector = _write_history(tmp_path)
        dr = DateRange.for_date(date(2026, 2, 5))
        events = collector.collect(dr)
        data = events[0].raw_data
        assert data["cwd"] == "C:\\Users\\bjopunsv\\Dev\\project-a"
        assert data["shell"] == "pwsh"
        assert data["pid"] == 1234


class TestShellTransformer:
    """Test shell-specific transformer rules."""

    def test_categorize_git_command(self, config):
        from timeline.transformer import Transformer

        transformer = Transformer(config)
        raw = _make_raw_shell("git push origin main", "C:\\Dev\\project-a")
        event = transformer.transform([raw])[0]
        assert event.category == "vcs"

    def test_categorize_build_command(self, config):
        from timeline.transformer import Transformer

        transformer = Transformer(config)
        raw = _make_raw_shell("uv run pytest", "C:\\Dev\\timeline")
        event = transformer.transform([raw])[0]
        assert event.category == "build"

    def test_categorize_docker_command(self, config):
        from timeline.transformer import Transformer

        transformer = Transformer(config)
        raw = _make_raw_shell("docker compose up -d", "C:\\Dev\\project-a")
        event = transformer.transform([raw])[0]
        assert event.category == "infra"

    def test_categorize_navigation(self, config):
        from timeline.transformer import Transformer

        transformer = Transformer(config)
        raw = _make_raw_shell("cd Dev", "C:\\Users\\bjopunsv")
        event = transformer.transform([raw])[0]
        assert event.category == "navigation"

    def test_categorize_unknown(self, config):
        from timeline.transformer import Transformer

        transformer = Transformer(config)
        raw = _make_raw_shell("some-random-command --flag", "C:\\Dev\\stuff")
        event = transformer.transform([raw])[0]
        assert event.category == "command"

    def test_project_from_cwd_mapping(self):
        from timeline.config import TimelineConfig
        from timeline.transformer import Transformer

        config = TimelineConfig(
            project_mapping={"customer-api": "Customer Platform"},
        )
        transformer = Transformer(config)
        raw = _make_raw_shell("git status", "C:\\Users\\bjopunsv\\Dev\\customer-api")
        event = transformer.transform([raw])[0]
        assert event.project == "Customer Platform"

    def test_project_from_cwd_fallback(self):
        from timeline.config import TimelineConfig
        from timeline.transformer import Transformer

        config = TimelineConfig(project_mapping={})
        transformer = Transformer(config)
        raw = _make_raw_shell("git status", "C:\\Users\\bjopunsv\\Dev\\my-project")
        event = transformer.transform([raw])[0]
        assert event.project == "my-project"

    def test_description_is_full_command(self, config):
        from timeline.transformer import Transformer

        transformer = Transformer(config)
        raw = _make_raw_shell("docker compose up -d", "C:\\Dev\\project-a")
        event = transformer.transform([raw])[0]
        assert event.description == "docker compose up -d"


def _make_raw_shell(command: str, cwd: str) -> RawEvent:
    return RawEvent(
        source="shell",
        collected_at=datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
        raw_data={
            "timestamp": "2026-02-06T10:00:00+01:00",
            "command": command,
            "cwd": cwd,
            "shell": "pwsh",
            "pid": 1234,
        },
        event_timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
    )
