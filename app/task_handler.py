"""Task handling logic invoked by FastAPI endpoints."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from time import sleep
from uuid import uuid4
import traceback

from fastapi import HTTPException, status

from app.common_utils import get_current_utc_time
from app.external_api import send_round_completion_notification
from app.openai_llm_utils import construct_user_prompt_for_round_01, construct_user_prompt_for_round_02, default_system_prompt, request_llm_and_get_output
from app.xml_utils import create_files_from_response

from .github_utils import GitHubError, create_remote_repository, git_commit_and_push, save_attachments, setup_local_repo, enable_github_pages
from .database_utils import archive_task_round_01, parse_db_timestamp, upsert_task, get_task

MAX_REPO_CREATION_ATTEMPTS = 30
ROUND_01_TIMEOUT_SECONDS = 10 * 60  # 10 minutes
ROUND_01_BUFFER_TIME_REQUIRED = 30
ROUND_02_TIMEOUT_SECONDS = 10 * 60  # 10 minutes
ROUND_02_BUFFER_TIME_REQUIRED = 30
# PAGES_BUILD_WAIT_UNTIL_TIME_LEFT = 60  # 60 seconds
PAGES_BUILD_TIME_ESTIMATE = 40  # 20 seconds

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
    LLM_APPROX_TIME_REQUIRED = int(os.getenv("OPENAI_API_REQUEST_TIMEOUT"))  # seconds

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

        # Interact with LLM to generate task solution files and commit
        # Since LLM calls can be flaky, we wrap this in a try-except to handle failures gracefully
        # This block is retried until time_elapsed + LLM_APPROX_TIME_REQUIRED + ROUND_01_BUFFER_TIME_REQUIRED < ROUND_01_TIMEOUT_SECONDS
        payload = get_task(task)
        task_created_at = parse_db_timestamp(payload.get("created_at"))
        while True:
            time_elapsed = (get_current_utc_time() - task_created_at).total_seconds()
            time_left = ROUND_01_TIMEOUT_SECONDS - time_elapsed
            if LLM_APPROX_TIME_REQUIRED + ROUND_01_BUFFER_TIME_REQUIRED > time_left:
                print("Lack of time to safely complete LLM interaction, so skipping it and submitting bare repo.")
                break
            print(f"Starting LLM interaction for task {task} as time elapsed {time_elapsed} is in safe range.")
            try:
                user_prompt = construct_user_prompt_for_round_01(
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
                print(f"Committed and pushed LLM-generated files to remote repository, commit {round1_commit_sha}")
                break  # Exit the while loop on success
            except Exception as exc:
                print(f"LLM interaction failed for task {task}, retrying if time permits: {exc}")
                traceback.print_exc()
                continue  # Retry the LLM interaction if time permits

        try:
            archive_task_round_01(task)
        except Exception as exc:
            print(f"Warning: Failed to archive round 1 task {task}: {exc}")
        
        # check if the pages has been built every 10 seconds, until timeout is nearing
        # payload = get_task(task)
        # try:
        #     while True:
        #         time_elapsed = (get_current_utc_time() - task_created_at).total_seconds()
        #         time_left = ROUND_01_TIMEOUT_SECONDS - time_elapsed
        #         if time_left < PAGES_BUILD_WAIT_UNTIL_TIME_LEFT:
        #             print("Not enough time left to wait for pages build, proceeding to notify evaluation service.")
        #             break
        #         print("Waiting 10 seconds for GitHub Pages build to complete...")
        #         sleep(1)
        #         try:
        #             pages_status = check_github_pages_status(
        #                 repo_name=payload['repo_name'],
        #                 owner=payload["owner"],
        #             )
        #             print(f"GitHub Pages build status: {pages_status}")
        #             if pages_status == "built":
        #                 print("GitHub Pages build completed successfully.")
        #                 break
        #         except Exception as exc:
        #             print(f"Warning: Failed to check GitHub Pages status for {repo_name}: {exc}, retrying in 10 seconds.")
        #             continue
        # except Exception as exc:
        #     print(f"Warning: Failed to check GitHub Pages status for {repo_name}: {exc}, proceeding to notify evaluation service.")

        # Wait a fixed time for pages to be built before notifying evaluation service
        time_elapsed = (get_current_utc_time() - task_created_at).total_seconds()
        time_left = ROUND_01_TIMEOUT_SECONDS - time_elapsed
        if PAGES_BUILD_TIME_ESTIMATE + ROUND_01_BUFFER_TIME_REQUIRED > time_left:
            print("Not enough time left to wait for pages build, proceeding to notify evaluation service.")
        else:
            print(f"Waiting {PAGES_BUILD_TIME_ESTIMATE} seconds for GitHub Pages build to complete...")
            sleep(PAGES_BUILD_TIME_ESTIMATE)

        try:
            print('============= Sending details to evaluation url for round 1 ============')
            send_round_completion_notification(task)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to notify evaluation service: {exc}",
            ) from exc

        payload = get_task(task)
        print(f"Successfully completed round 1 for repository: {repo_name}, task payload: {payload}")
        return {"backend_message": f"Repository {repo_name} created successfully."}

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Exhausted attempts to create a unique repository.",
    )


def handle_round_02(task: str) -> dict:
    """Placeholder for future round 2 handling logic."""
    # Interact with LLM to generate task solution files and commit
    # Since LLM calls can be flaky, we wrap this in a try-except to handle failures gracefully
    # This block is retried until time_elapsed + LLM_APPROX_TIME_REQUIRED + ROUND_02_BUFFER_TIME_REQUIRED < ROUND_02_TIMEOUT_SECONDS
    LLM_APPROX_TIME_REQUIRED = int(os.getenv("OPENAI_API_REQUEST_TIMEOUT"))  # seconds
    payload = get_task(task)
    complete_repo_path = payload.get("repo_local_path")
    repo_name = payload.get("repo_name")

    try:
        attachements = json.loads(payload.get("attachments"))
        if len(attachements or []) > 0:
            save_attachments(Path(complete_repo_path), attachements or [])
            print(f"Saved {len(attachements)} additional attachments to {complete_repo_path}")
            commit_sha = git_commit_and_push(
                repo_path=Path(complete_repo_path),
                owner=payload["owner"],
                message="Add additional attachments for round 2",
            )
            upsert_task(task, {
                "commit_hash": commit_sha,
            })
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add attachments for round 2: {exc}",
        ) from exc


    while True:
        task_created_at = parse_db_timestamp(payload.get("created_at"))
        time_elapsed = (get_current_utc_time() - task_created_at).total_seconds()
        time_left = ROUND_02_TIMEOUT_SECONDS - time_elapsed
        if LLM_APPROX_TIME_REQUIRED + ROUND_02_BUFFER_TIME_REQUIRED > time_left:
            print("Lack of time to safely complete LLM interaction, so skipping it and submitting bare repo.")
            break
        print(f"Starting LLM interaction for task {task} as time elapsed {time_elapsed} is in safe range.")
        try:
            user_prompt = construct_user_prompt_for_round_02(
                task=task
            )
            llm_output = request_llm_and_get_output(
                system_prompt=default_system_prompt(),
                user_prompt=user_prompt,
            )
            llm_output_save_path = Path(complete_repo_path) / '.llm_output_round_2.txt'
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
            print(f"Committed and pushed LLM-generated files to remote repository, commit {round1_commit_sha}")
            break  # Exit the while loop on success
        except Exception as exc:
            print(f"LLM interaction failed for task {task}, retrying if time permits: {exc}")
            traceback.print_exc()
            continue  # Retry the LLM interaction if time permits

    # check if the pages has been built every 10 seconds, until timeout is nearing
    # payload = get_task(task)
    # try:
    #     while True:
    #         time_elapsed = (get_current_utc_time() - task_created_at).total_seconds()
    #         time_left = ROUND_01_TIMEOUT_SECONDS - time_elapsed
    #         if time_left < PAGES_BUILD_WAIT_UNTIL_TIME_LEFT:
    #             print("Not enough time left to wait for pages build, proceeding to notify evaluation service.")
    #             break
    #         print("Waiting 10 seconds for GitHub Pages build to complete...")
    #         sleep(1)
    #         try:
    #             pages_status = check_github_pages_status(
    #                 repo_name=payload['repo_name'],
    #                 owner=payload["owner"],
    #             )
    #             print(f"GitHub Pages build status: {pages_status}")
    #             if pages_status == "built":
    #                 print("GitHub Pages build completed successfully.")
    #                 break
    #         except Exception as exc:
    #             print(f"Warning: Failed to check GitHub Pages status for {repo_name}: {exc}, retrying in 10 seconds.")
    #             continue
    # except Exception as exc:
    #     print(f"Warning: Failed to check GitHub Pages status for {repo_name}: {exc}, proceeding to notify evaluation service.")

    # Wait a fixed time for pages to be built before notifying evaluation service
    time_elapsed = (get_current_utc_time() - task_created_at).total_seconds()
    time_left = ROUND_02_TIMEOUT_SECONDS - time_elapsed
    if PAGES_BUILD_TIME_ESTIMATE + ROUND_02_BUFFER_TIME_REQUIRED > time_left:
        print("Not enough time left to wait for pages build, proceeding to notify evaluation service.")
    else:
        print(f"Waiting {PAGES_BUILD_TIME_ESTIMATE} seconds for GitHub Pages build to complete...")
        sleep(PAGES_BUILD_TIME_ESTIMATE)

    try:
        print('============= Sending details to evaluation url for round 2 ============')
        send_round_completion_notification(task)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to notify evaluation service: {exc}",
        ) from exc
    
    payload = get_task(task)
    print(f"Successfully completed round 2 for repository: {repo_name}, task payload: {payload}")
    return {"backend_message": f"Repository {repo_name} updated successfully."}