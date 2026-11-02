import asyncio
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.dml import Update
from test_app import login, settings_for, with_client

from backend.app.device_settings import DeviceSettings
from backend.app.main import create_app
from backend.app.services.bootstrap import bootstrap

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")


@asynccontextmanager
async def device_settings_app(tmp_path, database):
    app = create_app(settings_for(tmp_path))
    if database == "sqlite":
        yield app
        return

    # Use a private schema so an optional PostgreSQL test run cannot alter
    # any pre-existing tables in the supplied database.
    schema = f"device_settings_test_{uuid4().hex}"
    admin = create_async_engine(POSTGRES_URL, poolclass=NullPool)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    runtime = app.state.runtime
    await runtime.database.close()
    engine = create_async_engine(
        POSTGRES_URL,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )
    runtime.database.engine = engine
    runtime.database.sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield app
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.mark.parametrize(
    "database",
    [
        "sqlite",
        pytest.param(
            "postgresql",
            marks=pytest.mark.skipif(
                not POSTGRES_URL,
                reason="Set TEST_POSTGRES_URL to test PostgreSQL locks",
            ),
        ),
    ],
)
@pytest.mark.parametrize("source_change", ["reset", "create", "bootstrap"])
def test_defaults_save_serializes_inheritance_changes(
    tmp_path, monkeypatch, database, source_change
):
    from backend.app.services.settings import lock_device_settings_changes

    invalidated = asyncio.Event()
    finish_defaults_save = asyncio.Event()
    source_change_started = asyncio.Event()
    original_execute = AsyncSession.execute
    pause_defaults_save = False
    fetched_hwids = []
    runtime = None
    new_device = DeviceSettings(hwid="new-shared-device").model_dump()

    async def execute(session, statement, *args, **kwargs):
        result = await original_execute(session, statement, *args, **kwargs)
        if (
            pause_defaults_save
            and isinstance(statement, Update)
            and statement.table.name == "subscriptions"
        ):
            # Pause after the global save has skipped sources with overrides,
            # but before it has committed the new shared device.
            invalidated.set()
            await finish_defaults_save.wait()
        return result

    async def lock_source_change(session):
        source_change_started.set()
        await lock_device_settings_changes(session)

    async def fetch(url, settings, proxy_url=None, device_settings=None):
        fetched_hwids.append(device_settings.hwid)
        return b"vless://new@server.example:443#NewDevice\n", httpx.Headers()

    monkeypatch.setattr(AsyncSession, "execute", execute)
    monkeypatch.setattr(
        "backend.app.api.subscriptions.lock_device_settings_changes", lock_source_change
    )
    monkeypatch.setattr(
        "backend.app.services.bootstrap.lock_device_settings_changes",
        lock_source_change,
    )
    monkeypatch.setattr("backend.app.services.subscriptions.fetch_subscription", fetch)

    async def verify(client):
        nonlocal pause_defaults_save
        csrf = await login(client)
        headers = {"X-CSRF-Token": csrf}
        source = (await client.get("/api/subscriptions")).json()[0]
        source_url = f"/api/subscriptions/{source['id']}"
        if source_change == "reset":
            assigned = await client.patch(
                source_url,
                headers=headers,
                json={"device_settings": DeviceSettings(hwid="custom").model_dump()},
            )
            assert assigned.status_code == 200
        elif source_change == "bootstrap":
            assert (await client.delete(source_url, headers=headers)).status_code == 204
        source_change_started.clear()
        pause_defaults_save = True
        saving = asyncio.create_task(
            client.patch(
                "/api/settings",
                headers=headers,
                json={"default_device_settings": new_device},
            )
        )
        pending_source = None
        try:
            await asyncio.wait_for(invalidated.wait(), timeout=5)
            if source_change == "reset":
                source_request = client.patch(
                    source_url, headers=headers, json={"device_settings": None}
                )
            elif source_change == "create":
                source_request = client.post(
                    "/api/subscriptions",
                    headers=headers,
                    json={
                        "name": "New inherited source",
                        "url": "https://new.example/sub",
                    },
                )
            else:
                # No HTTP handler is involved when startup seeds a missing source.
                source_request = bootstrap(runtime)
            pending_source = asyncio.create_task(source_request)
            await asyncio.wait_for(source_change_started.wait(), timeout=5)
            # In PostgreSQL the source write used to finish here, allowing a
            # sync with old defaults whose source version was never invalidated.
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(pending_source), timeout=1)
        finally:
            finish_defaults_save.set()
            await asyncio.gather(
                saving,
                *([pending_source] if pending_source else []),
                return_exceptions=True,
            )
            pause_defaults_save = False
        assert saving.result().status_code == 200
        if source_change == "bootstrap":
            assert pending_source.result() is None
            source = (await client.get("/api/subscriptions")).json()[0]
        else:
            changed = pending_source.result()
            assert changed.status_code == (200 if source_change == "reset" else 201)
            source = changed.json()
        source_url = f"/api/subscriptions/{source['id']}"
        assert source["device_settings"] is None
        assert (
            await client.post(f"{source_url}/sync", headers=headers)
        ).status_code == 200
        assert fetched_hwids == [new_device["hwid"]]

    async def scenario():
        nonlocal runtime
        async with device_settings_app(tmp_path, database) as app:
            runtime = app.state.runtime
            await with_client(app, verify)

    asyncio.run(scenario())
