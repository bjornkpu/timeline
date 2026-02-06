"""LLM summarizer — generates daily summaries via Claude Code CLI."""

from __future__ import annotations

import subprocess

import click

from timeline.config import TimelineConfig
from timeline.models import DateRange, PeriodType, Summary, TimelineEvent

SYSTEM_PROMPT = (
    "You are a concise developer productivity assistant. "
    "Summarize the following developer activity timeline into a brief daily report. "
    "Focus on: what was accomplished, key projects worked on, and notable patterns. "
    "Keep it to 3-5 sentences. No bullet points, no headers — just a plain paragraph."
)


def _format_events(events: list[TimelineEvent], config: TimelineConfig) -> str:
    """Format events into a text block for the LLM prompt."""
    lines: list[str] = []
    for event in events:
        local_time = event.timestamp.astimezone(config.timezone)
        time_str = local_time.strftime("%H:%M")
        project = event.project or "unknown"
        parts = [
            time_str,
            f"[{event.source}]",
            f"({event.category})",
            f"{project}:",
            event.description,
        ]

        # Include git stats if present
        if event.source == "git":
            ins = event.metadata.get("insertions", 0)
            dels = event.metadata.get("deletions", 0)
            if ins or dels:
                parts.append(f"+{ins}/-{dels}")

        lines.append(" ".join(parts))

    return "\n".join(lines)


def _run_claude(prompt: str, system_prompt: str, model: str = "") -> str:
    """Run claude CLI in non-interactive mode, piping prompt via stdin."""
    cmd = [
        "claude",
        "-p",
        "--system-prompt",
        system_prompt,
        "--tools",
        "",
        "--no-session-persistence",
    ]
    if model:
        cmd.extend(["--model", model])
    result = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "(no output)"
        msg = f"claude CLI exited {result.returncode}: {detail}"
        raise RuntimeError(msg)
    return result.stdout.strip()


class Summarizer:
    def __init__(self, config: TimelineConfig) -> None:
        self._config = config

    def summarize(
        self,
        events: list[TimelineEvent],
        date_range: DateRange,
        period_type: PeriodType = PeriodType.DAY,
    ) -> Summary | None:
        """Generate a summary for the given events via Claude Code CLI."""
        if not self._config.summarizer.enabled:
            return None

        if not events:
            return None

        model = self._config.summarizer.model
        event_text = _format_events(events, self._config)
        prompt = (
            f"Activity timeline for {date_range.start.isoformat()}"
            f" ({len(events)} events):\n\n{event_text}"
        )

        try:
            summary_text = _run_claude(prompt, SYSTEM_PROMPT, model)
        except (subprocess.TimeoutExpired, RuntimeError, FileNotFoundError) as exc:
            click.echo(f"  [summarizer] Error: {exc}")
            return None

        if not summary_text:
            click.echo("  [summarizer] Empty response from claude CLI")
            return None

        return Summary(
            date_start=date_range.start,
            date_end=date_range.end,
            period_type=period_type,
            summary=summary_text,
            model=model,
        )
