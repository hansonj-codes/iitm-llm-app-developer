import pytest
from fastapi import HTTPException

from app import task_handler
from app.models import SubmitTaskRequest


def build_payload(round: int = 1) -> SubmitTaskRequest:
    """Helper to construct a minimal SubmitTaskRequest."""
    return SubmitTaskRequest(
        email="student@example.com",
        secret="secret",
        task="task-001",
        round=round,
        nonce="nonce",
        brief="Build something cool",
        checks=["lint", "test"],
        evaluation_url="https://example.com/evaluate",
        attachments=[],
    )


def test_handle_llm_task_delegates_round_1(monkeypatch):
    called = {}

    def fake_round_01(payload):
        called["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr(task_handler, "handle_round_01", fake_round_01)

    payload = build_payload(round=1)
    result = task_handler.handle_llm_task(payload)

    assert result == {"ok": True}
    assert called["payload"] == payload


def test_handle_llm_task_round_2_not_implemented(monkeypatch):
    payload = build_payload(round=2)
    with pytest.raises(HTTPException) as exc:
        task_handler.handle_llm_task(payload)

    assert exc.value.status_code == 501
    assert "not implemented" in exc.value.detail.lower()


@pytest.mark.parametrize("round_value", [0, 3, 99])
def test_handle_llm_task_invalid_round(round_value):
    payload = build_payload(round=round_value)
    with pytest.raises(HTTPException) as exc:
        task_handler.handle_llm_task(payload)

    assert exc.value.status_code == 400
    assert str(round_value) in exc.value.detail


def test_handle_round_01_success(monkeypatch, tmp_path):
    created_repo = {
        "clone_url": "https://github.com/example/repo.git",
        "owner": {"login": "example"},
        "html_url": "https://github.com/example/repo",
    }
    local_path = tmp_path / "repo-path"

    def fake_create_remote_repository(repo_name, description):
        result = created_repo.copy()
        result.update({"name": repo_name, "description": description})
        return result

    def fake_setup_local_repo(payload, repo_name, repo_clone_url, base_path, owner):
        assert repo_name.startswith(payload.task)
        assert base_path.exists()
        assert owner == created_repo["owner"]["login"]
        return local_path

    monkeypatch.setenv("REPO_BASE_PATH", str(tmp_path))
    monkeypatch.setattr(task_handler, "create_remote_repository", fake_create_remote_repository)
    monkeypatch.setattr(task_handler, "setup_local_repo", fake_setup_local_repo)

    payload = build_payload(round=1)
    result = task_handler.handle_round_01(payload)

    assert result["repo_path"] == str(local_path)
    assert result["clone_url"] == created_repo["clone_url"]
    assert "repo_name" in result
    assert payload.task in result["repo_name"]
