from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import unquote, urlsplit

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models import Node, Subscription
from ..security import SecretBox

SUPPORTED_PROTOCOLS = (
    "vless",
    "vmess",
    "trojan",
    "ss",
    "ssr",
    "hysteria",
    "hysteria2",
    "tuic",
    "wireguard",
)
UPSTREAM_USER_AGENT = "Happ/5.6.0/ios/2731171157721"


@dataclass(frozen=True)
class ParsedNode:
    uri: str
    fingerprint: str
    name: str
    protocol: str
    host: str | None
    position: int


@dataclass(frozen=True)
class PreparedSubscriptionSync:
    subscription_id: str
    nodes: tuple[ParsedNode, ...]
    synced_at: datetime


def _decode_base64_text(value: str) -> str | None:
    compact = "".join(value.split())
    if not compact:
        return None
    padding = "=" * (-len(compact) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            return decoder(compact + padding).decode("utf-8")
        except Exception:
            continue
    return None


def _try_decode_base64(value: str) -> str | None:
    decoded = _decode_base64_text(value)
    return decoded if decoded and "://" in decoded else None


def _node_metadata(uri: str) -> tuple[str, str, str | None]:
    parsed = urlsplit(uri)
    protocol = parsed.scheme.lower()
    name = unquote(parsed.fragment).strip()
    host = parsed.hostname

    if protocol == "vmess":
        try:
            payload = uri.split("://", 1)[1]
            decoded = _decode_base64_text(payload)
            data = json.loads(decoded or "{}")
            name = str(data.get("ps") or name).strip()
            host = str(data.get("add") or "").strip() or host
        except (ValueError, TypeError, json.JSONDecodeError):
            pass

    if not name:
        name = f"{protocol.upper()} · {host or 'server'}"
    return name[:255], protocol, host


def parse_subscription(body: bytes) -> list[ParsedNode]:
    text = body.decode("utf-8", errors="replace").strip()
    decoded = _try_decode_base64(text)
    if decoded:
        text = decoded

    nodes: list[ParsedNode] = []
    for line in text.splitlines():
        uri = line.strip()
        if not uri or "://" not in uri:
            continue
        protocol = uri.split("://", 1)[0].lower()
        if protocol not in SUPPORTED_PROTOCOLS:
            continue
        normalized = uri.split("#", 1)[0]
        fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        name, protocol, host = _node_metadata(uri)
        nodes.append(
            ParsedNode(
                uri=uri,
                fingerprint=fingerprint,
                name=name,
                protocol=protocol,
                host=host,
                position=len(nodes),
            )
        )
    return nodes


def encode_subscription(uris: list[str]) -> bytes:
    content = "\n".join(uris) + ("\n" if uris else "")
    return base64.b64encode(content.encode("utf-8"))


async def fetch_subscription(
    url: str,
    settings: Settings,
) -> tuple[bytes, httpx.Headers]:
    headers = {"User-Agent": UPSTREAM_USER_AGENT, "Accept": "text/plain, */*"}
    timeout = httpx.Timeout(settings.timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > settings.max_response_bytes:
                    raise ValueError("Upstream response is too large")
            return bytes(body), response.headers


async def prepare_subscription_sync(
    subscription: Subscription,
    settings: Settings,
    secret_box: SecretBox,
) -> PreparedSubscriptionSync:
    url = secret_box.decrypt(subscription.url_ciphertext)
    body, _ = await fetch_subscription(url, settings)
    parsed_nodes = parse_subscription(body)
    if not parsed_nodes:
        raise ValueError("Upstream response does not contain supported nodes")
    return PreparedSubscriptionSync(
        subscription_id=subscription.id,
        nodes=tuple(parsed_nodes),
        synced_at=datetime.now(UTC),
    )


async def persist_subscription_syncs(
    session: AsyncSession,
    prepared_syncs: list[PreparedSubscriptionSync],
    errors: dict[str, Exception],
    secret_box: SecretBox,
) -> None:
    subscription_ids = {
        prepared.subscription_id for prepared in prepared_syncs
    } | set(errors)
    if not subscription_ids:
        return

    subscriptions = {
        subscription.id: subscription
        for subscription in (
            await session.scalars(
                select(Subscription).where(Subscription.id.in_(subscription_ids))
            )
        ).all()
    }
    successful_ids = {prepared.subscription_id for prepared in prepared_syncs}
    existing_by_subscription: dict[str, dict[str, Node]] = {
        subscription_id: {} for subscription_id in successful_ids
    }
    if successful_ids:
        existing_nodes = (
            await session.scalars(
                select(Node).where(Node.subscription_id.in_(successful_ids))
            )
        ).all()
        for node in existing_nodes:
            existing_by_subscription[node.subscription_id][node.id] = node

    stale_node_ids: set[str] = set()
    for prepared in prepared_syncs:
        subscription = subscriptions.get(prepared.subscription_id)
        if subscription is None:
            continue
        existing = existing_by_subscription[prepared.subscription_id]
        active_ids: set[str] = set()
        fingerprint_occurrences: dict[str, int] = {}

        for parsed in prepared.nodes:
            occurrence = fingerprint_occurrences.get(parsed.fingerprint, 0)
            fingerprint_occurrences[parsed.fingerprint] = occurrence + 1
            node_identity = (
                parsed.fingerprint
                if occurrence == 0
                else f"{parsed.fingerprint}:{occurrence}"
            )
            node_id = hashlib.sha256(
                f"{prepared.subscription_id}:{node_identity}".encode()
            ).hexdigest()
            active_ids.add(node_id)
            node = existing.get(node_id)
            if node is None:
                node = Node(
                    id=node_id,
                    subscription_id=prepared.subscription_id,
                    fingerprint=parsed.fingerprint,
                    name=parsed.name,
                    protocol=parsed.protocol,
                    host=parsed.host,
                    uri_ciphertext=secret_box.encrypt(parsed.uri),
                    source_position=parsed.position,
                    last_seen_at=prepared.synced_at,
                )
                session.add(node)
            else:
                node.name = parsed.name
                node.protocol = parsed.protocol
                node.host = parsed.host
                node.uri_ciphertext = secret_box.encrypt(parsed.uri)
                node.source_position = parsed.position
                node.last_seen_at = prepared.synced_at

        stale_node_ids.update(set(existing) - active_ids)

        subscription.status = "healthy"
        subscription.node_count = len(prepared.nodes)
        subscription.last_error = None
        subscription.last_sync_at = prepared.synced_at

    if stale_node_ids:
        await session.execute(delete(Node).where(Node.id.in_(stale_node_ids)))

    for subscription_id, error in errors.items():
        subscription = subscriptions.get(subscription_id)
        if subscription is not None:
            subscription.status = "error"
            subscription.last_error = str(error)[:1000]

    await session.commit()


async def sync_subscription(
    session: AsyncSession,
    subscription: Subscription,
    settings: Settings,
    secret_box: SecretBox,
) -> int:
    subscription_id = subscription.id
    try:
        prepared = await prepare_subscription_sync(
            subscription,
            settings,
            secret_box,
        )
        await persist_subscription_syncs(session, [prepared], {}, secret_box)
        return len(prepared.nodes)
    except Exception as exc:
        await session.rollback()
        await persist_subscription_syncs(
            session,
            [],
            {subscription_id: exc},
            secret_box,
        )
        raise
