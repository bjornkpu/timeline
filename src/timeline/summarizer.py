"""LLM summarizer — generates daily summaries via Claude Code CLI."""

from __future__ import annotations

import subprocess

import click

from timeline.config import TimelineConfig
from timeline.models import DateRange, PeriodType, Summary, TimelineEvent

SYSTEM_PROMPT = (
    "You are a concise developer productivity assistant analyzing daily activity timelines. "
    "Your task: synthesize developer activity into a brief, coherent daily summary that maintains "
    "continuity with previous days.\n\n"
    "Focus on:\n"
    "- Concrete accomplishments (code written, PRs merged, features shipped, bugs fixed)\n"
    "- Active projects and how work is progressing across days\n"
    "- Significant meetings or collaboration events\n"
    "- Notable workflow patterns or context switches\n"
    "- Connection to previous day's work when applicable\n\n"
    "Downweight:\n"
    "- Generic browser activity unless clearly productive (docs, Stack Overflow, research)\n"
    "- Routine shell commands unless part of meaningful deployment/debugging\n"
    "- Meeting attendance without context (but note if recurring or significant)\n\n"
    "Output: 3-5 concise sentences forming a narrative paragraph. "
    "No bullet points, no headers. Write as if you're maintaining a developer's logbook."
)

WEEKLY_SYSTEM_PROMPT = (
    "You are a developer productivity assistant synthesizing weekly activity. "
    "Your task: create a coherent weekly narrative from daily summaries that captures "
    "progress, patterns, and momentum across the week.\n\n"
    "Focus on:\n"
    "- Major accomplishments and shipped work\n"
    "- Key projects and how they evolved through the week\n"
    "- Productivity patterns (deep work days, meeting-heavy days, context switches)\n"
    "- Notable momentum shifts or pivots from previous week\n"
    "- Team collaboration and cross-project work\n"
    "- Emerging trends or recurring themes\n\n"
    "Distill:\n"
    "- What got done (outcomes, not just activities)\n"
    "- Where focus was concentrated\n"
    "- How work is progressing relative to previous periods\n\n"
    "Output: 5-8 sentences forming a cohesive narrative. "
    "No bullet points, no headers. Write as a weekly developer log entry that provides "
    "both detail and strategic perspective."
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
        previous_summary: Summary | None = None,
    ) -> Summary | None:
        """Generate a summary for the given events via Claude Code CLI."""
        if not self._config.summarizer.enabled:
            return None

        if not events:
            return None

        model = self._config.summarizer.model
        event_text = _format_events(events, self._config)

        prompt_parts = []

        # Include previous day's summary for continuity
        if previous_summary:
            prev_date = previous_summary.date_start.isoformat()
            prompt_parts.append(f"Previous day ({prev_date}):\n{previous_summary.summary}\n")

        prompt_parts.append(
            f"Activity timeline for {date_range.start.isoformat()}"
            f" ({len(events)} events):\n\n{event_text}"
        )

        prompt = "\n".join(prompt_parts)

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

    def summarize_week(
        self,
        daily_summaries: list[Summary],
        date_range: DateRange,
        previous_week_summary: Summary | None = None,
    ) -> Summary | None:
        """Generate weekly summary from daily summaries via Claude CLI."""
        if not self._config.summarizer.enabled:
            return None

        if not daily_summaries:
            return None

        model = self._config.summarizer.model

        prompt_parts = []

        # Include previous week's summary for continuity
        if previous_week_summary:
            prev_year, prev_week, _ = previous_week_summary.date_start.isocalendar()
            prompt_parts.append(
                f"Previous week ({prev_year}-W{prev_week:02d}):\n{previous_week_summary.summary}\n"
            )

        lines = []
        for summary in daily_summaries:
            day_name = summary.date_start.strftime("%A")
            lines.append(f"{day_name} ({summary.date_start.isoformat()}): {summary.summary}")

        summaries_text = "\n\n".join(lines)
        year, week_num, _ = date_range.start.isocalendar()
        prompt_parts.append(
            f"Weekly summaries for {year}-W{week_num:02d} "
            f"({date_range.start.isoformat()} to {date_range.end.isoformat()}):\n\n"
            f"{summaries_text}"
        )

        prompt = "\n".join(prompt_parts)

        try:
            summary_text = _run_claude(prompt, WEEKLY_SYSTEM_PROMPT, model)
        except (subprocess.TimeoutExpired, RuntimeError, FileNotFoundError) as exc:
            click.echo(f"  [summarizer] Error: {exc}")
            return None

        if not summary_text:
            click.echo("  [summarizer] Empty response from claude CLI")
            return None

        return Summary(
            date_start=date_range.start,
            date_end=date_range.end,
            period_type=PeriodType.WEEK,
            summary=summary_text,
            model=model,
        )
