from __future__ import annotations

from urllib.parse import urlsplit

from ..models import Subscription
from ..schemas import SubscriptionResponse
from ..security import SecretBox


def _masked_url(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path
    if len(path) > 48:
        path = path[:45] + "…"
    suffix = "?•••" if parsed.query else ""
    return f"{parsed.scheme}://{parsed.netloc}{path}{suffix}"


def subscription_response(
    subscription: Subscription,
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
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )
