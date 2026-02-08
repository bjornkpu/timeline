"""Tests for the transformer — raw → events with cascading categorization."""

from datetime import UTC, datetime

from timeline.config import TimelineConfig
from timeline.models import RawEvent
from timeline.transformer import Transformer


def _make_raw_git(
    subject: str,
    files: list[dict] | None = None,
    repo_name: str = "my-project",
) -> RawEvent:
    """Helper to create a raw git event."""
    return RawEvent(
        source="git",
        collected_at=datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
        raw_data={
            "hash": f"hash_{subject[:8]}",
            "author_name": "Bjorn",
            "author_email": "bjorn@test.com",
            "timestamp": "2026-02-06T09:00:00+01:00",
            "subject": subject,
            "body": "",
            "refs": "",
            "repo_path": f"C:\\Dev\\{repo_name}",
            "repo_name": repo_name,
            "files": files or [],
        },
    )


class TestCascadingCategorization:
    """Test the 3-level categorization: conventional commit → file types → fallback."""

    def setup_method(self):
        self.transformer = Transformer(TimelineConfig())

    # Level 1: Conventional commits
    def test_feat_commit(self):
        raw = _make_raw_git("feat: add user dashboard")
        event = self.transformer.transform([raw])[0]
        assert event.category == "feature"
        assert event.description == "add user dashboard"

    def test_fix_commit(self):
        raw = _make_raw_git("fix: auth token refresh")
        event = self.transformer.transform([raw])[0]
        assert event.category == "bugfix"

    def test_docs_commit(self):
        raw = _make_raw_git("docs: update API reference")
        event = self.transformer.transform([raw])[0]
        assert event.category == "docs"

    def test_refactor_commit(self):
        raw = _make_raw_git("refactor: extract auth module")
        event = self.transformer.transform([raw])[0]
        assert event.category == "refactor"

    def test_test_commit(self):
        raw = _make_raw_git("test: add integration tests")
        event = self.transformer.transform([raw])[0]
        assert event.category == "test"

    def test_chore_commit(self):
        raw = _make_raw_git("chore: bump dependencies")
        event = self.transformer.transform([raw])[0]
        assert event.category == "chore"

    def test_ci_commit(self):
        raw = _make_raw_git("ci: update GitHub Actions workflow")
        event = self.transformer.transform([raw])[0]
        assert event.category == "ci"

    def test_scoped_conventional_commit(self):
        raw = _make_raw_git("feat(auth): add OAuth2 support")
        event = self.transformer.transform([raw])[0]
        assert event.category == "feature"
        assert event.description == "add OAuth2 support"

    def test_breaking_conventional_commit(self):
        raw = _make_raw_git("feat!: redesign API")
        event = self.transformer.transform([raw])[0]
        assert event.category == "feature"

    # Level 2: File type analysis
    def test_all_docs_files(self):
        raw = _make_raw_git(
            "update documentation",
            files=[
                {"path": "README.md", "insertions": 10, "deletions": 2},
                {"path": "docs/guide.md", "insertions": 5, "deletions": 0},
            ],
        )
        event = self.transformer.transform([raw])[0]
        assert event.category == "docs"

    def test_all_test_files(self):
        raw = _make_raw_git(
            "add more tests",
            files=[
                {"path": "tests/test_auth.py", "insertions": 50, "deletions": 0},
                {"path": "tests/test_api.py", "insertions": 30, "deletions": 0},
            ],
        )
        event = self.transformer.transform([raw])[0]
        assert event.category == "test"

    def test_all_config_files(self):
        raw = _make_raw_git(
            "update config",
            files=[
                {"path": "deploy.yaml", "insertions": 5, "deletions": 2},
                {"path": "settings.toml", "insertions": 3, "deletions": 1},
            ],
        )
        event = self.transformer.transform([raw])[0]
        assert event.category == "config"

    def test_ci_files(self):
        raw = _make_raw_git(
            "update pipeline",
            files=[
                {"path": ".github/workflows/ci.yml", "insertions": 10, "deletions": 5},
            ],
        )
        event = self.transformer.transform([raw])[0]
        assert event.category == "ci"

    def test_mixed_files_with_code(self):
        raw = _make_raw_git(
            "update auth and tests",
            files=[
                {"path": "src/auth.py", "insertions": 42, "deletions": 12},
                {"path": "tests/test_auth.py", "insertions": 18, "deletions": 3},
            ],
        )
        event = self.transformer.transform([raw])[0]
        assert event.category == "code"

    # Level 3: Fallback
    def test_fallback_no_files(self):
        raw = _make_raw_git("merge branch 'main'")
        event = self.transformer.transform([raw])[0]
        assert event.category == "commit"


