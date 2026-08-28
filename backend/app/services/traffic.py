from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ProfileSubscription, Subscription, SubscriptionUsage


@dataclass(frozen=True)
class ProfileTraffic:
    upload: int
    download: int
    total: int | None
    unlimited: bool
    expire: int | None
    updated_at: datetime | None
    sources_reporting: int
    sources_total: int

    @property
    def used(self) -> int:
        return self.upload + self.download

    @property
    def remaining(self) -> int | None:
        if self.total is None:
            return None
        return max(self.total - self.used, 0)


def aggregate_profile_traffic(
    usages: Iterable[SubscriptionUsage | None],
) -> ProfileTraffic:
    values = list(usages)
    reporting = [usage for usage in values if usage is not None]
    upload = sum(usage.upload for usage in reporting)
    download = sum(usage.download for usage in reporting)
    totals_complete = bool(values) and all(
        usage is not None and usage.total is not None for usage in values
    )
    unlimited = any(usage.total == 0 for usage in reporting)
    total = (
        None
        if not totals_complete or unlimited
        else sum(usage.total or 0 for usage in reporting)
    )
    expires = [usage.expire for usage in reporting if usage.expire]
    updated = [
        _ensure_utc(usage.updated_at)
        for usage in reporting
        if usage.updated_at is not None
    ]
    return ProfileTraffic(
        upload=upload,
        download=download,
        total=total,
        unlimited=unlimited,
        expire=min(expires) if expires else None,
        updated_at=min(updated) if updated else None,
        sources_reporting=len(reporting),
        sources_total=len(values),
    )


def _ensure_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def profile_traffic_summaries(
    session: AsyncSession,
    profile_ids: Iterable[str],
) -> dict[str, ProfileTraffic]:
    ids = list(profile_ids)
    usages_by_profile: dict[str, list[SubscriptionUsage | None]] = {
        profile_id: [] for profile_id in ids
    }
    if ids:
        rows = (
            await session.execute(
                select(ProfileSubscription.profile_id, SubscriptionUsage)
                .join(
                    Subscription,
                    Subscription.id == ProfileSubscription.subscription_id,
                )
                .outerjoin(
                    SubscriptionUsage,
                    SubscriptionUsage.subscription_id == Subscription.id,
                )
                .where(
                    ProfileSubscription.profile_id.in_(ids),
                    Subscription.enabled.is_(True),
                )
            )
        ).all()
        for profile_id, usage in rows:
            usages_by_profile[profile_id].append(usage)
    return {
        profile_id: aggregate_profile_traffic(usages)
        for profile_id, usages in usages_by_profile.items()
    }


async def profile_traffic_summary(
    session: AsyncSession,
    profile_id: str,
) -> ProfileTraffic:
    return (await profile_traffic_summaries(session, [profile_id]))[profile_id]


def subscription_userinfo_header(traffic: ProfileTraffic) -> str | None:
    if traffic.sources_reporting == 0:
        return None
    fields = [f"upload={traffic.upload}", f"download={traffic.download}"]
    if traffic.unlimited:
        fields.append("total=0")
    elif traffic.total is not None:
        fields.append(f"total={traffic.total}")
    if traffic.expire is not None:
        fields.append(f"expire={traffic.expire}")
    return "; ".join(fields)
