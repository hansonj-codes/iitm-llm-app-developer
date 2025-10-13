# Repository Guidelines

## Project Structure & Module Organization
- `app/` holds the FastAPI service: `main.py` for routing, `task_handler.py` for orchestration, `github_utils.py` for GitHub interactions, and `models.py` for typed request/response schemas.
- `tests/` contains pytest suites that mimic production flows; keep new fixtures alongside the code they exercise.
- Root-level files: `requirements.txt` for runtime deps, `pyproject.toml` for packaging + dev extras, and `uv.lock` if you opt into `uv` for dependency management.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate` — create an isolated environment.
- `pip install -r requirements.txt` or `uv pip sync` — install server and test dependencies.
- `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` — run the API locally with hot reload.
- `pytest` — execute the regression suite (includes Hypothesis property tests).

## Coding Style & Naming Conventions
- Target Python 3.10 features, four-space indentation, and PEP 8 formatting.
- Prefer explicit type hints and descriptive function names (`handle_round_01`, `create_remote_repository`).
- Use module-level docstrings for entry points and add lightweight comments only where logic is non-obvious.
- Keep filenames snake_case and align new models with existing Pydantic patterns.

## Testing Guidelines
- Write pytest functions starting with `test_`; parameterize edge cases as shown in `tests/test_task_handler.py`.
- Extend property-based tests when you add new validation logic; Hypothesis is available via the dev dependency group.
- Ensure new features include a regression test before opening a PR; locally rerun `pytest` and note slow Hypothesis warm-up on first run.

## Commit & Pull Request Guidelines
- Follow a concise, imperative subject line (e.g., “Add round handler validation”); elaborate in the body if rationale or follow-up steps are needed.
- Squash work-in-progress commits prior to review; each PR should map to one logical change.
- PR descriptions must cover the problem, solution, any config updates, and manual test evidence; link GitHub issues or tasks where applicable.
- Attach screenshots or logs when changes impact external automation or API responses.

## Secrets & Configuration Tips
- Set `LLM_APP_DEVELOPER_SECRET` and `GITHUB_TOKEN` in your shell or `.env`; the app autoloads `.env` when `SPACE_ID` is unset.
- Use `REPO_BASE_PATH` to point provisioning to a writable workspace during local runs; default is `./all_repositories`.
- Never commit secrets—add `.env` files to your ignore list and verify redactions in logs.
