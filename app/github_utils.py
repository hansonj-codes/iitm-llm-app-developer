"""Utilities for interacting with GitHub and managing repositories."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Tuple
from datetime import datetime

import requests

from app.database_utils import get_task


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
    """Create a GitHub repository using the authenticated user token and enable GitHub Pages (Classic)."""
    import os

    class GitHubError(Exception):
        pass

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

    create_repo_response = requests.post(
        api_url,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30,
    )

    if create_repo_response.status_code == 201:
        print(f"Created repository: {repo_name}")
        return create_repo_response.json()
    elif create_repo_response.status_code == 422 and "name already exists" in create_repo_response.text.lower():
        raise GitHubError("Repository with this name already exists.")
    else:
        raise GitHubError(
            f"Failed to create repository ({create_repo_response.status_code}): {create_repo_response.text}"
        )

def enable_github_pages(repo_name: str, owner: str) -> None:
    # <<code here>> — enable GitHub Pages (Classic Experience)

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise GitHubError("Missing GITHUB_TOKEN environment variable.")

    pages_api_url = f"https://api.github.com/repos/{owner}/{repo_name}/pages"
    pages_payload = {
        "source": {
            "branch": "main",
            "path": "/"
        }
    }

    pages_response = requests.post(
        pages_api_url,
        json=pages_payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30,
    )

    if pages_response.status_code in (201, 204):
        print(f"Enabled GitHub Pages for {repo_name} (Classic from main branch).")
        return pages_response.json()
    else:
        raise GitHubError(
            f"Failed to enable GitHub Pages ({pages_response.status_code}): {pages_response.text}"
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


def write_instructions(repo_path: str | Path, task: str, brief: str, checks: list[str]) -> None:
    """Create the instructions.txt file inside the repository."""
    repo_path = Path(repo_path)
    instructions = [
        f"Task: {task}",
        "",
        f"Brief: {brief}",
        "",
        "Checks:",
        *(f"- {item}" for item in checks),
    ]
    content = "\n".join(instructions).strip() + "\n"
    (repo_path / "README.md").write_text(content, encoding="utf-8")
    (repo_path / "index.html").write_text("<h1>Hello, World!</h1>\n", encoding="utf-8")
    (repo_path / ".nojekyll").write_text("", encoding="utf-8")  # To enable GitHub Pages (Classic)
    license_text = open("./app/templates/license_template.txt", "r")\
                    .read()\
                    .replace("[year]", datetime.now().strftime('%Y'))\
                    .replace("[fullname]", "Autogen LLM App")
    (repo_path / "LICENSE").write_text(license_text, encoding="utf-8")
    (repo_path / ".gitignore").write_text('.llm_output*', encoding="utf-8")


def save_attachments(repo_path: str | Path, attachments: list[dict[str, str]]) -> None:
    """Persist attachments onto disk inside the repository."""
    repo_path = Path(repo_path)
    for attachment in attachments:
        attachment_name = attachment.get("name")
        attachment_url = attachment.get("url")
        data, _mime_type = decode_data_uri(attachment_url)
        target_path = repo_path / attachment_name
        target_path.write_bytes(data)


def git_commit_and_push(repo_path: str | Path, owner: str, message: str) -> None:
    """Commit all changes and push them to the remote main branch."""
    env = os.environ.copy()
    token = env.get("GITHUB_TOKEN")
    if not token:
        raise GitHubError("Missing GITHUB_TOKEN environment variable for git push.")

    repo_path = Path(repo_path)
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

    commit_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    print(f"Pushed commit {commit_hash} to remote repository.")
    truncated_hash = commit_hash[:7]
    return truncated_hash


def setup_local_repo(
    task: str,
) -> Path:
    """
    Clone the repository, populate files, and push the initial commit.

    Returns the local repository path.
    """
    payload = get_task(task)
    repo_name = payload['repo_name']
    repo_clone_url = payload['repo_clone_url']
    base_path = Path(payload['base_path'])
    owner = payload['owner']
    attachements = json.loads(payload.get("attachments"))

    repo_path = base_path / repo_name
    clone_repository(repo_clone_url, repo_path)
    write_instructions(repo_path, task, payload['brief'], json.loads(payload.get("checks")))
    save_attachments(repo_path, attachements or [])
    commit_sha = git_commit_and_push(
        repo_path=repo_path,
        owner=owner,
        message="Add initial instructions and attachments",
    )
    return repo_path, commit_sha

# Check if the page has been deployed successfully
def check_github_pages_status(owner: str, repo_name: str) -> str:
    token = os.getenv("GITHUB_TOKEN")
    if not token:     
        raise GitHubError("Missing GITHUB_TOKEN environment variable.")
    pages_api_url = f"https://api.github.com/repos/{owner}/{repo_name}/pages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    response = requests.get(pages_api_url, headers=headers, timeout=30)
    if response.status_code == 200:
        data = response.json()
        return data.get("status", "unknown")
    else:
        raise GitHubError(
            f"Failed to fetch GitHub Pages status ({response.status_code}): {response.text}"
        )