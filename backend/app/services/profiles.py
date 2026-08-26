from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TypeAlias

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Node,
    Profile,
    ProfileNodePreference,
    ProfileSubscription,
    Subscription,
)
from ..runtime import AppRuntime
from .observability import record_subscription_request
from .settings import get_relay_settings
from .subscriptions import encode_subscription, sync_subscription

ProfileNodeRow: TypeAlias = tuple[
    Node,
    Subscription,
    ProfileNodePreference | None,
]


def _is_stale(value: datetime | None, refresh_seconds: int) -> bool:
    if value is None:
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value < datetime.now(UTC) - timedelta(seconds=refresh_seconds)


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
            select(Node, Subscription, ProfileNodePreference)
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
        node, subscription, preference = row
        explicit = preference.position if preference else None
        return (
            explicit if explicit is not None else 1_000_000,
            subscription.priority,
            node.source_position,
            node.name.casefold(),
        )

    return sorted(rows, key=sort_key)


async def refresh_profile_sources(runtime: AppRuntime, profile_id: str) -> None:
    async with runtime.database.sessions() as session:
        if not (await get_relay_settings(session)).auto_refresh_enabled:
            return
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
                .order_by(Subscription.priority)
            )
        ).all()

    for subscription in subscriptions:
        if not _is_stale(
            subscription.last_sync_at,
            runtime.settings.refresh_seconds,
        ):
            continue
        async with runtime.database.sessions() as session:
            current = await session.get(Subscription, subscription.id)
            if current is None:
                continue
            try:
                await sync_subscription(
                    session,
                    current,
                    runtime.settings,
                    runtime.secret_box,
                )
            except (httpx.HTTPError, ValueError):
                continue


async def render_profile(
    request: Request,
    runtime: AppRuntime,
    profile: Profile,
    *,
    request_type: str,
) -> Response:
    if not profile.enabled:
        await record_subscription_request(
            request,
            runtime,
            profile,
            request_type=request_type,
            status_code=404,
            error="Profile disabled",
        )
        return JSONResponse(status_code=404, content={"detail": "Profile disabled"})

    await refresh_profile_sources(runtime, profile.id)
    async with runtime.database.sessions() as session:
        settings = await get_relay_settings(session)
        rows = await profile_nodes(session, profile.id)
        uris: list[str] = []
        seen: set[str] = set()
        for node, _, _ in rows:
            if settings.deduplicate_servers and node.fingerprint in seen:
                continue
            seen.add(node.fingerprint)
            try:
                uris.append(runtime.secret_box.decrypt(node.uri_ciphertext))
            except ValueError:
                continue

    if not uris:
        error = "No healthy nodes are available for this profile"
        await record_subscription_request(
            request,
            runtime,
            profile,
            request_type=request_type,
            status_code=502,
            error=error,
        )
        return JSONResponse(
            status_code=502,
            content={"detail": error},
            headers={"Cache-Control": "no-store"},
        )

    await record_subscription_request(
        request,
        runtime,
        profile,
        request_type=request_type,
        status_code=200,
        node_count=len(uris),
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
