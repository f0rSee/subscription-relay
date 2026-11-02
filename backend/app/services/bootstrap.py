from __future__ import annotations

from sqlalchemy import func, select

from ..models import Profile, ProfileSubscription, Subscription
from ..runtime import AppRuntime
from .settings import get_relay_settings, lock_device_settings_changes


async def bootstrap(runtime: AppRuntime) -> None:
    async with runtime.database.sessions() as session:
        await get_relay_settings(session)
        await lock_device_settings_changes(session)

        profile = await session.scalar(
            select(Profile).where(Profile.token == runtime.settings.relay_token)
        )
        profile_created = profile is None
        if profile is None:
            profile = Profile(name="Default", token=runtime.settings.relay_token)
            session.add(profile)
            await session.flush()

        subscription_count = await session.scalar(
            select(func.count()).select_from(Subscription)
        )
        # Seed only on initial setup, so a deleted source stays deleted on restart.
        if profile_created and not subscription_count and runtime.settings.upstream_url:
            subscription = Subscription(
                name="Primary subscription",
                url_ciphertext=runtime.secret_box.encrypt(
                    runtime.settings.upstream_url
                ),
                priority=100,
            )
            session.add(subscription)
            await session.flush()
            session.add(
                ProfileSubscription(
                    profile_id=profile.id,
                    subscription_id=subscription.id,
                    position=0,
                )
            )
        elif profile_created:
            subscriptions = (
                await session.scalars(
                    select(Subscription).order_by(Subscription.priority)
                )
            ).all()
            for position, subscription in enumerate(subscriptions):
                session.add(
                    ProfileSubscription(
                        profile_id=profile.id,
                        subscription_id=subscription.id,
                        position=position,
                    )
                )
        await session.commit()
