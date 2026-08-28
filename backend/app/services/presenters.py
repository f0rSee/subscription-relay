from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

from ..models import Subscription, SubscriptionUsage
from ..schemas import (
    ProfileTrafficResponse,
    SubscriptionResponse,
    TrafficUsageResponse,
)
from ..security import SecretBox
from .traffic import ProfileTraffic


def _masked_url(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path
    if len(path) > 48:
        path = path[:45] + "…"
    suffix = "?•••" if parsed.query else ""
    return f"{parsed.scheme}://{parsed.netloc}{path}{suffix}"


def subscription_response(
    subscription: Subscription,
    usage: SubscriptionUsage | None,
    secret_box: SecretBox,
) -> SubscriptionResponse:
    try:
        url_hint = _masked_url(secret_box.decrypt(subscription.url_ciphertext))
    except ValueError:
        url_hint = "Encrypted value unavailable"

    return SubscriptionResponse(
        id=subscription.id,
        name=subscription.name,
        url_hint=url_hint,
        enabled=subscription.enabled,
        priority=subscription.priority,
        status=subscription.status,
        node_count=subscription.node_count,
        last_error=subscription.last_error,
        last_sync_at=subscription.last_sync_at,
        traffic=traffic_usage_response(usage) if usage else None,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


def _expire_at(value: int | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def traffic_usage_response(usage: SubscriptionUsage) -> TrafficUsageResponse:
    used = usage.upload + usage.download
    unlimited = usage.total == 0
    total = None if unlimited else usage.total
    updated_at = usage.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return TrafficUsageResponse(
        upload=usage.upload,
        download=usage.download,
        used=used,
        total=total,
        remaining=max(total - used, 0) if total is not None else None,
        unlimited=unlimited,
        expire_at=_expire_at(usage.expire),
        updated_at=updated_at,
    )


def profile_traffic_response(traffic: ProfileTraffic) -> ProfileTrafficResponse:
    return ProfileTrafficResponse(
        upload=traffic.upload,
        download=traffic.download,
        used=traffic.used,
        total=traffic.total,
        remaining=traffic.remaining,
        unlimited=traffic.unlimited,
        expire_at=_expire_at(traffic.expire),
        updated_at=traffic.updated_at,
        sources_reporting=traffic.sources_reporting,
        sources_total=traffic.sources_total,
    )
