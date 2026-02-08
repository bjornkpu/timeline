"""Shared test fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from timeline.config import GitAuthor, GitCollectorConfig, TimelineConfig
from timeline.models import RawEvent, TimelineEvent
from timeline.store import TimelineStore


@pytest.fixture
def store() -> TimelineStore:
    """In-memory SQLite store."""
    s = TimelineStore(":memory:")
    return s


@pytest.fixture
def config(tmp_path) -> TimelineConfig:
    """Test config with temp DB path."""
    return TimelineConfig(
        db_path=tmp_path / "test.db",
        project_mapping={
            "customer-api": "Customer Platform",
            "customer-frontend": "Customer Platform",
            "internal-tools": "Internal Tooling",
        },
        git=GitCollectorConfig(
            enabled=True,
            authors=[
                GitAuthor(email="bjorn@workplace.com"),
                GitAuthor(email="bjorn@customer.com"),
            ],
            repos=[],
        ),
    )


@pytest.fixture
def sample_raw_git_events() -> list[RawEvent]:
    """Realistic git raw events."""
    now = datetime(2026, 2, 6, 12, 0, 0, tzinfo=UTC)
    return [
        RawEvent(
            source="git",
            collected_at=now,
            raw_data={
                "hash": "abc123def456",
                "author_name": "Bjorn",
                "author_email": "bjorn@customer.com",
                "timestamp": "2026-02-06T09:12:00+01:00",
                "subject": "fix: auth token refresh",
                "body": "",
                "refs": "HEAD -> main",
                "repo_path": "C:\\Users\\bjopunsv\\Dev\\customer-api",
                "repo_name": "customer-api",
                "files": [
                    {"path": "src/auth.py", "insertions": 42, "deletions": 12},
                    {"path": "tests/test_auth.py", "insertions": 18, "deletions": 3},
                ],
            },
            event_timestamp=datetime(2026, 2, 6, 8, 12, 0, tzinfo=UTC),
        ),
        RawEvent(
            source="git",
            collected_at=now,
            raw_data={
                "hash": "def789ghi012",
                "author_name": "Bjorn",
                "author_email": "bjorn@workplace.com",
                "timestamp": "2026-02-06T14:30:00+01:00",
                "subject": "update deployment config",
                "body": "",
                "refs": "",
                "repo_path": "C:\\Users\\bjopunsv\\Dev\\internal-tools",
                "repo_name": "internal-tools",
                "files": [
                    {"path": "deploy.yaml", "insertions": 5, "deletions": 2},
                ],
            },
            event_timestamp=datetime(2026, 2, 6, 13, 30, 0, tzinfo=UTC),
        ),
        RawEvent(
            source="git",
            collected_at=now,
            raw_data={
                "hash": "ghi345jkl678",
                "author_name": "Bjorn",
                "author_email": "bjorn@customer.com",
                "timestamp": "2026-02-06T11:15:00+01:00",
                "subject": "docs: update README with new auth docs",
                "body": "",
                "refs": "",
                "repo_path": "C:\\Users\\bjopunsv\\Dev\\customer-api",
                "repo_name": "customer-api",
                "files": [
                    {"path": "README.md", "insertions": 45, "deletions": 10},
                ],
            },
            event_timestamp=datetime(2026, 2, 6, 10, 15, 0, tzinfo=UTC),
        ),
    ]


@pytest.fixture
def sample_timeline_events() -> list[TimelineEvent]:
    """Pre-transformed timeline events."""
    return [
        TimelineEvent(
            timestamp=datetime(2026, 2, 6, 8, 12, 0, tzinfo=UTC),
            source="git",
            category="bugfix",
            description="auth token refresh",
            project="Customer Platform",
            metadata={
                "commit_hash": "abc123def456",
                "insertions": 60,
                "deletions": 15,
                "repo_name": "customer-api",
            },
        ),
        TimelineEvent(
            timestamp=datetime(2026, 2, 6, 10, 15, 0, tzinfo=UTC),
            source="git",
            category="docs",
            description="update README with new auth docs",
            project="Customer Platform",
            metadata={
                "commit_hash": "ghi345jkl678",
                "insertions": 45,
                "deletions": 10,
                "repo_name": "customer-api",
            },
        ),
        TimelineEvent(
            timestamp=datetime(2026, 2, 6, 13, 30, 0, tzinfo=UTC),
            source="git",
            category="config",
            description="update deployment config",
            project="Internal Tooling",
            metadata={
                "commit_hash": "def789ghi012",
                "insertions": 5,
                "deletions": 2,
                "repo_name": "internal-tools",
            },
        ),
    ]


@pytest.fixture
def sample_raw_calendar_events() -> list[RawEvent]:
    """Realistic calendar raw events."""
    now = datetime(2026, 2, 6, 12, 0, 0, tzinfo=UTC)
    return [
        RawEvent(
            source="calendar",
            collected_at=now,
            raw_data={
                "subject": "Ukentlig Team Demo",
                "start_iso": "2026-02-06T09:00:00+01:00",
                "end_iso": "2026-02-06T10:00:00+01:00",
                "organizer_name": "Alice Smith",
                "organizer_email": "alice@enova.com",
                "location": "Teams Meeting",
                "account_email": "user@enova.com",
                "is_recurring": False,
            },
            event_timestamp=datetime(2026, 2, 6, 8, 0, 0, tzinfo=UTC),
        ),
        RawEvent(
            source="calendar",
            collected_at=now,
            raw_data={
                "subject": "Fagsamling",
                "start_iso": "2026-02-06T14:00:00+01:00",
                "end_iso": "2026-02-06T15:00:00+01:00",
                "organizer_name": "Bob Johnson",
                "organizer_email": "bob@crayon.no",
                "location": "Conference Room B",
                "account_email": "user@crayon.no",
                "is_recurring": False,
            },
            event_timestamp=datetime(2026, 2, 6, 13, 0, 0, tzinfo=UTC),
        ),
        RawEvent(
            source="calendar",
            collected_at=now,
            raw_data={
                "subject": "1:1 with Manager",
                "start_iso": "2026-02-06T11:30:00+01:00",
                "end_iso": "2026-02-06T12:00:00+01:00",
                "organizer_name": "Carol White",
                "organizer_email": "carol@enova.com",
                "location": "",
                "account_email": "user@enova.com",
                "is_recurring": False,
            },
            event_timestamp=datetime(2026, 2, 6, 10, 30, 0, tzinfo=UTC),
        ),
    ]


@pytest.fixture
def sample_calendar_timeline_events() -> list[TimelineEvent]:
    """Pre-transformed calendar timeline events."""
    return [
        TimelineEvent(
            timestamp=datetime(2026, 2, 6, 8, 0, 0, tzinfo=UTC),
            source="calendar",
            category="calendar",
            description="Ukentlig Team Demo",
            project="user@enova.com",
            end_time=datetime(2026, 2, 6, 9, 0, 0, tzinfo=UTC),
            metadata={
                "organizer_name": "Alice Smith",
                "organizer_email": "alice@enova.com",
                "location": "Teams Meeting",
                "is_recurring": False,
            },
        ),
        TimelineEvent(
            timestamp=datetime(2026, 2, 6, 10, 30, 0, tzinfo=UTC),
            source="calendar",
            category="calendar",
            description="1:1 with Manager",
            project="user@enova.com",
            end_time=datetime(2026, 2, 6, 11, 0, 0, tzinfo=UTC),
            metadata={
                "organizer_name": "Carol White",
                "organizer_email": "carol@enova.com",
                "location": "",
                "is_recurring": False,
            },
        ),
        TimelineEvent(
            timestamp=datetime(2026, 2, 6, 13, 0, 0, tzinfo=UTC),
            source="calendar",
            category="calendar",
            description="Fagsamling",
            project="user@crayon.no",
            end_time=datetime(2026, 2, 6, 14, 0, 0, tzinfo=UTC),
            metadata={
                "organizer_name": "Bob Johnson",
                "organizer_email": "bob@crayon.no",
                "location": "Conference Room B",
                "is_recurring": False,
            },
        ),
    ]
