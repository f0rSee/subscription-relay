from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TypeAlias

from fastapi import BackgroundTasks, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Node,
    Profile,
    ProfileNodePreference,
    ProfileSubscription,
    RelaySettings,
    Subscription,
)
from ..runtime import AppRuntime
from .observability import record_subscription_request
from .subscriptions import (
    PreparedSubscriptionSync,
    encode_subscription,
    persist_subscription_syncs,
    prepare_subscription_sync,
)

ProfileNodeRow: TypeAlias = tuple[
    Node,
    Subscription,
    ProfileNodePreference | None,
    ProfileSubscription,
]


def _was_refreshed_since(value: datetime | None, threshold: datetime) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value >= threshold


async def profile_nodes(
    session: AsyncSession,
    profile_id: str,
) -> list[ProfileNodeRow]:
    preference_join = and_(
        ProfileNodePreference.profile_id == profile_id,
        ProfileNodePreference.node_id == Node.id,
    )
    rows = (
        await session.execute(
            select(
                Node,
                Subscription,
                ProfileNodePreference,
                ProfileSubscription,
            )
            .join(Subscription, Subscription.id == Node.subscription_id)
            .join(
                ProfileSubscription,
                and_(
                    ProfileSubscription.profile_id == profile_id,
                    ProfileSubscription.subscription_id == Subscription.id,
                ),
            )
            .outerjoin(ProfileNodePreference, preference_join)
            .where(Subscription.enabled.is_(True), Node.enabled.is_(True))
        )
    ).all()

    def sort_key(row: ProfileNodeRow) -> tuple:
        node, subscription, preference, profile_subscription = row
        explicit = preference.position if preference else None
        return (
            profile_subscription.position,
            explicit if explicit is not None else 1_000_000,
            subscription.priority,
            node.source_position,
            node.name.casefold(),
        )

    return sorted(rows, key=sort_key)


async def refresh_profile_sources(
    runtime: AppRuntime,
    profile_id: str,
    *,
    auto_refresh_enabled: bool,
) -> None:
    if not auto_refresh_enabled:
        return

    requested_at = datetime.now(UTC)
    # Only one request schedules refreshes at a time. A request that waited for
    # a newer completed refresh can reuse it instead of creating a stampede.
    async with runtime.refresh_lock:
        async with runtime.database.sessions() as session:
            subscriptions = (
                await session.scalars(
                    select(Subscription)
                    .join(
                        ProfileSubscription,
                        ProfileSubscription.subscription_id == Subscription.id,
                    )
                    .where(
                        ProfileSubscription.profile_id == profile_id,
                        Subscription.enabled.is_(True),
                    )
                    .order_by(
                        ProfileSubscription.position,
                        Subscription.priority,
                    )
                )
            ).all()

        subscriptions_to_refresh = [
            subscription
            for subscription in subscriptions
            if not _was_refreshed_since(subscription.last_sync_at, requested_at)
        ]
        if not subscriptions_to_refresh:
            return

        # Network waits dominate synchronization, so fetch independent sources
        # concurrently. The database update remains one atomic transaction.
        semaphore = asyncio.Semaphore(8)

        async def prepare(
            subscription: Subscription,
        ) -> PreparedSubscriptionSync:
            async with semaphore:
                return await prepare_subscription_sync(
                    subscription,
                    runtime.settings,
                    runtime.secret_box,
                )

        results = await asyncio.gather(
            *(prepare(subscription) for subscription in subscriptions_to_refresh),
            return_exceptions=True,
        )
        prepared_syncs: list[PreparedSubscriptionSync] = []
        errors: dict[str, Exception] = {}
        for subscription, result in zip(
            subscriptions_to_refresh,
            results,
            strict=True,
        ):
            if isinstance(result, Exception):
                errors[subscription.id] = result
            else:
                prepared_syncs.append(result)

        async with runtime.database.sessions() as session:
            await persist_subscription_syncs(
                session,
                prepared_syncs,
                errors,
                runtime.secret_box,
            )


async def render_profile(
    request: Request,
    background_tasks: BackgroundTasks,
    runtime: AppRuntime,
    profile: Profile,
    relay_settings: RelaySettings,
    *,
    request_type: str,
) -> Response:
    if not profile.enabled:
        background_tasks.add_task(
            record_subscription_request,
            request,
            runtime,
            profile,
            request_type=request_type,
            status_code=404,
            error="Profile disabled",
            request_logging_enabled=relay_settings.request_logging_enabled,
            device_tracking_enabled=relay_settings.device_tracking_enabled,
        )
        return JSONResponse(status_code=404, content={"detail": "Profile disabled"})

    await refresh_profile_sources(
        runtime,
        profile.id,
        auto_refresh_enabled=relay_settings.auto_refresh_enabled,
    )
    async with runtime.database.sessions() as session:
        rows = await profile_nodes(session, profile.id)
        uris: list[str] = []
        seen: set[str] = set()
        for node, _, _, _ in rows:
            if relay_settings.deduplicate_servers and node.fingerprint in seen:
                continue
            seen.add(node.fingerprint)
            try:
                uris.append(runtime.secret_box.decrypt(node.uri_ciphertext))
            except ValueError:
                continue

    if not uris:
        error = "No healthy nodes are available for this profile"
        background_tasks.add_task(
            record_subscription_request,
            request,
            runtime,
            profile,
            request_type=request_type,
            status_code=502,
            error=error,
            request_logging_enabled=relay_settings.request_logging_enabled,
            device_tracking_enabled=relay_settings.device_tracking_enabled,
        )
        return JSONResponse(
            status_code=502,
            content={"detail": error},
            headers={"Cache-Control": "no-store"},
        )

    background_tasks.add_task(
        record_subscription_request,
        request,
        runtime,
        profile,
        request_type=request_type,
        status_code=200,
        node_count=len(uris),
        request_logging_enabled=relay_settings.request_logging_enabled,
        device_tracking_enabled=relay_settings.device_tracking_enabled,
    )
    return Response(
        content=encode_subscription(uris),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-store",
            "Profile-Title": profile.name,
            "Profile-Update-Interval": "15",
        },
    )
