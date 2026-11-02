import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import Update
from test_app import login, settings_for, with_client

from backend.app.main import create_app
from backend.app.models import (
    Node,
    Profile,
    ProfileNodePreference,
    ProfileSubscription,
    Subscription,
    SubscriptionDeviceSettings,
    SubscriptionProxy,
    SubscriptionUsage,
    UpstreamProxy,
)
from backend.app.services import expiration
from backend.app.services.subscriptions import (
    PreparedSubscriptionSync,
    parse_subscription,
    persist_subscription_syncs,
)


def test_cleanup_observes_grace_period_and_cascades(tmp_path):
    runtime = create_app(settings_for(tmp_path)).state.runtime
    now = datetime(2026, 11, 2, tzinfo=UTC)
    cutoff = int((now - timedelta(days=3)).timestamp())

    async def scenario():
        await runtime.database.create_schema()
        try:
            async with runtime.database.sessions() as session:
                for name, expire in {
                    "expired": cutoff - 1,
                    "disabled": cutoff - 3600,
                    "boundary": cutoff,
                    "recent": cutoff + 1,
                    "active": int(now.timestamp()) + 3600,
                    "unlimited": 0,
                    "unknown": None,
                    "invalid": -1,
                    "missing": None,
                }.items():
                    session.add(
                        Subscription(
                            id=name,
                            name=name,
                            url_ciphertext="encrypted",
                            enabled=name != "disabled",
                            status="error" if name == "expired" else "healthy",
                        )
                    )
                    if name != "missing":
                        session.add(
                            SubscriptionUsage(subscription_id=name, expire=expire)
                        )
                session.add(Profile(id="profile", name="Profile", token="token"))
                session.add(UpstreamProxy(id="proxy", name="Proxy", url_ciphertext="x"))
                await session.flush()
                session.add(
                    Node(
                        id="node",
                        subscription_id="expired",
                        fingerprint="fingerprint",
                        name="Node",
                        protocol="vless",
                        uri_ciphertext="encrypted",
                    )
                )
                session.add(
                    ProfileSubscription(profile_id="profile", subscription_id="expired")
                )
                session.add(
                    SubscriptionProxy(subscription_id="expired", proxy_id="proxy")
                )
                session.add(
                    SubscriptionDeviceSettings(
                        subscription_id="expired",
                        user_agent="agent",
                        hwid="device",
                        os="OS",
                        os_version="1",
                        model="Model",
                    )
                )
                await session.flush()
                session.add(ProfileNodePreference(profile_id="profile", node_id="node"))
                await session.commit()

            assert (
                await expiration.delete_expired_subscriptions(runtime.database, now=now)
                == 2
            )
            async with runtime.database.sessions() as session:
                assert set(await session.scalars(select(Subscription.id))) == {
                    "boundary",
                    "recent",
                    "active",
                    "unlimited",
                    "unknown",
                    "invalid",
                    "missing",
                }
                for model in (
                    Node,
                    ProfileNodePreference,
                    ProfileSubscription,
                    SubscriptionProxy,
                    SubscriptionDeviceSettings,
                ):
                    assert (await session.scalars(select(model))).all() == []
                assert await session.get(SubscriptionUsage, "expired") is None
                assert await session.get(Profile, "profile") is not None
                assert await session.get(UpstreamProxy, "proxy") is not None

                # A fetch started before cleanup cannot recreate the source or nodes.
                prepared = PreparedSubscriptionSync(
                    subscription_id="expired",
                    nodes=tuple(parse_subscription(b"vless://id@host:443#Node")),
                    usage=None,
                    synced_at=now,
                )
                assert (
                    await persist_subscription_syncs(
                        session, [prepared], {}, runtime.secret_box, {"expired": now}
                    )
                    == set()
                )
                assert (await session.scalars(select(Node))).all() == []

            # Exactly 72 hours is retained; a fraction of a second later is expired.
            assert (
                await expiration.delete_expired_subscriptions(
                    runtime.database, now=now + timedelta(microseconds=1)
                )
                == 1
            )
            assert (
                await expiration.delete_expired_subscriptions(
                    runtime.database, now=now + timedelta(microseconds=1)
                )
                == 0
            )
        finally:
            await runtime.database.close()

    asyncio.run(scenario())


def test_cleanup_rechecks_expiry_after_locking_source(tmp_path, monkeypatch):
    runtime = create_app(settings_for(tmp_path)).state.runtime
    original_execute = AsyncSession.execute
    renewed = False

    async def execute(session, statement, *args, **kwargs):
        nonlocal renewed
        if (
            not renewed
            and isinstance(statement, Update)
            and statement.table.name == "subscriptions"
        ):
            renewed = True
            async with runtime.database.sessions() as renewal:
                await renewal.execute(
                    update(SubscriptionUsage).values(expire=2_000_000_000)
                )
                await renewal.commit()
        return await original_execute(session, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", execute)

    async def scenario():
        await runtime.database.create_schema()
        try:
            async with runtime.database.sessions() as session:
                session.add(
                    Subscription(id="source", name="Source", url_ciphertext="x")
                )
                await session.flush()
                session.add(SubscriptionUsage(subscription_id="source", expire=1))
                await session.commit()
            assert await expiration.delete_expired_subscriptions(runtime.database) == 0
            assert renewed
            async with runtime.database.sessions() as session:
                assert await session.get(Subscription, "source") is not None
        finally:
            await runtime.database.close()

    asyncio.run(scenario())


def test_startup_cleanup_does_not_reimport_deleted_source(tmp_path):
    settings = settings_for(tmp_path)
    app = create_app(settings)

    async def seed(client):
        await login(client)
        source = (await client.get("/api/subscriptions")).json()[0]
        async with app.state.runtime.database.sessions() as session:
            session.add(SubscriptionUsage(subscription_id=source["id"], expire=1))
            await session.commit()

    async def verify(client):
        await login(client)
        assert (await client.get("/api/subscriptions")).json() == []
        profile = (await client.get("/api/profiles")).json()[0]
        assert profile["subscription_ids"] == []

    asyncio.run(with_client(app, seed))
    asyncio.run(with_client(create_app(settings), verify))
    asyncio.run(with_client(create_app(settings), verify))


def test_periodic_cleanup_retries_failures_and_stops_on_shutdown(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(expiration, "CLEANUP_INTERVAL_SECONDS", 0.01)
    original_delete = expiration.delete_expired_subscriptions
    deleted = asyncio.Event()
    attempts = 0
    app = create_app(settings_for(tmp_path))

    async def delete(database):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError("Temporary database failure")
        count = await original_delete(database)
        if count:
            deleted.set()
        return count

    monkeypatch.setattr(expiration, "delete_expired_subscriptions", delete)

    async def scenario():
        async with app.router.lifespan_context(app):
            task = next(
                task
                for task in asyncio.all_tasks()
                if task.get_coro().__name__ == "subscription_cleanup_loop"
            )
            async with app.state.runtime.database.sessions() as session:
                source = await session.scalar(select(Subscription))
                session.add(SubscriptionUsage(subscription_id=source.id, expire=1))
                await session.commit()
            await asyncio.wait_for(deleted.wait(), timeout=5)
            assert attempts >= 3
            assert "Expired subscription cleanup failed" in caplog.text
        assert task.cancelled()

    asyncio.run(scenario())
