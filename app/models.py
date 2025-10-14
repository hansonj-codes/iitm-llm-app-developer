"""Pydantic models for the FastAPI service."""

from __future__ import annotations

from typing import List, Any

from pydantic import BaseModel, Field, HttpUrl


class Attachment(BaseModel):
    """Represents an attachment provided as a data URI."""

    name: str = Field(..., description="Attachment file name including extension.")
    url: str = Field(..., description="Data URI payload for the attachment.")


class SubmitTaskRequest(BaseModel):
    """Incoming request schema for `/submit-task`."""

    email: str = Field(..., description="Student email ID.")
    secret: str = Field(..., description="Shared secret used for authentication.")
    task: str = Field(..., description="Unique task identifier.")
    round: int = Field(..., ge=1, description="Round index for the task.")
    nonce: str = Field(..., description="Nonce that should be echoed back on evaluation.")
    brief: str = Field(..., description="Short description of the requested app.")
    checks: List[Any] = Field(
        default_factory=list,
        description="Evaluation checklist items.",
    )
    evaluation_url: HttpUrl = Field(
        ...,
        description="Callback URL that receives repository details.",
    )
    attachments: List[Attachment] = Field(
        default_factory=list,
        description="Optional list of attachments encoded as data URIs.",
    )


class SubmitTaskResponse(BaseModel):
    """Response payload returned by `/submit-task`."""

    status: str = Field(..., description="Outcome indicator, e.g. 'success'.")
    message: str = Field(..., description="Human-readable explanation of the result.")
    # repo_name: Optional[str] = Field(
    #     default=None,
    #     description="Name of the repository created for the task, if any.",
    # )
    # repo_path: Optional[str] = Field(
    #     default=None,
    #     description="Local filesystem path where the repository was cloned.",
    # )
