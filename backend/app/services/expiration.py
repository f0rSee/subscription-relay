from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from ..database import Database
from ..models import Subscription, SubscriptionUsage

logger = logging.getLogger(__name__)

EXPIRATION_GRACE_PERIOD = timedelta(days=3)
CLEANUP_INTERVAL_SECONDS = 60 * 60


async def delete_expired_subscriptions(
    database: Database, *, now: datetime | None = None
) -> int:
    cutoff = ((now or datetime.now(UTC)) - EXPIRATION_GRACE_PERIOD).timestamp()
    deleted = 0
    async with database.sessions() as session:
        subscription_ids = (
            await session.scalars(
                select(SubscriptionUsage.subscription_id)
                .where(SubscriptionUsage.expire > 0, SubscriptionUsage.expire < cutoff)
                .order_by(SubscriptionUsage.subscription_id)
            )
        ).all()
        for subscription_id in subscription_ids:
            # Serialize with syncs and source edits before rechecking expiry.
            # A no-op write also acquires the write lock on SQLite.
            result = await session.execute(
                update(Subscription)
                .where(Subscription.id == subscription_id)
                .values(updated_at=Subscription.updated_at)
                .execution_options(synchronize_session=False)
            )
            if not result.rowcount:
                continue
            expire = await session.scalar(
                select(SubscriptionUsage.expire).where(
                    SubscriptionUsage.subscription_id == subscription_id
                )
            )
            if expire is None or not 0 < expire < cutoff:
                continue
            subscription = await session.get(Subscription, subscription_id)
            # Use ORM cascades: SQLite may have foreign-key cascades disabled.
            await session.delete(subscription)
            deleted += 1
        await session.commit()
    return deleted


async def cleanup_expired_subscriptions(database: Database) -> None:
    try:
        deleted = await delete_expired_subscriptions(database)
        if deleted:
            logger.info("Deleted %d expired subscriptions", deleted)
    except Exception:
        # A transient database failure must not stop the app or future runs.
        logger.exception("Expired subscription cleanup failed")


async def subscription_cleanup_loop(database: Database) -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        await cleanup_expired_subscriptions(database)
