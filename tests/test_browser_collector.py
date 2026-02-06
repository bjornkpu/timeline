"""Tests for browser history collector — SQLite parsing and categorization."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime

from timeline.collectors.browser import BrowserCollector
from timeline.config import BrowserCollectorConfig
from timeline.models import DateRange, RawEvent
from timeline.transformer import Transformer


def _create_test_db(tmp_path, visits: list[tuple]) -> str:
    """Create a minimal places.sqlite with test data.

    visits: list of (url, title, visit_date_us, visit_type)
    """
    db_path = tmp_path / "places.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE moz_places (
            id INTEGER PRIMARY KEY,
            url TEXT, title TEXT, visit_count INTEGER DEFAULT 0,
            description TEXT, site_name TEXT, hidden INTEGER DEFAULT 0,
            rev_host TEXT, typed INTEGER DEFAULT 0, frecency INTEGER DEFAULT -1,
            last_visit_date INTEGER, guid TEXT, foreign_count INTEGER DEFAULT 0,
            url_hash INTEGER DEFAULT 0, preview_image_url TEXT, origin_id INTEGER,
            recalc_frecency INTEGER DEFAULT 0, alt_frecency INTEGER,
            recalc_alt_frecency INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE moz_historyvisits (
            id INTEGER PRIMARY KEY,
            from_visit INTEGER, place_id INTEGER, visit_date INTEGER,
            visit_type INTEGER, session INTEGER DEFAULT 0,
            source INTEGER DEFAULT 0, triggeringPlaceId INTEGER
        )
    """)
    for i, (url, title, visit_date_us, visit_type) in enumerate(visits, 1):
        conn.execute(
            "INSERT INTO moz_places (id, url, title, visit_count) VALUES (?, ?, ?, 1)",
            (i, url, title),
        )
        conn.execute(
            "INSERT INTO moz_historyvisits (place_id, visit_date, visit_type) VALUES (?, ?, ?)",
            (i, visit_date_us, visit_type),
        )
    conn.commit()
    conn.close()
    return str(db_path)


def _ts_to_us(year, month, day, hour=12, minute=0) -> int:
    """Convert to Firefox microsecond timestamp."""
    dt = datetime(year, month, day, hour, minute, tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000)


class TestBrowserCollector:
    def test_source_name(self, tmp_path):
        config = BrowserCollectorConfig(enabled=True, places_path=str(tmp_path / "x.sqlite"))
        collector = BrowserCollector(config)
        assert collector.source_name() == "browser"

    def test_is_cheap(self, tmp_path):
        config = BrowserCollectorConfig(enabled=True, places_path=str(tmp_path / "x.sqlite"))
        assert BrowserCollector(config).is_cheap() is True

    def test_collects_visits_for_date(self, tmp_path):
        db = _create_test_db(
            tmp_path,
            [
                ("https://github.com/user/repo", "My Repo", _ts_to_us(2026, 2, 5, 9, 0), 1),
                (
                    "https://stackoverflow.com/q/123",
                    "Python question",
                    _ts_to_us(2026, 2, 5, 10, 0),
                    1,
                ),
                ("https://google.com/search?q=test", "Google", _ts_to_us(2026, 2, 6, 8, 0), 2),
            ],
        )
        config = BrowserCollectorConfig(enabled=True, places_path=db)
        collector = BrowserCollector(config)

        dr = DateRange.for_date(date(2026, 2, 5))
        events = collector.collect(dr)
        assert len(events) == 2
        assert events[0].raw_data["url"] == "https://github.com/user/repo"
        assert events[1].raw_data["url"] == "https://stackoverflow.com/q/123"

    def test_filters_by_visit_type(self, tmp_path):
        """Only visit types 1, 2, 3 should be collected."""
        db = _create_test_db(
            tmp_path,
            [
                ("https://example.com/page", "Page", _ts_to_us(2026, 2, 5, 9, 0), 1),  # link click
                ("https://example.com/typed", "Typed", _ts_to_us(2026, 2, 5, 9, 5), 2),  # typed
                (
                    "https://example.com/redir",
                    "Redirect",
                    _ts_to_us(2026, 2, 5, 9, 10),
                    6,
                ),  # redirect
                (
                    "https://example.com/perm",
                    "PermRedir",
                    _ts_to_us(2026, 2, 5, 9, 15),
                    5,
                ),  # perm redir
            ],
        )
        config = BrowserCollectorConfig(enabled=True, places_path=db)
        collector = BrowserCollector(config)

        dr = DateRange.for_date(date(2026, 2, 5))
        events = collector.collect(dr)
        assert len(events) == 2  # only types 1 and 2

    def test_skips_internal_urls(self, tmp_path):
        db = _create_test_db(
            tmp_path,
            [
                ("about:preferences", "Settings", _ts_to_us(2026, 2, 5, 9, 0), 1),
                ("moz-extension://abc/popup.html", "Extension", _ts_to_us(2026, 2, 5, 9, 5), 1),
                ("https://real-site.com", "Real Site", _ts_to_us(2026, 2, 5, 9, 10), 1),
            ],
        )
        config = BrowserCollectorConfig(enabled=True, places_path=db)
        collector = BrowserCollector(config)

        dr = DateRange.for_date(date(2026, 2, 5))
        events = collector.collect(dr)
        assert len(events) == 1
        assert events[0].raw_data["domain"] == "real-site.com"

    def test_missing_db(self, tmp_path):
        config = BrowserCollectorConfig(
            enabled=True, places_path=str(tmp_path / "nonexistent.sqlite")
        )
        collector = BrowserCollector(config)
        events = collector.collect(DateRange.for_date(date(2026, 2, 5)))
        assert events == []

    def test_event_timestamp_set(self, tmp_path):
        db = _create_test_db(
            tmp_path,
            [
                ("https://example.com", "Test", _ts_to_us(2026, 2, 5, 14, 30), 1),
            ],
        )
        config = BrowserCollectorConfig(enabled=True, places_path=db)
        collector = BrowserCollector(config)

        events = collector.collect(DateRange.for_date(date(2026, 2, 5)))
        assert len(events) == 1
        assert events[0].event_timestamp is not None
        assert events[0].event_timestamp.hour == 14
        assert events[0].event_timestamp.minute == 30

    def test_extracts_domain(self, tmp_path):
        db = _create_test_db(
            tmp_path,
            [
                (
                    "https://docs.python.org/3/library/sqlite3.html",
                    "sqlite3",
                    _ts_to_us(2026, 2, 5, 9, 0),
                    1,
                ),
            ],
        )
        config = BrowserCollectorConfig(enabled=True, places_path=db)
        collector = BrowserCollector(config)

        events = collector.collect(DateRange.for_date(date(2026, 2, 5)))
        assert events[0].raw_data["domain"] == "docs.python.org"


