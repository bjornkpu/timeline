"""Configuration loading and interactive bootstrapping."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import UTC, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_CONFIG_DIR = Path.home() / ".timeline"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"
DEFAULT_DB_PATH = DEFAULT_CONFIG_DIR / "timeline.db"


@dataclass
class GitAuthor:
    email: str
    name: str | None = None


@dataclass
class GitCollectorConfig:
    enabled: bool = True
    authors: list[GitAuthor] = field(default_factory=list)
    repos: list[str] = field(default_factory=list)


DEFAULT_SHELL_HISTORY_PATH = DEFAULT_CONFIG_DIR / "shell_history.jsonl"


@dataclass
class BrowserCollectorConfig:
    enabled: bool = False
    places_path: str = ""  # path to places.sqlite
    skip_domains: list[str] = field(default_factory=list)
    # domain substring → project name
    domain_mapping: dict[str, str] = field(default_factory=dict)


@dataclass
class ShellCollectorConfig:
    enabled: bool = False
    history_path: str = str(DEFAULT_SHELL_HISTORY_PATH)


@dataclass
class StdoutExporterConfig:
    enabled: bool = True
    group_by: str = "flat"  # "flat", "hour", "period"


@dataclass
class SummarizerConfig:
    enabled: bool = False
    model: str = ""  # empty = use default subscription model


@dataclass
class TimelineConfig:
    db_path: Path = DEFAULT_DB_PATH
    timezone: tzinfo = field(default_factory=lambda: _system_timezone())
    work_hours_start: str = "08:00"
    work_hours_end: str = "17:00"
    lunch_boundary: str = "12:00"
    project_mapping: dict[str, str] = field(default_factory=dict)
    git: GitCollectorConfig = field(default_factory=GitCollectorConfig)
    shell: ShellCollectorConfig = field(default_factory=ShellCollectorConfig)
    browser: BrowserCollectorConfig = field(default_factory=BrowserCollectorConfig)
    stdout: StdoutExporterConfig = field(default_factory=StdoutExporterConfig)
    summarizer: SummarizerConfig = field(default_factory=SummarizerConfig)

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> TimelineConfig:
        """Load config from TOML file."""
        if not path.exists():
            msg = f"Config not found at {path}. Run 'timeline init' to create one."
            raise FileNotFoundError(msg)

        with open(path, "rb") as f:
            data = tomllib.load(f)

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> TimelineConfig:
        general = data.get("general", {})
        projects = data.get("projects", {})
        git_data = data.get("collectors", {}).get("git", {})
        shell_data = data.get("collectors", {}).get("shell", {})
        browser_data = data.get("collectors", {}).get("browser", {})
        stdout_data = data.get("exporters", {}).get("stdout", {})
        summarizer_data = data.get("summarizer", {})

        tz_str = general.get("timezone", "")
        tz = ZoneInfo(tz_str) if tz_str else _system_timezone()

        db_path_str = general.get("db_path", str(DEFAULT_DB_PATH))
        db_path = Path(db_path_str).expanduser()

        authors = [
            GitAuthor(email=a["email"], name=a.get("name")) for a in git_data.get("authors", [])
        ]

        return cls(
            db_path=db_path,
            timezone=tz,
            work_hours_start=general.get("work_hours", {}).get("start", "08:00"),
            work_hours_end=general.get("work_hours", {}).get("end", "17:00"),
            lunch_boundary=general.get("lunch_boundary", "12:00"),
            project_mapping=projects.get("mapping", {}),
            git=GitCollectorConfig(
                enabled=git_data.get("enabled", True),
                authors=authors,
                repos=git_data.get("repos", []),
            ),
            shell=ShellCollectorConfig(
                enabled=shell_data.get("enabled", False),
                history_path=shell_data.get("history_path", str(DEFAULT_SHELL_HISTORY_PATH)),
            ),
            browser=BrowserCollectorConfig(
                enabled=browser_data.get("enabled", False),
                places_path=browser_data.get("places_path", ""),
                skip_domains=browser_data.get("skip_domains", []),
                domain_mapping=browser_data.get("domain_mapping", {}),
            ),
            stdout=StdoutExporterConfig(
                enabled=stdout_data.get("enabled", True),
                group_by=stdout_data.get("group_by", "flat"),
            ),
            summarizer=SummarizerConfig(
                enabled=summarizer_data.get("enabled", False),
                model=summarizer_data.get("model", ""),
            ),
        )


def _system_timezone() -> tzinfo:
    """Detect system timezone."""
    from datetime import datetime

    local_tz = datetime.now(UTC).astimezone().tzinfo
    return local_tz if local_tz is not None else UTC


def _format_domain_mapping(mapping: dict[str, str]) -> str:
    """Format domain_mapping as TOML key-value pairs."""
    lines = []
    for k, v in mapping.items():
        lines.append(f'"{k}" = "{v}"')
    return "\n".join(lines)


def generate_config_toml(config: TimelineConfig) -> str:
    """Generate TOML string from config for writing to file."""
    tz_name = ""
    if isinstance(config.timezone, ZoneInfo):
        tz_name = str(config.timezone)

    authors_toml = ""
    for author in config.git.authors:
        if author.name:
            authors_toml += f'    {{ email = "{author.email}", name = "{author.name}" }},\n'
        else:
            authors_toml += f'    {{ email = "{author.email}" }},\n'

    repos_toml = ""
    for repo in config.git.repos:
        # Escape backslashes for TOML
        escaped = repo.replace("\\", "\\\\")
        repos_toml += f'    "{escaped}",\n'

    mapping_toml = ""
    for key, value in config.project_mapping.items():
        escaped_key = key.replace("\\", "\\\\")
        mapping_toml += f'"{escaped_key}" = "{value}"\n'

    return f"""[general]
