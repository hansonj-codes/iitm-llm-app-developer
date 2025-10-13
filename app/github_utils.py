"""Utilities for interacting with GitHub and managing repositories."""

from __future__ import annotations

import base64
import os
import re
import subprocess
from pathlib import Path
from typing import Iterable, Tuple

import requests

from .models import Attachment, SubmitTaskRequest

DATA_URI_PATTERN = re.compile(r"^data:(?P<mime>[\w\-/+.]+)?(;charset=[\w-]+)?(?P<encoding>;base64)?,")


class GitHubError(Exception):
    """Raised when a GitHub API operation fails."""


def ensure_base_path(base_path: Path) -> Path:
    """Ensure the repositories base path exists."""
    base_path.mkdir(parents=True, exist_ok=True)
    return base_path


def decode_data_uri(data_uri: str) -> Tuple[bytes, str]:
    """
    Decode a data URI into bytes and return the suggested file extension.

    Returns:
        Tuple of decoded bytes and MIME type string.
    Raises:
        ValueError if the payload is malformed or unsupported.
    """
    match = DATA_URI_PATTERN.match(data_uri)
    if not match:
        raise ValueError("Attachment is not a valid data URI.")

    header, data_part = data_uri.split(",", 1)
    is_base64 = ";base64" in header

    if is_base64:
        try:
            payload = base64.b64decode(data_part)
        except (base64.binascii.Error, ValueError) as exc:  # pragma: no cover
            raise ValueError("Failed to decode base64 data URI payload.") from exc
    else:
        payload = data_part.encode("utf-8")

    mime_type = match.group("mime") or "application/octet-stream"
    return payload, mime_type


def create_remote_repository(repo_name: str, description: str) -> dict:
    """Create a GitHub repository using the authenticated user token."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise GitHubError("Missing GITHUB_TOKEN environment variable.")

    api_url = "https://api.github.com/user/repos"
    payload = {
        "name": repo_name,
        "description": description,
        "private": False,
        "auto_init": False,
    }

    response = requests.post(
        api_url,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30,
    )

    if response.status_code == 201:
        return response.json()

    if response.status_code == 422 and "name already exists" in response.text.lower():
        raise GitHubError("Repository with this name already exists.")

    raise GitHubError(
        f"Failed to create repository ({response.status_code}): {response.text}"
    )


def clone_repository(clone_url: str, target_dir: Path) -> None:
    """Clone a GitHub repository into the target directory."""
    ensure_base_path(target_dir.parent)
    subprocess.run(
        ["git", "clone", clone_url, str(target_dir)],
        check=True,
        capture_output=True,
        text=True,
    )


def write_instructions(repo_path: Path, payload: SubmitTaskRequest) -> None:
    """Create the instructions.txt file inside the repository."""
    instructions = [
        f"Task: {payload.task}",
        "",
        f"Brief: {payload.brief}",
        "",
        "Checks:",
        *(f"- {item}" for item in payload.checks),
    ]
    content = "\n".join(instructions).strip() + "\n"
    (repo_path / "instructions.txt").write_text(content, encoding="utf-8")


def save_attachments(repo_path: Path, attachments: Iterable[Attachment]) -> None:
    """Persist attachments onto disk inside the repository."""
    for attachment in attachments:
        data, _mime_type = decode_data_uri(attachment.url)
        target_path = repo_path / attachment.name
        target_path.write_bytes(data)


def git_commit_and_push(repo_path: Path, owner: str, message: str) -> None:
    """Commit all changes and push them to the remote main branch."""
    env = os.environ.copy()
    token = env.get("GITHUB_TOKEN")
    if not token:
        raise GitHubError("Missing GITHUB_TOKEN environment variable for git push.")

    repo_name = repo_path.name
    remote_url = f"https://{owner}:{token}@github.com/{owner}/{repo_name}.git"

    subprocess.run(["git", "checkout", "-B", "main"], cwd=repo_path, check=True)
    subprocess.run(["git", "add", "--all"], cwd=repo_path, check=True)

    # Commit only if there are staged changes
    commit_status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo_path,
    )
    if commit_status.returncode == 0:
        return

    subprocess.run(["git", "commit", "-m", message], cwd=repo_path, check=True)
    subprocess.run(["git", "push", remote_url, "HEAD:main"], cwd=repo_path, check=True)


def setup_local_repo(
    payload: SubmitTaskRequest,
    repo_name: str,
    repo_clone_url: str,
    base_path: Path,
    owner: str,
) -> Path:
    """
    Clone the repository, populate files, and push the initial commit.

    Returns the local repository path.
    """
    repo_path = base_path / repo_name
    clone_repository(repo_clone_url, repo_path)
    write_instructions(repo_path, payload)
    save_attachments(repo_path, payload.attachments or [])
    git_commit_and_push(
        repo_path=repo_path,
        owner=owner,
        message="Add initial instructions and attachments",
    )
    return repo_path
