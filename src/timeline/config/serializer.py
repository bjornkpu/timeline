"""TOML serialization for Timeline configuration."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from timeline.config.models import TimelineConfig


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

[collectors.windows_events]
enabled = {str(config.windows_events.enabled).lower()}

[exporters.stdout]
enabled = {str(config.stdout.enabled).lower()}
group_by = "{config.stdout.group_by}"

[summarizer]
enabled = {str(config.summarizer.enabled).lower()}
model = "{config.summarizer.model}"
"""
