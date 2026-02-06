"""Tests for git collector — parsing logic, no real git repos needed."""

from timeline.collectors.git import GitCollector
from timeline.config import GitAuthor, GitCollectorConfig


class TestGitLogParsing:
    """Test parsing of git log output."""

    def setup_method(self):
        config = GitCollectorConfig(
            enabled=True,
            authors=[GitAuthor(email="bjorn@test.com")],
            repos=[],
        )
        self.collector = GitCollector(config)

    def test_parse_single_commit(self):
        # NUL-delimited: hash, author_name, author_email, timestamp, subject, refs, body
        raw = (
            "abc123\x00Bjorn\x00bjorn@test.com\x00"
            "2026-02-06T09:12:00+01:00\x00fix: auth bug\x00HEAD -> main\x00"
        )
        result = self.collector._parse_single_commit(raw)
        assert result is not None
        assert result["hash"] == "abc123"
        assert result["subject"] == "fix: auth bug"

    def test_parse_single_commit_with_special_chars(self):
        """Commit messages with quotes/backslashes should parse correctly."""
        raw = (
            "abc123\x00Bjorn\x00bjorn@test.com\x00"
            '2026-02-06T09:12:00+01:00\x00fix: handle "quoted" paths\x00\x00'
            'Body with C:\\Users\\path and "quotes"'
        )
        result = self.collector._parse_single_commit(raw)
        assert result is not None
        assert result["subject"] == 'fix: handle "quoted" paths'
        assert "C:\\Users\\path" in result["body"]

    def test_parse_log_output_multiple_commits(self):
        sep = "---TIMELINE_COMMIT_SEP---"
        c1 = "aaa\x00A\x00a@test.com\x002026-02-06T09:00:00+01:00\x00first\x00\x00"
        c2 = "bbb\x00B\x00b@test.com\x002026-02-06T10:00:00+01:00\x00second\x00\x00"
        output = f"{sep}{c1}{sep}{c2}"
        results = self.collector._parse_log_output(output)
        assert len(results) == 2
        assert results[0]["hash"] == "aaa"
        assert results[1]["hash"] == "bbb"

    def test_parse_empty_output(self):
        assert self.collector._parse_log_output("") == []
        assert self.collector._parse_log_output("  \n  ") == []

    def test_parse_malformed_entry_skipped(self):
        sep = "---TIMELINE_COMMIT_SEP---"
        valid = "valid\x00A\x00a@test.com\x002026-02-06T09:00:00+01:00\x00ok\x00\x00"
        output = f"{sep}not enough fields{sep}{valid}"
        results = self.collector._parse_log_output(output)
        assert len(results) == 1
        assert results[0]["hash"] == "valid"

    def test_source_name(self):
        assert self.collector.source_name() == "git"

    def test_is_cheap(self):
        assert self.collector.is_cheap() is True
