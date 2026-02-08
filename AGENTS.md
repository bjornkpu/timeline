# AGENTS.md — Timeline

Local-first daily activity timeline aggregator for developers.
Python 3.13+, uv, ruff, pytest, click.

Do not use git add/commit/push commands without my permission.

## Build & Run

```bash
uv sync                          # install deps
uv run timeline --help           # CLI help
uv run timeline run today        # full pipeline for today
uv run timeline reset            # wipe DB and start fresh
```

## Test Commands

```bash
uv run pytest                              # all tests
uv run pytest -v                           # verbose
uv run pytest tests/test_store.py          # single file
uv run pytest tests/test_store.py::TestEventStorage::test_idempotent_insert  # single test
uv run pytest -k "categoriz"               # match test name pattern
uv run pytest --tb=short                   # short tracebacks
```

## Lint & Format

```bash
uv run ruff check src/ tests/             # lint
uv run ruff check --fix src/ tests/       # auto-fix
uv run ruff format src/ tests/            # format
uv run ruff format --check src/ tests/    # check formatting
```

Ruff config: line-length 100, target py313.
Rules: E, F, W, I (isort), N (naming), UP (pyupgrade), B (bugbear), A (builtins), SIM (simplify).

## Architecture

Three-layer pipeline: **raw** (collector output) -> **events** (normalized) -> **summaries** (LLM-derived).

```txt
src/timeline/
  cli.py              # click CLI entry point
  config/
    __init__.py       # public API re-export
    models.py         # dataclass configs: GitCollectorConfig, BrowserCollectorConfig, etc.
    loader.py         # load_config() — TOML read + validation
    serializer.py     # generate_config_toml() — TOML write
    validation.py     # ConfigValidator — schema validation (hard failures)
  models.py           # RawEvent, TimelineEvent, Summary, DateRange
  store.py            # SQLite storage (raw_events, events, summaries tables)
  transformer/
    __init__.py       # public API re-export
    dispatcher.py     # Transformer orchestrator (dependency injection)
    categorizer.py    # registry-based rules: GitCommitCategorizer, ShellCommandCategorizer, BrowserDomainCategorizer
    parser.py         # source-specific parsing (git/shell/browser)
    projector.py      # ProjectMapper — project name mapping
    cleaner.py        # DescriptionCleaner — description normalization
  pipeline.py         # orchestrator: collect -> transform -> summarize -> export
  summarizer.py       # LLM integration (stub)
  collectors/
    base.py           # ABC: collect(date_range) -> list[RawEvent]
    git.py            # git log --all + reflog
    shell.py          # JSONL from PSReadLine hook
    browser.py        # Firefox/Zen places.sqlite
    windows_events.py # Windows Event Log collector
  exporters/
    base.py           # ABC: export(events, summary, date_range, config)
    stdout.py         # colored terminal output
```

## Code Style

### Imports

- `from __future__ import annotations` on every file
- Stdlib first, third-party second, local third (enforced by ruff isort)
- Always explicit named imports: `from timeline.models import DateRange, RawEvent`
- Absolute imports from package root: `from timeline.collectors.base import Collector`
- No star imports

### Types

- All function signatures fully typed with return types
- `str | None` not `Optional[str]` (PEP 604)
- `list[str]`, `dict[str, Any]`, `set[str]` (lowercase builtins, PEP 585)
- `collections.abc.Iterator`, `collections.abc.Sequence` for abstract types
- `Self` for classmethod return types
- `dict[str, Any]` for unstructured metadata blobs

### Naming

- **Classes**: `PascalCase` — `TimelineStore`, `GitCollector`, `DateRange`
- **Config dataclasses**: `<Thing>Config` — `GitCollectorConfig`, `BrowserCollectorConfig`
- **Functions/methods**: `snake_case`
- **Private**: `_` prefix — `self._config`, `_run_cmd()`, `_to_utc_iso()`
- **Constants**: `UPPER_SNAKE_CASE` at module level — `SCHEMA`, `COMMIT_SEP`
- **Enums**: `PeriodType(str, Enum)` with `UPPER_CASE` values
- **Test files**: `test_<module>.py`
- **Test helpers**: `_` prefix — `_make_raw_git()`, `_write_history()`

### Docstrings

- Module-level docstring on every file (one-line: `"""Description."""`)
- Method docstrings: concise single-line when needed, omit for obvious methods
- No `__all__` exports

### Error Handling

- Build `msg` string then raise: `msg = "..."; raise ValueError(msg)`
- `raise ... from None` to suppress exception chains in CLI
- `contextlib.suppress(KeyError, ValueError)` for expected failures
- Return `None` for unparseable data, let caller filter
- Silent failure for external commands (subprocess returns `""`)
- Narrow exception types: `json.JSONDecodeError`, `sqlite3.IntegrityError`
- Early return for missing resources: `if not path.exists(): return []`
- `try/finally` for resource cleanup: `pipeline.close()`

### Data Model

- **Dataclasses** only (no Pydantic/attrs)
- `frozen=True` for value objects (`DateRange`)
- Mutable dataclasses for entities (`RawEvent`, `TimelineEvent`)
- Idempotency via `event_hash` (SHA256) with `INSERT OR IGNORE`
- All timestamps stored as UTC in SQLite, displayed in local timezone

### Collectors

- Inherit from `Collector` ABC
- `is_cheap() -> bool`: `True` for local sources (git, shell, browser), `False` for APIs (toggl)
- Cheap collectors always re-scan; expensive ones use cached raw data
- `collect(date_range) -> list[RawEvent]` with `event_timestamp` set

### Transformer

- `Transformer` class in `dispatcher.py` accepts config + optional dependency overrides (for testing)
- `Parser` class handles source-specific parsing: `parse_git()`, `parse_shell()`, `parse_browser()`
- `GitCommitCategorizer`: cascading rules (conventional commit → file types → fallback)
- `ShellCommandCategorizer`: pre-sorted registry of matcher functions (`_is_vcs_command`, etc.)
- `BrowserDomainCategorizer`: pre-sorted registry of domain pattern matchers
- `ProjectMapper`: config-driven `[projects.mapping]`, fallback to repo name or cwd dir name
- `DescriptionCleaner`: strips conventional commit prefixes from descriptions
- **Registry pattern**: Each categorizer has pluggable rules; add new rule = add static method, no refactoring

## Testing Patterns

- In-memory SQLite via `store` fixture (`TimelineStore(":memory:")`)
- `tmp_path` for file-based tests (config, shell history, browser DB)
- Test classes group related tests: `TestCascadingCategorization`, `TestRawEventStorage`
- `setup_method` for per-class setup (not `__init__`)
- Plain `assert` statements, one behavior per test
- No mocking for store/transformer tests — test against real implementations
- `MagicMock` for collectors in pipeline tests (to verify caching/call behavior)
- Shared fixtures in `conftest.py`: `store`, `config`, `sample_raw_git_events`, `sample_timeline_events`
- Helper functions return realistic test data with all required fields

## Key Design Decisions

- Config lives at `~/.timeline/config.toml`, DB at `~/.timeline/timeline.db`
- `timeline reset` deletes DB during development (no migrations needed yet)
- `--refresh` flag forces re-collection of API sources
- `--quick` flag skips LLM summarization
- Browser collector copies `places.sqlite` to temp file to avoid Firefox lock
- Shell history uses PSReadLine hook writing JSONL to `~/.timeline/shell_history.jsonl`
