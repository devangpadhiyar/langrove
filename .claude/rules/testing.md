---
description: pytest conventions, fixtures, test patterns, and CI commands
globs:
  - "tests/**/*.py"
---

# Testing

## Framework
- `pytest` + `pytest-asyncio` for all async tests
- Dev dependencies: `httpx` (test client), `testcontainers[postgres,redis]`

## Fixtures (conftest.py)
- `fixtures_dir` → `Path(__file__).parent / "fixtures"` — test data directory
- `test_config_path` → path to test `langgraph.json`
- Path objects from fixtures — convert with `str()` when passing to functions expecting strings

## Test Patterns
- **Auth tests:** create temp handler files with `tmp_path.write_text()`, test module loading
- **SSE formatter tests:** verify exact wire format (event names, JSON encoding, blank line separators, null data)
- **Config tests:** valid/invalid JSON, missing files (returns defaults), type validation, CORS parsing
- **Graph registry tests:** loading from config, NotFoundError for missing graphs, schema extraction

## Conventions
- No mocking of database when possible — use real postgres via testcontainers
- Full stream sequence tests: metadata → events → end
- Test both success and error paths for every endpoint

## Commands
```bash
uv run pytest --tb=short -q          # Quick feedback
uv run pytest tests/test_runs.py     # Specific file
uv run pytest -x -v                  # Stop on first failure, verbose
uv run ruff check .                  # Lint
uv run ruff format .                 # Format
uv run ruff check . && uv run ruff format . && uv run pytest  # Full pre-commit check
```
