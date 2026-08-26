from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .database import Database
from .security import SecretBox, SessionManager


@dataclass(frozen=True)
class AppRuntime:
    settings: Settings
    database: Database
    secret_box: SecretBox
    sessions: SessionManager


def create_runtime(settings: Settings) -> AppRuntime:
    return AppRuntime(
        settings=settings,
        database=Database(settings),
        secret_box=SecretBox(settings.app_encryption_key),
        sessions=SessionManager(settings),
    )
