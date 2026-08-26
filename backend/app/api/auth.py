from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ..dependencies import SessionManagerDep, SettingsDep
from ..schemas import AuthSessionResponse, LoginRequest
from ..security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    AdminSessionDep,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=AuthSessionResponse)
async def login(
    payload: LoginRequest,
    settings: SettingsDep,
    session_manager: SessionManagerDep,
) -> Response:
    if settings.admin_password is None:
        raise HTTPException(status_code=503, detail="Admin login is not configured")
    if not session_manager.authenticate(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    cookie, session = session_manager.create_cookie(payload.username)
    response = JSONResponse(
        AuthSessionResponse(
            authenticated=True,
            admin_configured=True,
            username=session.username,
            csrf_token=session.csrf_token,
        ).model_dump(exclude_none=True)
    )
    response.set_cookie(
        SESSION_COOKIE,
        cookie,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/",
    )
    return response


@router.get("/session")
async def auth_session(
    request: Request,
    settings: SettingsDep,
    session_manager: SessionManagerDep,
) -> AuthSessionResponse:
    session = session_manager.read_cookie(request.cookies.get(SESSION_COOKIE))
    if session is None:
        return AuthSessionResponse(
            authenticated=False,
            admin_configured=settings.admin_password is not None,
        )
    return AuthSessionResponse(
        authenticated=True,
        admin_configured=True,
        username=session.username,
        csrf_token=session.csrf_token,
    )


@router.post("/logout")
async def logout(_admin: AdminSessionDep) -> Response:
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