db_path = "{str(config.db_path).replace(chr(92), chr(92) * 2)}"
timezone = "{tz_name}"
lunch_boundary = "{config.lunch_boundary}"

[general.work_hours]
start = "{config.work_hours_start}"
end = "{config.work_hours_end}"

[projects]
default_from = "repo_name"

[projects.mapping]
{mapping_toml}
[collectors.git]
enabled = {str(config.git.enabled).lower()}
authors = [
{authors_toml}]
repos = [
{repos_toml}]

[collectors.shell]
enabled = {str(config.shell.enabled).lower()}
history_path = "{str(config.shell.history_path).replace(chr(92), chr(92) * 2)}"

[collectors.browser]
enabled = {str(config.browser.enabled).lower()}
places_path = "{str(config.browser.places_path).replace(chr(92), chr(92) * 2)}"
skip_domains = [{", ".join(f'"{d}"' for d in config.browser.skip_domains)}]

[collectors.browser.domain_mapping]
{_format_domain_mapping(config.browser.domain_mapping)}

[exporters.stdout]
enabled = {str(config.stdout.enabled).lower()}
group_by = "{config.stdout.group_by}"

[summarizer]
enabled = {str(config.summarizer.enabled).lower()}
model = "{config.summarizer.model}"
"""


def interactive_init(config_path: Path = DEFAULT_CONFIG_PATH) -> TimelineConfig:
    """Interactively create a config file."""
    import click

    click.echo("Timeline Configuration")
    click.echo("=" * 40)
    click.echo()

    # General
    db_path = click.prompt(
        "Storage path",
        default=str(DEFAULT_DB_PATH),
    )

    sys_tz = _system_timezone()
    tz_name = str(sys_tz) if isinstance(sys_tz, ZoneInfo) else ""
    tz_input = click.prompt(
        "Timezone (blank for system default)",
        default=tz_name,
    )
    tz = ZoneInfo(tz_input) if tz_input else sys_tz

    work_start = click.prompt("Workday start", default="08:00")
    work_end = click.prompt("Workday end", default="17:00")
    lunch = click.prompt("Lunch boundary", default="12:00")

    click.echo()

    # Git collector
    click.echo("Git Collector")
    click.echo("-" * 20)
    git_enabled = click.confirm("Enable git collector?", default=True)

    authors: list[GitAuthor] = []
    repos: list[str] = []
    if git_enabled:
        emails_str = click.prompt(
            "Git author emails (comma-separated)",
            default="",
        )
        if emails_str:
            authors = [GitAuthor(email=e.strip()) for e in emails_str.split(",") if e.strip()]

        repos_str = click.prompt(
            "Repo paths (comma-separated)",
            default="",
        )
        if repos_str:
            repos = [r.strip() for r in repos_str.split(",") if r.strip()]

    click.echo()

    # Project mapping
    mapping: dict[str, str] = {}
    if click.confirm("Configure project name mappings?", default=False):
        click.echo("Enter mappings as 'repo-substring = Display Name' (blank line to finish)")
        while True:
            entry = click.prompt("Mapping", default="")
            if not entry:
                break
            if "=" in entry:
                key, value = entry.split("=", 1)
                mapping[key.strip()] = value.strip()

    config = TimelineConfig(
        db_path=Path(db_path).expanduser(),
        timezone=tz,
        work_hours_start=work_start,
        work_hours_end=work_end,
        lunch_boundary=lunch,
        project_mapping=mapping,
        git=GitCollectorConfig(
            enabled=git_enabled,
            authors=authors,
            repos=repos,
        ),
    )

    # Write config
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(generate_config_toml(config))
    click.echo(f"\nConfig written to {config_path}")

    # Ensure DB directory exists
    config.db_path.parent.mkdir(parents=True, exist_ok=True)

    return config
