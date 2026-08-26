from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Query, Request
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


@router.get("/subscription", include_in_schema=False)
async def default_subscription(
    request: Request,
    runtime: RuntimeDep,
    session: SessionDep,
    token: Annotated[str | None, Query()] = None,
) -> Response:
    if not secrets.compare_digest(token or "", runtime.settings.relay_token):
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid relay token"},
            headers={"Cache-Control": "no-store"},
        )
    profile = await session.scalar(
        select(Profile).where(Profile.token == runtime.settings.relay_token)
    )
    if profile is None:
        return JSONResponse(status_code=503, content={"detail": "No profile"})
    return await render_profile(
        request,
        runtime,
        profile,
        request_type="default",
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
