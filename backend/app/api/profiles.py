from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import SessionDep, SettingsDep
from ..models import (
    Profile,
    ProfileNodePreference,
    ProfileSubscription,
    Subscription,
)
from ..schemas import (
    NodeOrderUpdate,
    ProfileCreate,
    ProfileNodeResponse,
    ProfileResponse,
    ProfileUpdate,
    UpdatedResponse,
)
from ..services.profiles import profile_nodes

router = APIRouter(prefix="/profiles", tags=["profiles"])


async def _validate_source_ids(
    session: AsyncSession,
    source_ids: list[str],
) -> None:
    if not source_ids:
        return
    existing = set(
        (
            await session.scalars(
                select(Subscription.id).where(Subscription.id.in_(source_ids))
            )
        ).all()
    )
    if existing != set(source_ids):
        raise HTTPException(status_code=422, detail="Unknown subscription")


def _profile_response(
    profile: Profile,
    source_ids: list[str],
) -> ProfileResponse:
    return ProfileResponse(
        id=profile.id,
        name=profile.name,
        token=profile.token,
        enabled=profile.enabled,
        subscription_ids=source_ids,
        url=f"/s/{profile.token}",
        created_at=profile.created_at,
    )


@router.get("")
async def list_profiles(session: SessionDep) -> list[ProfileResponse]:
    profiles = (
        await session.scalars(select(Profile).order_by(Profile.created_at))
    ).all()
    links = (
        await session.execute(
            select(
                ProfileSubscription.profile_id,
                ProfileSubscription.subscription_id,
            ).order_by(ProfileSubscription.position)
        )
    ).all()
    source_ids_by_profile: dict[str, list[str]] = {}
    for profile_id, subscription_id in links:
        source_ids_by_profile.setdefault(profile_id, []).append(subscription_id)
    return [
        _profile_response(profile, source_ids_by_profile.get(profile.id, []))
        for profile in profiles
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: ProfileCreate,
    session: SessionDep,
) -> ProfileResponse:
    source_ids = payload.subscription_ids or list(
        (await session.scalars(select(Subscription.id))).all()
    )
    await _validate_source_ids(session, source_ids)

    profile = Profile(name=payload.name, token=secrets.token_urlsafe(32))
    session.add(profile)
    await session.flush()
    for position, source_id in enumerate(source_ids):
        session.add(
            ProfileSubscription(
                profile_id=profile.id,
                subscription_id=source_id,
                position=position,
            )
        )
    await session.commit()
    return _profile_response(profile, source_ids)


@router.patch("/{profile_id}")
async def update_profile(
    profile_id: str,
    payload: ProfileUpdate,
    session: SessionDep,
    settings: SettingsDep,
) -> ProfileResponse:
    profile = await session.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    if payload.subscription_ids is not None:
        await _validate_source_ids(session, payload.subscription_ids)
    if payload.name is not None:
        profile.name = payload.name
    if payload.enabled is not None:
        profile.enabled = payload.enabled
    if payload.rotate_token:
        if secrets.compare_digest(profile.token, settings.relay_token):
            raise HTTPException(
                status_code=409,
                detail="Default profile token is configured through RELAY_TOKEN",
            )
        profile.token = secrets.token_urlsafe(32)
    if payload.subscription_ids is not None:
        await session.execute(
            delete(ProfileSubscription).where(
                ProfileSubscription.profile_id == profile_id
            )
        )
        for position, source_id in enumerate(payload.subscription_ids):
            session.add(
                ProfileSubscription(
                    profile_id=profile_id,
                    subscription_id=source_id,
                    position=position,
                )
            )
    await session.commit()
    source_ids = list(
        (
            await session.scalars(
                select(ProfileSubscription.subscription_id)
                .where(ProfileSubscription.profile_id == profile_id)
                .order_by(ProfileSubscription.position)
            )
        ).all()
    )
    return _profile_response(profile, source_ids)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    profile = await session.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if secrets.compare_digest(profile.token, settings.relay_token):
        raise HTTPException(
            status_code=409,
            detail="Default profile cannot be deleted",
        )
    await session.delete(profile)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{profile_id}/nodes")
async def list_profile_nodes(
    profile_id: str,
    session: SessionDep,
) -> list[ProfileNodeResponse]:
    if await session.get(Profile, profile_id) is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    rows = await profile_nodes(session, profile_id)
    seen: set[str] = set()
    result: list[ProfileNodeResponse] = []
    for node, subscription, _ in rows:
        duplicate = node.fingerprint in seen
        seen.add(node.fingerprint)
        result.append(
            ProfileNodeResponse(
                id=node.id,
                name=node.name,
                protocol=node.protocol,
                host=node.host,
                subscription_id=subscription.id,
                subscription_name=subscription.name,
                duplicate=duplicate,
            )
        )
    return result


@router.put("/{profile_id}/node-order")
async def update_node_order(
    profile_id: str,
    payload: NodeOrderUpdate,
    session: SessionDep,
) -> UpdatedResponse:
    if len(payload.node_ids) != len(set(payload.node_ids)):
        raise HTTPException(status_code=422, detail="Node ids must be unique")
    if await session.get(Profile, profile_id) is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    valid_rows = await profile_nodes(session, profile_id)
    valid_ids = {node.id for node, _, _ in valid_rows}
    if not set(payload.node_ids).issubset(valid_ids):
        raise HTTPException(status_code=422, detail="Unknown node in order")

    await session.execute(
        delete(ProfileNodePreference).where(
            ProfileNodePreference.profile_id == profile_id
        )
    )
    for position, node_id in enumerate(payload.node_ids):
        session.add(
            ProfileNodePreference(
                profile_id=profile_id,
                node_id=node_id,
                position=position,
            )
        )
    await session.commit()
    return UpdatedResponse(updated=len(payload.node_ids))
