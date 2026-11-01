from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import exists, update

from ..dependencies import SessionDep
from ..models import DefaultDeviceSettings, Subscription, SubscriptionDeviceSettings
from ..schemas import RelaySettingsResponse, RelaySettingsUpdate
from ..services.settings import (
    get_default_device_settings,
    get_relay_settings,
    relay_settings_response,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def read_settings(session: SessionDep) -> RelaySettingsResponse:
    return relay_settings_response(
        await get_relay_settings(session), await get_default_device_settings(session)
    )


@router.patch("")
async def update_settings(
    payload: RelaySettingsUpdate,
    session: SessionDep,
) -> RelaySettingsResponse:
    settings = await get_relay_settings(session)
    if payload.default_device_settings is not None:
        current = await get_default_device_settings(session)
        if payload.default_device_settings != current:
            # Invalidate in-flight fetches and refresh inherited sources next time.
            await session.execute(
                update(Subscription)
                .where(
                    ~exists().where(
                        SubscriptionDeviceSettings.subscription_id == Subscription.id
                    )
                )
                .values(updated_at=datetime.now(UTC), status="never", last_error=None)
            )
            stored = await session.get(DefaultDeviceSettings, 1)
            if stored is None:
                stored = DefaultDeviceSettings(id=1)
                session.add(stored)
            for key, value in payload.default_device_settings.model_dump().items():
                setattr(stored, key, value)
    for key, value in payload.model_dump(
        exclude_none=True, exclude={"default_device_settings"}
    ).items():
        setattr(settings, key, value)
    settings.updated_at = datetime.now(UTC)
    await session.commit()
    return relay_settings_response(settings, await get_default_device_settings(session))
