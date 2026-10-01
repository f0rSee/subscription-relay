from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote, urlsplit

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models import (
    Node,
    Subscription,
    SubscriptionProxy,
    SubscriptionUsage,
    UpstreamProxy,
)
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
UPSTREAM_USER_AGENT = "VPNClient/2.0/ios/2731171157721"
UPSTREAM_HEADERS = {
    "User-Agent": UPSTREAM_USER_AGENT,
    "Accept": "text/plain, */*",
    "X-HWID": "4139def9-6877-4771-b313-49e3119ba158",
    "X-Device-OS": "iOS",
    "X-Ver-OS": "27.0",
    "X-Device-Model": "iPhone 17 Pro Max",
}
MAX_TRAFFIC_VALUE = 2**63 - 1


class StaleSubscriptionSync(ValueError):
    pass


@dataclass(frozen=True)
class ParsedNode:
    uri: str
    fingerprint: str
    name: str
    protocol: str
    host: str | None
    position: int


@dataclass(frozen=True)
class ParsedSubscriptionUsage:
    upload: int
    download: int
    total: int | None
    expire: int | None


@dataclass(frozen=True)
class PreparedSubscriptionSync:
    subscription_id: str
    nodes: tuple[ParsedNode, ...]
    usage: ParsedSubscriptionUsage | None
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


def _parse_traffic_value(value: str) -> int | None:
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    result = int(parsed)
    return result if result <= MAX_TRAFFIC_VALUE else None


def parse_subscription_userinfo(value: str | None) -> ParsedSubscriptionUsage | None:
    if not value:
        return None
    parsed_fields: dict[str, int] = {}
    for raw_field in value[:4096].split(";"):
        name, separator, raw_value = raw_field.partition("=")
        name = name.strip().lower()
        if not separator or name not in {"upload", "download", "total", "expire"}:
            continue
        parsed = _parse_traffic_value(raw_value.strip())
        if parsed is not None:
            parsed_fields[name] = parsed
    if not parsed_fields:
        return None
    expire = parsed_fields.get("expire")
    return ParsedSubscriptionUsage(
        upload=parsed_fields.get("upload", 0),
        download=parsed_fields.get("download", 0),
        total=parsed_fields.get("total"),
        expire=expire if expire else None,
    )


def encode_subscription(uris: list[str]) -> bytes:
    content = "\n".join(uris) + ("\n" if uris else "")
    return base64.b64encode(content.encode("utf-8"))


async def fetch_subscription(
    url: str,
    settings: Settings,
    proxy_url: str | None = None,
) -> tuple[bytes, httpx.Headers]:
    timeout = httpx.Timeout(settings.timeout_seconds)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        proxy=proxy_url,
        # Direct sources must not inherit HTTP_PROXY.
        trust_env=proxy_url is not None,
    ) as client:
        async with client.stream("GET", url, headers=UPSTREAM_HEADERS) as response:
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
    proxy_url: str | None = None,
) -> PreparedSubscriptionSync:
    url = secret_box.decrypt(subscription.url_ciphertext)
    if proxy_url is None:
        body, headers = await fetch_subscription(url, settings)
    else:
        body, headers = await fetch_subscription(url, settings, proxy_url)
    parsed_nodes = parse_subscription(body)
    if not parsed_nodes:
        raise ValueError("Upstream response does not contain supported nodes")
    return PreparedSubscriptionSync(
        subscription_id=subscription.id,
        nodes=tuple(parsed_nodes),
        usage=parse_subscription_userinfo(headers.get("subscription-userinfo")),
        synced_at=datetime.now(UTC),
    )


async def proxy_urls_for_subscriptions(
    session: AsyncSession,
    subscription_ids: list[str],
    secret_box: SecretBox,
) -> dict[str, str]:
    if not subscription_ids:
        return {}
    rows = (
        await session.execute(
            select(SubscriptionProxy.subscription_id, UpstreamProxy.url_ciphertext)
            .join(UpstreamProxy, UpstreamProxy.id == SubscriptionProxy.proxy_id)
            .where(SubscriptionProxy.subscription_id.in_(subscription_ids))
        )
    ).all()
    return {
        subscription_id: secret_box.decrypt(url_ciphertext)
        for subscription_id, url_ciphertext in rows
    }


async def persist_subscription_syncs(
    session: AsyncSession,
    prepared_syncs: list[PreparedSubscriptionSync],
    errors: dict[str, Exception],
    secret_box: SecretBox,
    expected_versions: dict[str, datetime] | None = None,
) -> set[str]:
    subscription_ids = {prepared.subscription_id for prepared in prepared_syncs} | set(
        errors
    )
    if not subscription_ids:
        return set()

    if expected_versions is not None:
        current_ids: set[str] = set()
        for subscription_id in sorted(subscription_ids):
            expected = expected_versions[subscription_id]
            # This conditional write locks the source until commit. Route changes
            # update the same row before changing proxy links or credentials.
            result = await session.execute(
                update(Subscription)
                .where(
                    Subscription.id == subscription_id,
                    Subscription.updated_at == expected,
                )
                .values(updated_at=Subscription.updated_at)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount:
                current_ids.add(subscription_id)
        prepared_syncs = [
            prepared
            for prepared in prepared_syncs
            if prepared.subscription_id in current_ids
        ]
        errors = {
            subscription_id: error
            for subscription_id, error in errors.items()
            if subscription_id in current_ids
        }
        subscription_ids = current_ids
        if not subscription_ids:
            await session.commit()
            return set()

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
    usage_by_subscription = {
        usage.subscription_id: usage
        for usage in (
            await session.scalars(
                select(SubscriptionUsage).where(
                    SubscriptionUsage.subscription_id.in_(successful_ids)
                )
            )
        ).all()
    }

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

        usage = usage_by_subscription.get(prepared.subscription_id)
        if prepared.usage is None:
            if usage is not None:
                await session.delete(usage)
        elif usage is None:
            session.add(
                SubscriptionUsage(
                    subscription_id=prepared.subscription_id,
                    upload=prepared.usage.upload,
                    download=prepared.usage.download,
                    total=prepared.usage.total,
                    expire=prepared.usage.expire,
                    updated_at=prepared.synced_at,
                )
            )
        else:
            usage.upload = prepared.usage.upload
            usage.download = prepared.usage.download
            usage.total = prepared.usage.total
            usage.expire = prepared.usage.expire
            usage.updated_at = prepared.synced_at

    if stale_node_ids:
        await session.execute(delete(Node).where(Node.id.in_(stale_node_ids)))

    for subscription_id, error in errors.items():
        subscription = subscriptions.get(subscription_id)
        if subscription is not None:
            subscription.status = "error"
            subscription.last_error = str(error)[:1000]

    await session.commit()
    return subscription_ids


async def sync_subscription(
    session: AsyncSession,
    subscription: Subscription,
    settings: Settings,
    secret_box: SecretBox,
    proxy_url: str | None = None,
) -> int:
    subscription_id = subscription.id
    expected_version = subscription.updated_at
    try:
        prepared = await prepare_subscription_sync(
            subscription,
            settings,
            secret_box,
            proxy_url,
        )
        persisted_ids = await persist_subscription_syncs(
            session, [prepared], {}, secret_box, {subscription_id: expected_version}
        )
        if subscription_id not in persisted_ids:
            raise StaleSubscriptionSync("Subscription changed during sync; retry")
        return len(prepared.nodes)
    except StaleSubscriptionSync:
        raise
    except Exception as exc:
        await session.rollback()
        await persist_subscription_syncs(
            session,
            [],
            {subscription_id: exc},
            secret_box,
            {subscription_id: expected_version},
        )
        raise
