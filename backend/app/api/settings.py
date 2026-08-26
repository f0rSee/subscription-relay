from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from ..dependencies import SessionDep
from ..schemas import RelaySettingsResponse, RelaySettingsUpdate
from ..services.settings import get_relay_settings, relay_settings_response

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def read_settings(session: SessionDep) -> RelaySettingsResponse:
    return relay_settings_response(await get_relay_settings(session))


@router.patch("")
async def update_settings(
    payload: RelaySettingsUpdate,
    session: SessionDep,
) -> RelaySettingsResponse:
    settings = await get_relay_settings(session)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(settings, key, value)
    settings.updated_at = datetime.now(UTC)
    await session.commit()
    return relay_settings_response(settings)
