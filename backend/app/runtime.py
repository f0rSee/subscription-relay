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
    blocking, with automatic cleanup when no waiters remain.
    """

    def __init__(self) -> None:
        self._locks: dict[str, tuple[asyncio.Lock, int]] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, key: str) -> AsyncIterator[None]:
        async with self._guard:
            if key in self._locks:
                lock, count = self._locks[key]
                self._locks[key] = (lock, count + 1)
            else:
                lock = asyncio.Lock()
                self._locks[key] = (lock, 1)
        try:
            async with lock:
                yield
        finally:
            async with self._guard:
                if key in self._locks:
                    lock, count = self._locks[key]
                    if count <= 1:
                        del self._locks[key]
                    else:
                        self._locks[key] = (lock, count - 1)


@dataclass(frozen=True)
class AppRuntime:
    settings: Settings
    database: Database
    secret_box: SecretBox
    sessions: SessionManager
    refresh_lock: asyncio.Lock
    profile_locks: KeyedLock
    subscription_locks: KeyedLock
    device_lock: asyncio.Lock


def create_runtime(settings: Settings) -> AppRuntime:
    return AppRuntime(
        settings=settings,
        database=Database(settings),
        secret_box=SecretBox(settings.app_encryption_key),
        sessions=SessionManager(settings),
        refresh_lock=asyncio.Lock(),
        profile_locks=KeyedLock(),
        subscription_locks=KeyedLock(),
        device_lock=asyncio.Lock(),
    )