class TestBrowserTransformer:
    def test_github_is_development(self):
        from timeline.config import TimelineConfig

        t = Transformer(TimelineConfig())
        raw = _make_raw_browser("https://github.com/user/repo", "My Repo", "github.com")
        event = t.transform([raw])[0]
        assert event.category == "development"

    def test_stackoverflow_is_development(self):
        from timeline.config import TimelineConfig

        t = Transformer(TimelineConfig())
        raw = _make_raw_browser(
            "https://stackoverflow.com/q/123", "Python question", "stackoverflow.com"
        )
        event = t.transform([raw])[0]
        assert event.category == "development"

    def test_docs_is_reference(self):
        from timeline.config import TimelineConfig

        t = Transformer(TimelineConfig())
        raw = _make_raw_browser(
            "https://docs.python.org/3/library/", "Python Docs", "docs.python.org"
        )
        event = t.transform([raw])[0]
        assert event.category == "reference"

    def test_teams_is_communication(self):
        from timeline.config import TimelineConfig

        t = Transformer(TimelineConfig())
        raw = _make_raw_browser(
            "https://teams.microsoft.com/chat", "Teams Chat", "teams.microsoft.com"
        )
        event = t.transform([raw])[0]
        assert event.category == "communication"

    def test_claude_is_ai(self):
        from timeline.config import TimelineConfig

        t = Transformer(TimelineConfig())
        raw = _make_raw_browser("https://claude.ai/chat/abc", "Claude", "claude.ai")
        event = t.transform([raw])[0]
        assert event.category == "ai"

    def test_sharepoint_is_documents(self):
        from timeline.config import TimelineConfig

        t = Transformer(TimelineConfig())
        raw = _make_raw_browser(
            "https://company.sharepoint.com/doc", "Doc", "company.sharepoint.com"
        )
        event = t.transform([raw])[0]
        assert event.category == "documents"

    def test_unknown_domain_is_browsing(self):
        from timeline.config import TimelineConfig

        t = Transformer(TimelineConfig())
        raw = _make_raw_browser("https://random-site.com/page", "Random", "random-site.com")
        event = t.transform([raw])[0]
        assert event.category == "browsing"

    def test_description_uses_title(self):
        from timeline.config import TimelineConfig

        t = Transformer(TimelineConfig())
        raw = _make_raw_browser("https://example.com", "My Page Title", "example.com")
        event = t.transform([raw])[0]
        assert event.description == "My Page Title"

    def test_description_falls_back_to_domain(self):
        from timeline.config import TimelineConfig

        t = Transformer(TimelineConfig())
        raw = _make_raw_browser("https://example.com", "", "example.com")
        event = t.transform([raw])[0]
        assert event.description == "example.com"

    def test_skip_domains_config(self):
        from timeline.config import BrowserCollectorConfig, TimelineConfig

        config = TimelineConfig(
            browser=BrowserCollectorConfig(enabled=True, skip_domains=["ads.example.com"]),
        )
        t = Transformer(config)
        raw = _make_raw_browser("https://ads.example.com/track", "Ad", "ads.example.com")
        events = t.transform([raw])
        assert len(events) == 0


def _make_raw_browser(url: str, title: str, domain: str) -> RawEvent:
    return RawEvent(
        source="browser",
        collected_at=datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
        raw_data={
            "url": url,
            "title": title,
            "domain": domain,
            "visit_type": 1,
            "visit_count": 1,
            "description": "",
            "site_name": "",
            "timestamp": "2026-02-06T09:00:00+00:00",
        },
        event_timestamp=datetime(2026, 2, 6, 9, 0, tzinfo=UTC),
    )
