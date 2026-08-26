"""Production ASGI entrypoint."""

from .main import create_app

app = create_app()

__all__ = ["app"]
