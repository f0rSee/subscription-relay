from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select, text

from ..dependencies import RuntimeDep, SessionDep
from ..models import Profile
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
    runtime: RuntimeDep,
    session: SessionDep,
) -> Response:
    profile = await session.scalar(select(Profile).where(Profile.token == token))
    if profile is None:
        return JSONResponse(status_code=404, content={"detail": "Profile not found"})
    return await render_profile(
        request,
        runtime,
        profile,
        request_type="profile",
    )
