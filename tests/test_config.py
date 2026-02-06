"""Tests for configuration loading."""

from pathlib import Path

import pytest

from timeline.config import TimelineConfig, generate_config_toml


class TestConfigLoad:
    def test_load_missing_file(self):
        with pytest.raises(FileNotFoundError, match="Run 'timeline init'"):
            TimelineConfig.load(Path("/nonexistent/config.toml"))

    def test_load_valid_toml(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text("""
[general]
db_path = "~/.timeline/test.db"
timezone = ""
lunch_boundary = "12:00"

[general.work_hours]
start = "08:00"
end = "17:00"

[projects.mapping]
"customer-api" = "Customer Platform"

[collectors.git]
enabled = true
authors = [
    { email = "bjorn@test.com" },
]
repos = [
    "C:\\\\Dev\\\\my-repo",
]

[exporters.stdout]
enabled = true
group_by = "flat"

[summarizer]
enabled = false
command = ""
""")
        config = TimelineConfig.load(config_path)
        assert config.git.enabled is True
        assert len(config.git.authors) == 1
        assert config.git.authors[0].email == "bjorn@test.com"
        assert len(config.git.repos) == 1
        assert config.project_mapping["customer-api"] == "Customer Platform"
        assert config.lunch_boundary == "12:00"

    def test_generate_roundtrip(self, tmp_path):
        """Generate TOML from config, write it, read it back."""
        config = TimelineConfig(
            db_path=tmp_path / "test.db",
            lunch_boundary="11:30",
        )
        toml_str = generate_config_toml(config)
        config_path = tmp_path / "config.toml"
        config_path.write_text(toml_str)

        loaded = TimelineConfig.load(config_path)
        assert loaded.lunch_boundary == "11:30"
