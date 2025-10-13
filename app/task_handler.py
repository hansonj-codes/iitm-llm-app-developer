"""Task handling logic invoked by FastAPI endpoints."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from uuid import uuid4

from fastapi import HTTPException, status

from .github_utils import GitHubError, create_remote_repository, setup_local_repo
from .models import SubmitTaskRequest

MAX_REPO_CREATION_ATTEMPTS = 5


def handle_llm_task(payload: SubmitTaskRequest) -> dict:
    """Delegate a task based on its round identifier."""
    if payload.round == 1:
        return handle_round_01(payload)
    if payload.round == 2:
        return handle_round_02(payload)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported round index: {payload.round}",
    )


def handle_round_01(payload: SubmitTaskRequest) -> dict:
    """Create and initialise a repository for round 1 tasks."""
    base_path = Path(os.getenv("REPO_BASE_PATH", "./all_repositories")).resolve()

    for attempt in range(MAX_REPO_CREATION_ATTEMPTS):
        repo_suffix = uuid4().hex[:8]
        repo_name = f"{payload.task}-{repo_suffix}"

        try:
            repo_info = create_remote_repository(
                repo_name=repo_name,
                description=f"Auto-generated for task {payload.task}",
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
                payload=payload,
                repo_name=repo_name,
                repo_clone_url=repo_info["clone_url"],
                base_path=base_path,
                owner=repo_info["owner"]["login"],
            )
        except (GitHubError, OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to prepare repository: {exc}",
            ) from exc

        return {
            "repo_name": repo_name,
            "repo_path": str(repo_path),
            "clone_url": repo_info["clone_url"],
            "html_url": repo_info.get("html_url"),
        }

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
