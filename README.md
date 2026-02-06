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

## Usage

```bash
uv run timeline run today             # full pipeline for today
uv run timeline run yesterday --quick # skip LLM summarization
uv run timeline show today            # display stored timeline
uv run timeline backfill 2026-01-01   # load historical data
uv run timeline reset                 # wipe DB and start fresh
```

Key flags: `--quick` (skip LLM), `--refresh` (force re-collect API sources), `--group-by {flat,hour,period}`.

## Development

```bash
uv run pytest                          # run tests
uv run ruff check src/ tests/          # lint
uv run ruff format src/ tests/         # format
```

Python 3.13+. Ruff for linting/formatting. Config: `~/.timeline/config.toml`, DB: `~/.timeline/timeline.db`.
