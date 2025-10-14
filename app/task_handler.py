"""Task handling logic invoked by FastAPI endpoints."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

from fastapi import HTTPException, status

from app.openai_llm_utils import construct_user_prompt, default_system_prompt, request_llm_and_get_output
from app.xml_utils import create_files_from_response

from .github_utils import GitHubError, create_remote_repository, git_commit_and_push, setup_local_repo, enable_github_pages
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
            complete_repo_path, commit_sha = setup_local_repo(
                task=task,
            )
            upsert_task(task, {
                "repo_local_path": str(complete_repo_path),
                "commit_hash": commit_sha,
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

        print(f"Successfully created and initialized bare repository: {repo_name}")
        print(f"Details: {get_task(task)}")

        try:
            user_prompt = construct_user_prompt(
                task=task
            )
            llm_output = request_llm_and_get_output(
                system_prompt=default_system_prompt(),
                user_prompt=user_prompt,
            )
            llm_output_save_path = Path(complete_repo_path) / '.llm_output_round_1.txt'
            with open(llm_output_save_path, 'w', encoding='utf-8') as f:
                f.write(llm_output)
            print(f"Saved LLM output to {llm_output_save_path}")
            upsert_task(task, {
                "llm_output_path": str(llm_output_save_path),
            })
            created_files = create_files_from_response(
                task=task,
                xml_file_path=llm_output_save_path,
                repo_path=complete_repo_path,
                additional_exclude_files=[],
            )
            upsert_task(task, {
                "created_files": json.dumps(created_files),
            })
            payload = get_task(task)
            round1_commit_sha = git_commit_and_push(
                repo_path=complete_repo_path,
                owner=payload["owner"],
                message=payload.get("commit_message", "Initial commit from LLM")
            )
            upsert_task(task, {
                "commit_hash": round1_commit_sha,
            })
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to construct user prompt: {exc}",
            ) from exc
        
        
        
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
