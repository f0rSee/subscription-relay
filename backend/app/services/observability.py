from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from fastapi import Request

from ..models import ClientDevice, Profile, RequestLog
from ..runtime import AppRuntime
from .settings import get_relay_settings

logger = logging.getLogger(__name__)


def _client_identity(request: Request) -> tuple[str, str, str]:
    user_agent = request.headers.get("user-agent", "Unknown client").strip()[:512]
    ip_address = (request.client.host if request.client else "unknown")[:64]
    product = user_agent.split(" ", 1)[0].split("/", 1)[0].strip()
    return (product or "Unknown client")[:160], user_agent, ip_address


async def record_subscription_request(
    request: Request,
    runtime: AppRuntime,
    profile: Profile,
    *,
    request_type: str,
    status_code: int,
    node_count: int = 0,
    error: str | None = None,
) -> None:
    client_name, user_agent, ip_address = _client_identity(request)
    now = datetime.now(UTC)

    try:
        async with runtime.database.sessions() as session:
            settings = await get_relay_settings(session)
            device_id: str | None = None

            if settings.device_tracking_enabled:
                device_id = hashlib.sha256(
                    (
                        f"{runtime.settings.session_secret}\0{ip_address}\0{user_agent}"
                    ).encode()
                ).hexdigest()
                device = await session.get(ClientDevice, device_id)
                if device is None:
                    device = ClientDevice(
                        id=device_id,
                        name=client_name,
                        user_agent=user_agent,
                        ip_address=ip_address,
                        request_count=1,
                        last_profile_name=profile.name,
                        last_status_code=status_code,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                    session.add(device)
                else:
                    device.name = client_name
                    device.user_agent = user_agent
                    device.ip_address = ip_address
                    device.request_count += 1
                    device.last_profile_name = profile.name
                    device.last_status_code = status_code
                    device.last_seen_at = now

            if settings.request_logging_enabled:
                session.add(
                    RequestLog(
                        profile_id=profile.id,
                        profile_name=profile.name,
                        request_type=request_type,
                        device_id=device_id,
                        client_name=client_name,
                        user_agent=user_agent,
                        ip_address=ip_address,
                        status_code=status_code,
                        node_count=node_count,
                        error=error[:1000] if error else None,
                        requested_at=now,
                    )
                )
            await session.commit()
    except Exception:
        logger.exception("Failed to persist subscription request metadata")
