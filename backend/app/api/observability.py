from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete, select, update

from ..dependencies import SessionDep
from ..models import ClientDevice, RequestLog
from ..schemas import (
    ClientDeviceResponse,
    DeletedCountResponse,
    RequestLogResponse,
)

router = APIRouter(tags=["observability"])


@router.get("/request-logs")
async def list_request_logs(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[RequestLogResponse]:
    logs = (
        await session.scalars(
            select(RequestLog).order_by(RequestLog.requested_at.desc()).limit(limit)
        )
    ).all()
    return [
        RequestLogResponse(
            id=log.id,
            profile_id=log.profile_id,
            profile_name=log.profile_name,
            request_type=log.request_type,
            device_id=log.device_id,
            client_name=log.client_name,
            user_agent=log.user_agent,
            ip_address=log.ip_address,
            status_code=log.status_code,
            node_count=log.node_count,
            error=log.error,
            requested_at=log.requested_at,
        )
        for log in logs
    ]


@router.get("/devices")
async def list_devices(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ClientDeviceResponse]:
    devices = (
        await session.scalars(
            select(ClientDevice).order_by(ClientDevice.last_seen_at.desc()).limit(limit)
        )
    ).all()
    return [
        ClientDeviceResponse(
            id=device.id,
            name=device.name,
            user_agent=device.user_agent,
            ip_address=device.ip_address,
            request_count=device.request_count,
            last_profile_name=device.last_profile_name,
            last_status_code=device.last_status_code,
            first_seen_at=device.first_seen_at,
            last_seen_at=device.last_seen_at,
        )
        for device in devices
    ]


@router.delete("/request-logs")
async def clear_request_logs(session: SessionDep) -> DeletedCountResponse:
    result = await session.execute(delete(RequestLog))
    await session.commit()
    count = result.rowcount if result.rowcount is not None else 0
    return DeletedCountResponse(deleted=count)


@router.delete("/devices")
async def clear_devices(session: SessionDep) -> DeletedCountResponse:
    await session.execute(update(RequestLog).values(device_id=None))
    result = await session.execute(delete(ClientDevice))
    await session.commit()
    count = result.rowcount if result.rowcount is not None else 0
    return DeletedCountResponse(deleted=count)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: str,
    session: SessionDep,
) -> Response:
    device = await session.get(ClientDevice, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    await session.execute(
        update(RequestLog)
        .where(RequestLog.device_id == device_id)
        .values(device_id=None)
    )
    await session.delete(device)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
