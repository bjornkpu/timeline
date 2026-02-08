"""Configuration validation for Timeline."""

from __future__ import annotations

from dataclasses import dataclass

from timeline.config.models import TimelineConfig


@dataclass(frozen=True)
class ValidationError:
    """A configuration validation error."""

    path: str
    message: str


class ConfigValidator:
    """Validate TimelineConfig dataclass against schema."""

    def validate(self, config: TimelineConfig) -> list[ValidationError]:
        """Validate config, return list of errors (empty if valid)."""
        errors: list[ValidationError] = []

        # Validate collectors config objects exist
        if config.git is None:
            errors.append(ValidationError("collectors.git", "Git config is None"))

        if config.shell is None:
            errors.append(ValidationError("collectors.shell", "Shell config is None"))

        if config.browser is None:
            errors.append(ValidationError("collectors.browser", "Browser config is None"))

        if config.windows_events is None:
            errors.append(
                ValidationError("collectors.windows_events", "Windows events config is None")
            )

        if config.calendar is None:
            errors.append(ValidationError("collectors.calendar", "Calendar config is None"))

        if config.calendar and config.calendar.enabled:
            # Calendar collector uses COM/MAPI, no email validation needed
            pass

        # Validate project mapping
        for pattern, name in config.project_mapping.items():
            if not isinstance(pattern, str):
                errors.append(
                    ValidationError(
                        "projects.mapping",
                        f"Mapping key {pattern!r} is not a string",
                    )
                )
            if not isinstance(name, str):
                errors.append(
                    ValidationError(
                        f"projects.mapping.{pattern}",
                        f"Mapping value {name!r} is not a string",
                    )
                )

        # Validate git authors
        if config.git:
            for i, author in enumerate(config.git.authors):
                if not author.email:
                    errors.append(
                        ValidationError(
                            f"collectors.git.authors[{i}]",
                            "Author email is required",
                        )
                    )

        # Validate browser skip_domains
        if config.browser:
            for i, domain in enumerate(config.browser.skip_domains):
                if not isinstance(domain, str):
                    errors.append(
                        ValidationError(
                            f"collectors.browser.skip_domains[{i}]",
                            f"Domain {domain!r} is not a string",
                        )
                    )

        # Validate work hours format (simple check)
        for time_str, field_name in [
            (config.work_hours_start, "work_hours_start"),
            (config.work_hours_end, "work_hours_end"),
            (config.lunch_boundary, "lunch_boundary"),
        ]:
            if not _is_valid_time(time_str):
                config_field = (
                    "lunch_boundary"
                    if "boundary" in field_name
                    else f"work_hours_{field_name.split('_')[-1]}"
                )
                errors.append(
                    ValidationError(
                        f"general.{config_field}",
                        f"Invalid time format: {time_str!r} (expected HH:MM)",
                    )
                )

        return errors


def _is_valid_time(time_str: str) -> bool:
    """Check if time string is in valid HH:MM format."""
    if not isinstance(time_str, str):
        return False
    parts = time_str.split(":")
    if len(parts) != 2:
        return False
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        return 0 <= hour < 24 and 0 <= minute < 60
    except ValueError:
        return False
