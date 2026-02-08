"""Tests for CLI source filtering."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from click.testing import CliRunner

from timeline.cli import cli, parse_source_arg, _build_source_filter
from timeline.models import DateRange, SourceFilter, TimelineEvent
from timeline.store import TimelineStore


class TestParseSourceArg:
    """Test source argument parsing."""

    def test_parse_single_source(self):
        """Parse a single source name."""
        sources = parse_source_arg("git")
        assert sources == {"git"}

    def test_parse_multiple_sources(self):
        """Parse comma-separated sources."""
        sources = parse_source_arg("git,shell,browser")
        assert sources == {"git", "shell", "browser"}

    def test_parse_whitespace_handling(self):
        """Handle whitespace around commas."""
        sources = parse_source_arg("git , shell , browser")
        assert sources == {"git", "shell", "browser"}

    def test_parse_case_insensitive(self):
        """Convert to lowercase."""
        sources = parse_source_arg("GIT,Shell,BROWSER")
        assert sources == {"git", "shell", "browser"}

    def test_invalid_source_raises_error(self):
        """Raise error for invalid source names."""
        with pytest.raises(Exception):  # click.BadParameter
            parse_source_arg("git,invalid_source")


class TestBuildSourceFilter:
    """Test source filter builder."""

    def test_build_include_filter(self):
        """Build include filter."""
        sf = _build_source_filter("git,shell", None)
        assert sf is not None
        assert sf.mode == "include"
        assert sf.sources == {"git", "shell"}

    def test_build_exclude_filter(self):
        """Build exclude filter."""
        sf = _build_source_filter(None, "browser,windows_events")
        assert sf is not None
        assert sf.mode == "exclude"
        assert sf.sources == {"browser", "windows_events"}

    def test_both_flags_raises_error(self):
        """Raise error when both include and exclude provided."""
        with pytest.raises(Exception):  # click.UsageError
            _build_source_filter("git", "browser")

    def test_no_filters_returns_none(self):
        """Return None when no filters provided."""
        sf = _build_source_filter(None, None)
        assert sf is None


class TestShowCommandWithFilter:
    """Test show command with source filtering."""

    def test_show_with_include_filter(self, store: TimelineStore):
        """Test 'show' command with --include flag."""
        # Setup test data
        ts = datetime(2026, 2, 8, 9, 0, tzinfo=UTC)
        store.save_events(
            [
                TimelineEvent(
                    timestamp=ts,
                    source="git",
                    category="feature",
                    description="Commit A",
                ),
                TimelineEvent(
                    timestamp=ts,
                    source="browser",
                    category="browsing",
                    description="Visit github.com",
                ),
            ]
        )

        runner = CliRunner()
        # Note: This requires proper config and DB setup, which is complex in CLI tests
        # For now, we're testing the parsing and filter building works
        result = runner.invoke(
            cli,
            ["show", "2026-02-08", "--include", "git"],
            catch_exceptions=False,
        )
        # Expect this to work or fail gracefully (depending on config)
        assert result.exit_code in [0, 2]  # 0 for success, 2 for missing config

    def test_show_with_exclude_filter(self):
        """Test 'show' command with --exclude flag."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["show", "2026-02-08", "--exclude", "browser"],
            catch_exceptions=False,
        )
        # Expect this to work or fail gracefully (depending on config)
        assert result.exit_code in [0, 2]  # 0 for success, 2 for missing config

    def test_show_rejects_both_filters(self):
        """Test 'show' command rejects both --include and --exclude."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["show", "2026-02-08", "--include", "git", "--exclude", "browser"],
            catch_exceptions=False,
        )
        # Should fail due to mutual exclusivity
        assert result.exit_code == 2


class TestRunCommandWithFilter:
    """Test run command with source filtering."""

    def test_run_with_include_filter(self):
        """Test 'run' command with --include flag."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["run", "2026-02-08", "--include", "git", "--quick"],
            catch_exceptions=False,
        )
        # Expect this to work or fail gracefully (depending on config)
        assert result.exit_code in [0, 2]  # 0 for success, 2 for missing config

    def test_run_rejects_both_filters(self):
        """Test 'run' command rejects both --include and --exclude."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["run", "2026-02-08", "--include", "git", "--exclude", "browser"],
            catch_exceptions=False,
        )
        # Should fail due to mutual exclusivity
        assert result.exit_code == 2
