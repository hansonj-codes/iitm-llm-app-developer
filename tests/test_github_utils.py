import base64
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from app.github_utils import decode_data_uri, ensure_base_path, save_attachments, write_instructions
from app.models import Attachment, SubmitTaskRequest


def build_payload(**overrides) -> SubmitTaskRequest:
    """Utility to create SubmitTaskRequest instances for tests."""
    base_payload = dict(
        email="user@example.com",
        secret="topsecret",
        task="task-123",
        round=1,
        nonce="abc123",
        brief="Example brief",
        checks=["check 1", "check 2"],
        evaluation_url="https://example.com/eval",
        attachments=[],
    )
    base_payload.update(overrides)
    return SubmitTaskRequest(**base_payload)


def test_ensure_base_path_creates_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "repo"
    result = ensure_base_path(target)
    assert result == target
    assert target.exists()
    assert target.is_dir()


@given(payload=st.binary(max_size=512))
def test_decode_data_uri_round_trip_base64(payload: bytes) -> None:
    data_uri = "data:application/octet-stream;base64," + base64.b64encode(payload).decode("ascii")
    decoded, mime = decode_data_uri(data_uri)
    assert decoded == payload
    assert mime == "application/octet-stream"


@given(text=st.text(alphabet=st.characters(blacklist_categories=("Cs",), min_codepoint=32, max_codepoint=126), max_size=128))
def test_decode_data_uri_plain_text(text: str) -> None:
    data_uri = "data:text/plain," + text
    decoded, mime = decode_data_uri(data_uri)
    assert decoded == text.encode("utf-8")
    assert mime == "text/plain"


def test_decode_data_uri_rejects_invalid_format() -> None:
    with pytest.raises(ValueError):
        decode_data_uri("not-a-data-uri")


def test_write_instructions_creates_expected_content(tmp_path: Path) -> None:
    payload = build_payload(checks=["first", "second"])
    write_instructions(tmp_path, payload)
    content = (tmp_path / "instructions.txt").read_text(encoding="utf-8").splitlines()
    assert content[0] == f"Task: {payload.task}"
    assert "Brief: Example brief" in content
    assert content[-2:] == ["- first", "- second"]


@given(
    name=st.from_regex(r"[A-Za-z0-9_\-]{1,16}\.bin", fullmatch=True),
    payload=st.binary(max_size=512),
)
def test_save_attachments_writes_file(tmp_path: Path, name: str, payload: bytes) -> None:
    data_uri = "data:application/octet-stream;base64," + base64.b64encode(payload).decode("ascii")
    attachment = Attachment(name=name, url=data_uri)
    save_attachments(tmp_path, [attachment])
    assert (tmp_path / name).read_bytes() == payload
