# Repository Guidelines

## Project Structure & Module Organization
- Keep Python source in `src/instacart_chatgpt/`; split conversational agents, prompt assets, and utilities into focused modules (e.g., `agents/`, `prompts/`, `services/`).
- Place integration and unit tests in `tests/`, mirroring the source layout (`tests/agents/test_routing.py` for `src/instacart_chatgpt/agents/routing.py`).
- Store datasets, fixtures, and long-lived prompt examples under `assets/` or `tests/fixtures/`; prefer lightweight YAML or JSON for reproducibility.
- Configuration belonging to local environments (API keys, secrets) should live in `.env` files that are ignored by git; update `.env.example` whenever variables change.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate` — create/activate the local virtual environment; run once per machine.
- `python -m pip install -r requirements.txt` — install runtime and tooling dependencies; regenerate the lock file when versions change.
- `python -m pytest` — execute the full automated test suite; use `-k` to focus on a subset during development.
- `ruff check src tests` and `ruff format src tests` — run static analysis and auto-formatting; both commands must succeed before opening a pull request.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation; prefer explicit imports and module-level type hints to clarify contracts.
- Name agent classes with the suffix `Agent` (e.g., `CartAssistAgent`), prompt templates with `_PROMPT`, and async entry points with the prefix `async_`.
- Document public methods with concise docstrings describing intent, inputs, and output format.

## Testing Guidelines
- Use `pytest` for all test cases; new features require companion tests covering happy path and edge conditions.
- Name tests following `test_<module>_scenario` and mark slow or integration tests with `@pytest.mark.slow` so they can be skipped locally.
- Aim for ≥85% statement coverage; justify exceptions in the pull request description and add TODO comments with owners.
- Snapshot or mock LLM responses to keep tests deterministic; store fixtures in `tests/fixtures/` and reuse across suites.

## Commit & Pull Request Guidelines
- Write Conventional Commit messages (`feat:`, `fix:`, `docs:`) with imperative verbs; scope optional but encouraged (`feat(agent): add retry policy`).
- Keep commits focused: code, accompanying tests, and documentation updates in the same change.
- Pull requests should include a short summary, testing notes (commands + results), and references to Jira tickets or GitHub issues.
- Provide screenshots or terminal captures whenever changes affect the developer experience or customer-visible flows.
