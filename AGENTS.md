# Repository Guidelines

Always use context7 when I need code generation, setup or configuration steps, or
library/API documentation. This means you should automatically use the Context7 MCP
tools to resolve library id and get library docs without me having to explicitly ask.


## Project Structure & Module Organization


## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate` — create/activate the local virtual environment; run once per machine.
- `python -m pip install -r requirements.txt` — install runtime and tooling dependencies; regenerate the lock file when versions change.
- `python -m pytest` — execute the full automated test suite; use `-k` to focus on a subset during development.
- `ruff check src tests` and `ruff format src tests` — run static analysis and auto-formatting; both commands must succeed before opening a pull request.


## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation; prefer explicit imports and module-level type hints to clarify contracts.
- Document public methods with concise docstrings describing intent, inputs, and output format.


## Commit & Pull Request Guidelines
- Write Conventional Commit messages (`feat:`, `fix:`, `docs:`) with imperative verbs; scope optional but encouraged (`feat(agent): add retry policy`).
- Keep commits focused: code, accompanying tests, and documentation updates in the same change.
- Pull requests should include a short summary, testing notes (commands + results), and references to Jira tickets or GitHub issues.
- Provide screenshots or terminal captures whenever changes affect the developer experience or customer-visible flows.
