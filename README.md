---
title: IITM LLM App Developer
emoji: 🏢
colorFrom: red
colorTo: red
sdk: docker
pinned: false
license: mit
short_description: Develops Github Page Apps via LLM and publishes the same
app_port: 7777
---

# IITM LLM App Developer

Serverless-friendly FastAPI service that provisions starter repositories for IIT Madras LLM application development tasks. It accepts an authenticated task submission, scaffolds a GitHub repository with task instructions and attachments, and pushes the initial commit on behalf of the operator.

## Table of Contents
- [About the Service](#about-the-service)
- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Running the API](#running-the-api)
- [API Usage](#api-usage)
- [Testing](#testing)
- [Development Workflow Tips](#development-workflow-tips)
- [Deployment Notes](#deployment-notes)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## About the Service
The application accepts authenticated build requests, provisions a new GitHub repository seeded with task instructions, and pushes an initial commit. It is designed for IIT Madras LLM application rounds where fast turnaround and reproducibility matter.

## Features
- FastAPI endpoint (`POST /submit-task`) that validates authenticated task submissions.
- Background job that clones a template, writes incoming instructions, persists attachments, and pushes commits.
- GitHub API helpers to create repositories, manage remotes, and guard against name collisions.
- Data URI attachment handling with type-aware decoding.
- Regression test suite powered by `pytest` and Hypothesis strategies.

## Architecture Overview
.
|-- app/
|   |-- main.py                  # FastAPI entrypoint and HTTP surface
|   |-- task_handler.py          # Task routing and repository orchestration
|   |-- github_utils.py          # GitHub API + local git helpers
|   |-- openai_llm_utils.py      # OpenAI / GPT API integrations
|   |-- xml_utils.py             # XML parsing, CDATA handling, and conversion helpers
|   |-- database_utils.py        # Database connection and query utilities
|   |-- external_api.py          # Integrations with external APIs and web services
|   |-- common_utils.py          # Shared helper functions and constants
|   |-- models.py                # Pydantic request/response schemas
|   |-- set_github_user.sh       # Setup GitHub user and email
|   `-- templates/               # LICENSE template
|
|-- tests/                       # pytest-based regression and integration tests
|
|-- requirements.txt             # Runtime and test dependencies
|-- pyproject.toml               # Runtime and test dependencies
|-- uv.lock                      # Runtime and test dependencies
|-- AGENTS.md                    # Codex agents file
|-- Dockerfile                   # Dockerfile for deployment
|-- LICENSE                      # MIT LICENSE
`-- README.md                    # Project overview and usage guide


## Requirements
- Python 3.10 or later.
- Git 2.30+ available on `PATH`.
- GitHub personal access token with `repo` scope exported as `GITHUB_TOKEN`.
- (Optional) [`uv`](https://github.com/astral-sh/uv) for rapid dependency syncing.

## Quick Start
Create an isolated environment, install dependencies, and launch the API. Choose either `pip` or `uv` depending on preference.

### Using pip
```bash
python -m venv .venv
source .venv/bin/activate                # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
export LLM_APP_DEVELOPER_SECRET="secret" # shared secret with the caller
export GITHUB_TOKEN="ghp_yourtoken"      # token with repo rights
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Using uv
```bash
uv venv
source .venv/bin/activate
uv pip sync
export LLM_APP_DEVELOPER_SECRET="secret"
export GITHUB_TOKEN="ghp_yourtoken"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Configuration
- `LLM_APP_DEVELOPER_SECRET` (required): Shared secret expected from the client.
- `GITHUB_TOKEN` (required): Personal access token with repository creation rights.
- `GIT_AUTHOR_NAME` (required): Git author name used for commit (for the LLM generated app)
- `GIT_AUTHOR_EMAIL` (required): Git author email used for commit (for the LLM generated app)
- `OPENAI_MODEL` (required): OpenAI Model name (for eg: gpt-5-mini)
- `OPENAI_MAX_OUTPUT_TOKENS` (required): OpenAI model's maximum output tokens for each response
- `OPENAI_API_KEY` (required): OpenAI API key
- `OPENAI_API_URL` (required): OpenAI API's url endpoint
- `OPENAI_API_REQUEST_TIMEOUT` (required): Seconds to wait until OpenAI's API request times out
- `OPENAI_MAX_CONTINUATIONS` (required): OpenAI maximum continuations
- `REPO_BASE_PATH` (optional): Absolute or relative directory for cloned repositories; defaults to `./all_repositories`.
- `SPACE_ID` (optional): If provided, `.env` loading is skipped. Omit to rely on local `.env` files.

## Running the API
Start the service locally:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Hot reload is enabled so file changes restart the worker automatically.

## API Usage
Submit a task from an authenticated client. The API responds immediately while repository creation continues in the background.

```http
POST /submit-task HTTP/1.1
Content-Type: application/json

{
  "email": "student@example.com",
  "secret": "super-secret",
  "task": "portfolio-app",
  "round": 1,
  "nonce": "abc123",
  "brief": "LLM-generated GitHub Pages portfolio",
  "checks": ["lint", "unit tests"],
  "evaluation_url": "https://example.com/evaluate",
  "attachments": [
    {
      "name": "wireframe.png",
      "url": "data:image/png;base64,iVBORw0KGgoAAA..."
    }
  ]
}
```

### Response
```json
{
  "status": "success",
  "message": "Task accepted and processing started."
}
```

Once processing completes, the task handler clones the new repository under `REPO_BASE_PATH`, writes `instructions.txt`, saves attachments, commits, and pushes to GitHub.

## Testing
Run the automated checks before submitting changes:
```bash
pytest
```

Hypothesis-based property tests are included; execution may take longer on the first run while strategies are generated.

## Development Workflow Tips
- Use `pytest -k <pattern>` to scope tests when iterating on a failing case.
- `tests/test_task_handler.py` contains end-to-end orchestration cases and fixtures that mimic production payloads.
- Regenerate tokens and secrets via `.env` for local runs; never commit secrets.

## Deployment Notes
- The app is CORS-enabled for any origin, making it suitable for serverless platforms or Hugging Face Spaces (configured via the YAML front matter above).
- Ensure `LLM_APP_DEVELOPER_SECRET` is set in the deployment environment; missing secrets raise 500 errors.
- Failed GitHub interactions surface as HTTP 502/500 responses with contextual error messages.

## Troubleshooting
- **401 Unauthorized**: Verify the client-supplied secret matches `LLM_APP_DEVELOPER_SECRET`.
- **GitHub 404/403 errors**: Confirm the PAT has `repo` scope and that the account can create repositories under the configured organization.
- **File permission issues**: Override `REPO_BASE_PATH` to a writable directory when running in containerized or sandboxed environments.

## License
Released under the MIT License. See `license: mit` in the space metadata or add a `LICENSE` file for standalone usage.
