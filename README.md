---
title: Iitm Llm App Developer
emoji: 🏢
colorFrom: red
colorTo: red
sdk: docker
pinned: false
license: mit
short_description: Develops Github Page Apps via LLM and publishes the same
---

# IITM LLM App Developer

Serverless-friendly FastAPI service that provisions starter repositories for IIT Madras LLM application development tasks. It accepts an authenticated task submission, scaffolds a GitHub repository with task instructions and attachments, and pushes the initial commit on behalf of the operator.

## Guiding Principles
- **Clarity first:** Explain what the project does, who it is for, and how it fits into the wider workflow.
- **Actionable steps:** Document how to install dependencies, configure secrets, run the API, and execute tests.
- **Discoverability:** Surface key commands, project layout, and troubleshooting tips to shorten onboarding time.
- **Maintainability:** Reference configuration knobs and automation so future contributors understand the moving pieces.

## Features
- FastAPI endpoint (`POST /submit-task`) for authenticated task intake.
- Background provisioning of round 1 repositories with unique suffixes.
- GitHub automation for repository creation, cloning, file generation, and pushing the initial commit.
- Attachment handling via Data URI decoding.
- pytest + Hypothesis test suite covering core utilities.

## Architecture Overview
```
.
|-- app/
|   |-- main.py             # FastAPI entrypoint and HTTP surface
|   |-- task_handler.py     # Round routing and repository orchestration
|   |-- github_utils.py     # GitHub API + local git helpers
|   `-- models.py           # Pydantic request/response schemas
|-- tests/                  # pytest-based regression tests
|-- requirements.txt        # Runtime and test dependencies
`-- README.md
```

## Prerequisites
- Python 3.10+ and pip.
- Git 2.30+ installed and on `PATH`.
- GitHub personal access token with `repo` scope stored in `GITHUB_TOKEN`.

## Quick Start
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
export LLM_APP_DEVELOPER_SECRET="super-secret"   # shared secret with caller
export GITHUB_TOKEN="ghp_yourtoken"              # token with repo rights
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Optional environment variables:
- `REPO_BASE_PATH` – absolute or relative path where cloned repositories are stored (defaults to `./all_repositories`).

## Usage
Submit a task from an authenticated client. The API responds immediately while the repository is created in the background.

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
  "message": "Task accepted and processing started.",
  "repo_name": null,
  "repo_path": null
}
```

Once processing completes, the task handler clones the new repository under `REPO_BASE_PATH`, writes `instructions.txt`, saves attachments, commits, and pushes to GitHub.

## Testing
Run the automated checks before submitting changes:
```bash
pytest
```

Hypothesis-based property tests are included; execution may take longer on the first run while strategies are generated.

## Deployment Notes
- The app is CORS-enabled for any origin, making it suitable for serverless platforms or Hugging Face Spaces (configured via the YAML front matter above).
- Ensure `LLM_APP_DEVELOPER_SECRET` is set in the deployment environment; missing secrets raise 500 errors.
- Failed GitHub interactions surface as HTTP 502/500 responses with contextual error messages.

## License
Released under the MIT License. See `license: mit` in the space metadata or add a `LICENSE` file for standalone usage.
