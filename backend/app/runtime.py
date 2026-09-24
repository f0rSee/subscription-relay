from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from .config import Settings
from .database import Database
from .security import SecretBox, SessionManager


class KeyedLock:
    """Manages independent locks keyed by identifier to prevent head-of-line
    blocking.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, key: str) -> AsyncIterator[None]:
        async with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
        async with lock:
            yield


@dataclass(frozen=True)
class AppRuntime:
    settings: Settings
    database: Database
    secret_box: SecretBox
    sessions: SessionManager
    refresh_lock: asyncio.Lock
    profile_locks: KeyedLock


def create_runtime(settings: Settings) -> AppRuntime:
    return AppRuntime(
        settings=settings,
        database=Database(settings),
        secret_box=SecretBox(settings.app_encryption_key),
        sessions=SessionManager(settings),
        refresh_lock=asyncio.Lock(),
        profile_locks=KeyedLock(),
    )

