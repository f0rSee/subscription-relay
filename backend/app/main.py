from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

from .api.public import router as public_router
from .api.router import router as api_router
from .config import Settings, get_settings
from .runtime import create_runtime
from .services.bootstrap import bootstrap
from .services.expiration import (
    cleanup_expired_subscriptions,
    subscription_cleanup_loop,
)


def create_app(settings_override: Settings | None = None) -> FastAPI:
    """Build the application without reading global state in tests."""
    settings = settings_override or get_settings()
    runtime = create_runtime(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await runtime.database.create_schema()
        await bootstrap(runtime)
        await cleanup_expired_subscriptions(runtime.database)
        cleanup_task = asyncio.create_task(subscription_cleanup_loop(runtime.database))
        try:
            yield
        finally:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
            await runtime.database.close()

    app = FastAPI(
        title="Subscription Relay",
        version="2.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.include_router(public_router)
    app.include_router(api_router)
    if settings.frontend_dist.is_dir():
        app.frontend(
            "/admin",
            directory=settings.frontend_dist,
            fallback="index.html",
        )
    else:

        @app.get("/admin", include_in_schema=False)
        @app.get("/admin/{path:path}", include_in_schema=False)
        async def dashboard_not_built(path: str = "") -> Response:
            return JSONResponse(
                status_code=503,
                content={"detail": "Dashboard assets are not built"},
            )

    return app
