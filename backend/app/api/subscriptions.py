from __future__ import annotations

from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select

from ..dependencies import SecretBoxDep, SessionDep, SettingsDep
from ..models import Profile, ProfileSubscription, Subscription, SubscriptionUsage
from ..schemas import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionUpdate,
    SyncResponse,
)
from ..services.presenters import subscription_response
from ..services.subscriptions import sync_subscription

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _validate_source_url(url: str, *, allow_insecure_http: bool) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="URL must be valid http(s)")
    if parsed.scheme == "http" and not allow_insecure_http:
        raise HTTPException(status_code=422, detail="Only HTTPS sources are allowed")


@router.get("")
async def list_subscriptions(
    session: SessionDep,
    secret_box: SecretBoxDep,
) -> list[SubscriptionResponse]:
    rows = (
        await session.execute(
            select(Subscription, SubscriptionUsage)
            .outerjoin(
                SubscriptionUsage,
                SubscriptionUsage.subscription_id == Subscription.id,
            )
            .order_by(
                Subscription.priority,
                Subscription.created_at,
            )
        )
    ).all()
    return [
        subscription_response(subscription, usage, secret_box)
        for subscription, usage in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_subscription(
    payload: SubscriptionCreate,
    session: SessionDep,
    settings: SettingsDep,
    secret_box: SecretBoxDep,
) -> SubscriptionResponse:
    _validate_source_url(
        payload.url,
        allow_insecure_http=settings.allow_insecure_http,
    )
    subscription = Subscription(
        name=payload.name,
        url_ciphertext=secret_box.encrypt(payload.url),
        enabled=payload.enabled,
        priority=payload.priority,
    )
    session.add(subscription)
    await session.flush()

    default_profile = await session.scalar(
        select(Profile).where(Profile.token == settings.relay_token)
    )
    if default_profile is not None:
        position = await session.scalar(
            select(func.count())
            .select_from(ProfileSubscription)
            .where(ProfileSubscription.profile_id == default_profile.id)
        )
        session.add(
            ProfileSubscription(
                profile_id=default_profile.id,
                subscription_id=subscription.id,
                position=position or 0,
            )
        )
    await session.commit()
    return subscription_response(subscription, None, secret_box)


@router.patch("/{subscription_id}")
async def update_subscription(
    subscription_id: str,
    payload: SubscriptionUpdate,
    session: SessionDep,
    settings: SettingsDep,
    secret_box: SecretBoxDep,
) -> SubscriptionResponse:
    subscription = await session.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")

    usage = await session.get(SubscriptionUsage, subscription_id)
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "url" in updates:
        url = updates.pop("url")
        if url is None:
            raise HTTPException(status_code=422, detail="URL cannot be null")
        _validate_source_url(
            url,
            allow_insecure_http=settings.allow_insecure_http,
        )
        subscription.url_ciphertext = secret_box.encrypt(url)
        subscription.status = "never"
        if usage is not None:
            await session.delete(usage)
            usage = None
    for key, value in updates.items():
        setattr(subscription, key, value)
    await session.commit()
    return subscription_response(subscription, usage, secret_box)


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    subscription_id: str,
    session: SessionDep,
) -> Response:
    subscription = await session.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    await session.delete(subscription)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{subscription_id}/sync")
async def sync_source(
    subscription_id: str,
    session: SessionDep,
    settings: SettingsDep,
    secret_box: SecretBoxDep,
) -> SyncResponse:
    subscription = await session.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    try:
        count = await sync_subscription(
            session,
            subscription,
            settings,
            secret_box,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream returned HTTP {exc.response.status_code}",
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SyncResponse(status="healthy", node_count=count)