class TestProjectMapping:
    def test_maps_repo_to_project(self):
        config = TimelineConfig(
            project_mapping={"customer-api": "Customer Platform"},
        )
        transformer = Transformer(config)
        raw = _make_raw_git("fix: bug", repo_name="customer-api")
        event = transformer.transform([raw])[0]
        assert event.project == "Customer Platform"

    def test_multiple_repos_same_project(self):
        config = TimelineConfig(
            project_mapping={
                "customer-api": "Customer Platform",
                "customer-frontend": "Customer Platform",
            },
        )
        transformer = Transformer(config)

        e1 = transformer.transform([_make_raw_git("fix: bug", repo_name="customer-api")])[0]
        e2 = transformer.transform([_make_raw_git("feat: ui", repo_name="customer-frontend")])[0]
        assert e1.project == "Customer Platform"
        assert e2.project == "Customer Platform"

    def test_fallback_to_repo_name(self):
        config = TimelineConfig(project_mapping={})
        transformer = Transformer(config)
        raw = _make_raw_git("fix: bug", repo_name="my-side-project")
        event = transformer.transform([raw])[0]
        assert event.project == "my-side-project"


class TestGitMetadata:
    def setup_method(self):
        self.transformer = Transformer(TimelineConfig())

    def test_metadata_includes_stats(self):
        raw = _make_raw_git(
            "fix: something",
            files=[
                {"path": "src/main.py", "insertions": 10, "deletions": 5},
                {"path": "src/util.py", "insertions": 3, "deletions": 1},
            ],
        )
        event = self.transformer.transform([raw])[0]
        assert event.metadata["insertions"] == 13
        assert event.metadata["deletions"] == 6
        assert event.metadata["commit_hash"] == "hash_fix: som"
        assert len(event.metadata["files_changed"]) == 2

    def test_metadata_includes_author(self):
        raw = _make_raw_git("feat: add feature")
        event = self.transformer.transform([raw])[0]
        assert event.metadata["author_email"] == "bjorn@test.com"
        assert event.metadata["repo_name"] == "my-project"


class TestWindowsEventsTransformer:
    """Test Windows event log transformation."""

    def setup_method(self):
        self.transformer = Transformer(TimelineConfig())

    def test_parse_logon_event(self):
        """Test that logon events are categorized as 'active'."""
        raw = RawEvent(
            source="windows_events",
            collected_at=datetime(2026, 2, 8, 12, 0, tzinfo=UTC),
            raw_data={
                "event_type": "logon",
                "event_id": 7001,
                "timestamp": "2026-02-08T12:34:55.620115+00:00",
            },
        )
        events = self.transformer.transform([raw])
        assert len(events) == 1
        event = events[0]
        assert event.source == "windows_events"
        assert event.category == "active"
        assert event.description == "Workstation logon"

    def test_parse_logoff_event(self):
        """Test that logoff events are categorized as 'afk'."""
        raw = RawEvent(
            source="windows_events",
            collected_at=datetime(2026, 2, 8, 12, 0, tzinfo=UTC),
            raw_data={
                "event_type": "logoff",
                "event_id": 7002,
                "timestamp": "2026-02-08T12:33:12.254599+00:00",
            },
        )
        events = self.transformer.transform([raw])
        assert len(events) == 1
        event = events[0]
        assert event.source == "windows_events"
        assert event.category == "afk"
        assert event.description == "Workstation logoff"

    def test_invalid_event_type_skipped(self):
        """Test that events with invalid event_type are skipped."""
        raw = RawEvent(
            source="windows_events",
            collected_at=datetime(2026, 2, 8, 12, 0, tzinfo=UTC),
            raw_data={
                "event_type": "invalid",
                "event_id": 9999,
                "timestamp": "2026-02-08T12:34:55+00:00",
            },
        )
        events = self.transformer.transform([raw])
        assert len(events) == 0

    def test_missing_timestamp_skipped(self):
        """Test that events without timestamp are skipped."""
        raw = RawEvent(
            source="windows_events",
            collected_at=datetime(2026, 2, 8, 12, 0, tzinfo=UTC),
            raw_data={
                "event_type": "logon",
                "event_id": 7001,
            },
        )
        events = self.transformer.transform([raw])
        assert len(events) == 0

    def test_metadata_preserved(self):
        """Test that event metadata is preserved in transformation."""
        raw = RawEvent(
            source="windows_events",
            collected_at=datetime(2026, 2, 8, 12, 0, tzinfo=UTC),
            raw_data={
                "event_type": "logon",
                "event_id": 7001,
                "timestamp": "2026-02-08T12:34:55+00:00",
            },
        )
        event = self.transformer.transform([raw])[0]
        assert event.metadata["event_type"] == "logon"
        assert event.metadata["event_id"] == 7001
