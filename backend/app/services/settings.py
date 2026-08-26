from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import RelaySettings
from ..schemas import RelaySettingsResponse


async def get_relay_settings(session: AsyncSession) -> RelaySettings:
    settings = await session.get(RelaySettings, 1)
    if settings is None:
        settings = RelaySettings(id=1)
        session.add(settings)
        await session.flush()
    return settings


def relay_settings_response(settings: RelaySettings) -> RelaySettingsResponse:
    return RelaySettingsResponse(
        deduplicate_servers=settings.deduplicate_servers,
        request_logging_enabled=settings.request_logging_enabled,
        device_tracking_enabled=settings.device_tracking_enabled,
        auto_refresh_enabled=settings.auto_refresh_enabled,
        updated_at=settings.updated_at,
    )
