"""Task handling logic invoked by FastAPI endpoints."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from uuid import uuid4

from fastapi import HTTPException, status

from .github_utils import GitHubError, create_remote_repository, setup_local_repo, enable_github_pages
from .models import SubmitTaskRequest
from .database_utils import upsert_task, get_task

MAX_REPO_CREATION_ATTEMPTS = 5


def handle_llm_task(task: str) -> dict:
    """Delegate a task based on its round identifier."""
    payload = get_task(task)
    payload_round = payload.get("round") if payload else None
    if payload_round == 1:
        return handle_round_01(task)
    if payload_round == 2:
        return handle_round_02(task)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported round index: {payload_round}",
    )


def handle_round_01(task: str) -> dict:
    """Create and initialise a repository for round 1 tasks."""
    base_path = Path(os.getenv("REPO_BASE_PATH", "./all_repositories")).resolve()

    payload = get_task(task)
    for attempt in range(MAX_REPO_CREATION_ATTEMPTS):
        repo_suffix = uuid4().hex[:8]
        repo_name = f"{task}-{repo_suffix}"

        try:
            repo_info = create_remote_repository(
                repo_name=repo_name,
                description=f"Auto-generated for task {task}",
            )
            upsert_task(task, {
                "repo_name": repo_name,
                "repo_clone_url": repo_info.get("html_url"),
                "base_path": str(base_path),
                "owner": repo_info["owner"]["login"],
                }
            )
        except GitHubError as exc:
            if "already exists" in str(exc).lower() and attempt < MAX_REPO_CREATION_ATTEMPTS - 1:
                continue
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to create repository: {exc}",
            ) from exc

        try:
            repo_path = setup_local_repo(
                task=task,
            )
            upsert_task(task, {
                "repo_local_path": str(repo_path),
            })
        except (GitHubError, OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to prepare repository: {exc}",
            ) from exc
        
        try:
            page_info = enable_github_pages(repo_name, owner=repo_info["owner"]["login"])
            upsert_task(task, {
                # "pages_url": f"https://{repo_info['owner']['login']}.github.io/{repo_name}/",
                "pages_url": page_info.get("html_url"),
            })
        except GitHubError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to enable GitHub Pages: {exc}",
            ) from exc

        print(f"Successfully created and initialized repository: {repo_name}")
        print(f"Details: {get_task(task)}")

        return {"backend_message": f"Repository {repo_name} created successfully."}

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Exhausted attempts to create a unique repository.",
    )


def handle_round_02(payload: SubmitTaskRequest) -> dict:
    """Placeholder for future round 2 handling logic."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Round 2 handling is not implemented yet.",
    )
