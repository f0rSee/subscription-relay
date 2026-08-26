from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .database import Database
from .runtime import AppRuntime
from .security import SecretBox, SessionManager


def get_runtime(request: Request) -> AppRuntime:
    return request.app.state.runtime


RuntimeDep = Annotated[AppRuntime, Depends(get_runtime)]


def get_database(runtime: RuntimeDep) -> Database:
    return runtime.database


DatabaseDep = Annotated[Database, Depends(get_database)]


async def get_session(database: DatabaseDep) -> AsyncIterator[AsyncSession]:
    async with database.sessions() as session:
        yield session


SessionDep = Annotated[
    AsyncSession,
    Depends(get_session, scope="function"),
]


def get_settings(runtime: RuntimeDep) -> Settings:
    return runtime.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_secret_box(runtime: RuntimeDep) -> SecretBox:
    return runtime.secret_box


SecretBoxDep = Annotated[SecretBox, Depends(get_secret_box)]


def get_session_manager(runtime: RuntimeDep) -> SessionManager:
    return runtime.sessions


SessionManagerDep = Annotated[SessionManager, Depends(get_session_manager)]
