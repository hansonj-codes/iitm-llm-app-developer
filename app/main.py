"""FastAPI application entry-point."""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .common_utils import get_current_utc_time
from .models import SubmitTaskRequest, SubmitTaskResponse
from .task_handler import handle_llm_task
from .database_utils import initialize_db, upsert_task
from fastapi import BackgroundTasks

# Load .env only if running locally
if os.getenv("SPACE_ID") is None:  # SPACE_ID is set by HF automatically
    from dotenv import load_dotenv
    load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Database
    initialize_db()
    yield
    # Exiting, clean up resources if needed
    pass

app = FastAPI(
    title="LLM Task Handler",
    version="1.0.0",
    description="Automates repository setup for LLM-driven assignments.",
    lifespan=lifespan,
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

    # Record the new task in the database with 'pending' status
    try:
        upsert_task(payload.task, {
            "email": payload.email,
            "round": payload.round,
            "nonce": payload.nonce,
            "brief": payload.brief,
            "evaluation_url": str(payload.evaluation_url),
            "checks": json.dumps(payload.checks),
            "attachments": json.dumps([{"name": att.name, "url": att.url} for att in payload.attachments]),
            "status": "pending",
            "result": None,
            "error_message": None,
            "created_at": get_current_utc_time(),
            "updated_at": get_current_utc_time(),
        })
    except Exception as exc:
        logger.error(f"Failed to record task {payload.task} in database: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record task in database.",
        ) from exc
    def background_task():
        handle_llm_task(payload.task)

    background_tasks.add_task(background_task)

    return SubmitTaskResponse(
        status="success",
        message="Task accepted and processing started.",
    )
