"""FastAPI application entry-point."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .models import SubmitTaskRequest, SubmitTaskResponse
from .task_handler import handle_llm_task
from fastapi import BackgroundTasks

# Load .env only if running locally
if os.getenv("SPACE_ID") is None:  # SPACE_ID is set by HF automatically
    from dotenv import load_dotenv
    load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="LLM Task Handler",
    version="1.0.0",
    description="Automates repository setup for LLM-driven assignments.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

@app.get("/", status_code=status.HTTP_200_OK)
async def root() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "message": "LLM App Developer is running."}


@app.post(
    "/submit-task",
    response_model=SubmitTaskResponse,
    status_code=status.HTTP_200_OK,
)
async def submit_task(payload: SubmitTaskRequest, background_tasks: BackgroundTasks) -> SubmitTaskResponse:
    """Accept a task submission request, respond immediately, and trigger repository provisioning in background."""
    expected_secret = os.getenv("LLM_APP_DEVELOPER_SECRET")
    if expected_secret is None:
        logger.error("LLM_APP_DEVELOPER_SECRET is not configured.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: missing shared secret.",
        )

    if payload.secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid secret.",
        )

    def background_task():
        handle_llm_task(payload)

    background_tasks.add_task(background_task)

    return SubmitTaskResponse(
        status="success",
        message="Task accepted and processing started.",
    )
