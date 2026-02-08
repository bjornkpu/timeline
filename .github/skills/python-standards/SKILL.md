---
name: python-standards
description: Detailed Python coding standards (load only when needed)
model: haiku
---

# Python Development Standards

## Tooling

- **uv** for dependency management (no pip/poetry)
- **ruff** for linting and formatting (no black/isort/flake8)
- **ty** for type checking
- **pytest** for testing

## Python Style

### Type Hints (Always)

```python
def create_event(user_id: str, event_type: str) -> Event:
    ...

class EventRepository(Protocol):
    def save(self, event: Event) -> None: ...
```

**Prefer Protocol over ABC** for defining interfaces - it's more flexible and follows structural subtyping.

### Data Structures

- **Dataclasses** for simple data containers - prefer `frozen=True` for immutability and use `dataclasses.replace` for updates
- **Pydantic models** for validation and serialization (API boundaries)
- Never use dicts for structured data

```python
from dataclasses import dataclass, replace

@dataclass(frozen=True)
class Event:
    user_id: str
    event_type: str

# Update using replace
updated_event = replace(event, event_type="new_type")
```

### Optimizations

- Use `functools.cache` for pure functions with expensive computations and limited input space
- Consider `functools.lru_cache` when you need to limit memory usage

```python
from functools import cache

@cache
def get_config(env: str) -> dict:
    # Expensive config loading
    return load_config(env)
```

### Async/Await

- Use async for all I/O operations (DB, HTTP, file)

### File Paths

- Always use `pathlib.Path` instead of string manipulation for file paths
- More readable, cross-platform, and has useful methods

```python
from pathlib import Path

config_dir = Path("config") / "settings"
if config_dir.exists():
    files = list(config_dir.glob("*.yaml"))
```

### Error Handling

- Use `contextlib.suppress` when you expect and intentionally ignore specific exceptions
- Makes intent explicit rather than empty except blocks

```python
from contextlib import suppress

with suppress(FileNotFoundError):
    Path("temp.txt").unlink()
```

### Pattern Matching

- Use `match` with guards for complex conditional logic when it improves readability
- Particularly useful for parsing or handling multiple data shapes

```python
match event:
    case {"type": "user_login", "user_id": uid} if uid.startswith("admin"):
        handle_admin_login(uid)
    case {"type": "user_login", "user_id": uid}:
        handle_user_login(uid)
    case {"type": "error", "code": code}:
        handle_error(code)
```

## Code Organization

### Key Principles

- **Separate concerns:** Keep business logic out of API endpoints
- **Keep it simple:** Don't over-engineer, add layers only when needed

## Testing Standards

Only write happy path tests and minimal amount of code to get the job done unless instructed differently.

### AAA Pattern (Arrange-Act-Assert)

```python
def test_should_create_event_when_valid_data() -> None:
    # Arrange
    repo = Mock(spec=EventRepository)
    service = EventService(repo)

    # Act
    result = service.create_event("user1", "coffee")

    # Assert
    assert result.user_id == "user1"
    repo.save.assert_called_once()
```

### Naming Convention

- `test_should_<expected>_when_<condition>`
- Descriptive, not terse

## Anti-Patterns to Avoid

❌ God classes (class doing too much)
❌ Circular dependencies
❌ Mutable default arguments `def func(items=[])`
❌ Bare except clauses `except:`
❌ Global state
❌ Business logic in presentation layer
❌ Using `Any` for type hints unless necessary
❌ Mixing async and sync code incorrectly
