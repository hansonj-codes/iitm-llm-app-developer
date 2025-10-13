"""Application package for the LLM task handler service."""

from .main import app  # re-export FastAPI app for convenience

__all__ = ["app"]
