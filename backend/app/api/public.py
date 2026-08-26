from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select, text

from ..dependencies import RuntimeDep
from ..models import Profile, RelaySettings
from ..services.profiles import render_profile

router = APIRouter(tags=["public"])


@router.get("/healthz", include_in_schema=False)
async def healthz(runtime: RuntimeDep) -> Response:
    try:
        async with runtime.database.sessions() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "database_unavailable"},
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        {
            "status": "ok",
            "storage": (
                "persistent" if runtime.settings.persistent_database else "ephemeral"
            ),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/s/{token}", include_in_schema=False)
async def public_profile(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    runtime: RuntimeDep,
) -> Response:
    async with runtime.database.sessions() as session:
        row = (
            await session.execute(
                select(Profile, RelaySettings)
                .join(RelaySettings, RelaySettings.id == 1)
                .where(Profile.token == token)
            )
        ).one_or_none()
    if row is None:
        return JSONResponse(status_code=404, content={"detail": "Profile not found"})
    profile, relay_settings = row
    return await render_profile(
        request,
        background_tasks,
        runtime,
        profile,
        relay_settings,
        request_type="profile",
    )
