from __future__ import annotations

from sqlalchemy import func, select

from ..models import Profile, ProfileSubscription, RelaySettings, Subscription
from ..runtime import AppRuntime


async def bootstrap(runtime: AppRuntime) -> None:
    async with runtime.database.sessions() as session:
        if await session.get(RelaySettings, 1) is None:
            session.add(RelaySettings(id=1))

        profile = await session.scalar(
            select(Profile).where(Profile.token == runtime.settings.relay_token)
        )
        if profile is None:
            profile = Profile(name="Default", token=runtime.settings.relay_token)
            session.add(profile)
            await session.flush()

        subscription_count = await session.scalar(
            select(func.count()).select_from(Subscription)
        )
        if not subscription_count and runtime.settings.upstream_url:
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
        else:
            linked_ids = set(
                (
                    await session.scalars(
                        select(ProfileSubscription.subscription_id).where(
                            ProfileSubscription.profile_id == profile.id
                        )
                    )
                ).all()
            )
            subscriptions = (
                await session.scalars(
                    select(Subscription).order_by(Subscription.priority)
                )
            ).all()
            for position, subscription in enumerate(subscriptions):
                if subscription.id not in linked_ids:
                    session.add(
                        ProfileSubscription(
                            profile_id=profile.id,
                            subscription_id=subscription.id,
                            position=position,
                        )
                    )
        await session.commit()
