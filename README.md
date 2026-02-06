# Timeline

Local-first daily activity timeline aggregator for developers. Collects data from git, shell history, and browser activity, normalizes it into timeline events, and optionally generates LLM summaries.

## Architecture

Three-layer pipeline: **raw** (collector output) → **events** (normalized) → **summaries** (LLM-derived). All data stored in local SQLite.

**Collectors:** git log/reflog, PSReadLine shell history (JSONL), Firefox/Zen browser history.
**Exporters:** colored terminal output.

## Setup

```bash
uv sync
uv run timeline init          # create ~/.timeline/config.toml
```

### Global install (optional)

Install as a global tool so `timeline` works from any directory:

```bash
uv tool install -e .          # run from project root; editable so source changes apply immediately
```

Uninstall with `uv tool uninstall timeline`.

## Usage

After global install, drop the `uv run` prefix:

```bash
timeline run today             # full pipeline for today
timeline run yesterday --quick # skip LLM summarization
timeline show today            # display stored timeline
timeline backfill 2026-01-01   # load historical data
timeline reset                 # wipe DB and start fresh
```

Or run from the project directory without global install:

```bash
uv run timeline run today
uv run timeline show today
```

Key flags: `--quick` (skip LLM), `--refresh` (force re-collect API sources), `--group-by {flat,hour,period}`.

## Development

```bash
uv run pytest                          # run tests
uv run ruff check src/ tests/          # lint
uv run ruff format src/ tests/         # format
```

Python 3.13+. Ruff for linting/formatting. Config: `~/.timeline/config.toml`, DB: `~/.timeline/timeline.db`.
