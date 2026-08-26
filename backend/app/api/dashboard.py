from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from ..dependencies import SessionDep, SettingsDep
from ..models import ClientDevice, Node, Profile, RequestLog, Subscription
from ..schemas import DashboardResponse

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
async def dashboard(
    session: SessionDep,
    settings: SettingsDep,
) -> DashboardResponse:
    subscriptions = await session.scalar(select(func.count()).select_from(Subscription))
    healthy = await session.scalar(
        select(func.count())
        .select_from(Subscription)
        .where(Subscription.status == "healthy")
    )
    nodes = await session.scalar(select(func.count()).select_from(Node))
    profiles = await session.scalar(select(func.count()).select_from(Profile))
    request_logs = await session.scalar(select(func.count()).select_from(RequestLog))
    devices = await session.scalar(select(func.count()).select_from(ClientDevice))
    return DashboardResponse(
        subscriptions=subscriptions or 0,
        healthy_subscriptions=healthy or 0,
        nodes=nodes or 0,
        profiles=profiles or 0,
        request_logs=request_logs or 0,
        devices=devices or 0,
        persistent_storage=settings.persistent_database,
    )
