"""Backward-compatible ASGI entrypoint used by Uvicorn and Render."""

from backend.app.main import app

__all__ = ["app"]
