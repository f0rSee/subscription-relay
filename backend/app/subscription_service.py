from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import Node, Subscription, SyncRun
from .security import SecretBox


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

# Subscription providers often change their response format based on User-Agent.
# A stable service identity keeps synchronization in the URI-list format that the
# parser needs, regardless of which VPN client requested the relay profile.
UPSTREAM_USER_AGENT = "subscription-relay/2.0"


@dataclass(frozen=True)
class ParsedNode:
    uri: str
    fingerprint: str
    name: str
    protocol: str
    host: str | None
    position: int


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
    url: str, _user_agent: str, settings: Settings
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


async def sync_subscription(
    session: AsyncSession,
    subscription: Subscription,
    settings: Settings,
    secret_box: SecretBox,
    user_agent: str,
) -> int:
    run = SyncRun(subscription_id=subscription.id, status="running")
    session.add(run)
    await session.flush()

    try:
        url = secret_box.decrypt(subscription.url_ciphertext)
        body, _ = await fetch_subscription(url, user_agent, settings)
        parsed_nodes = parse_subscription(body)
        if not parsed_nodes:
            raise ValueError("Upstream response does not contain supported nodes")

        now = datetime.now(timezone.utc)
        existing_result = await session.execute(
            select(Node).where(Node.subscription_id == subscription.id)
        )
        existing = {node.id: node for node in existing_result.scalars()}
        active_ids: set[str] = set()
        fingerprint_occurrences: dict[str, int] = {}

        for parsed in parsed_nodes:
            occurrence = fingerprint_occurrences.get(parsed.fingerprint, 0)
            fingerprint_occurrences[parsed.fingerprint] = occurrence + 1
            node_identity = (
                parsed.fingerprint
                if occurrence == 0
                else f"{parsed.fingerprint}:{occurrence}"
            )
            node_id = hashlib.sha256(
                f"{subscription.id}:{node_identity}".encode("utf-8")
            ).hexdigest()
            active_ids.add(node_id)
            node = existing.get(node_id)
            if node is None:
                node = Node(
                    id=node_id,
                    subscription_id=subscription.id,
                    fingerprint=parsed.fingerprint,
                    name=parsed.name,
                    protocol=parsed.protocol,
                    host=parsed.host,
                    uri_ciphertext=secret_box.encrypt(parsed.uri),
                    source_position=parsed.position,
                    last_seen_at=now,
                )
                session.add(node)
            else:
                node.name = parsed.name
                node.protocol = parsed.protocol
                node.host = parsed.host
                node.uri_ciphertext = secret_box.encrypt(parsed.uri)
                node.source_position = parsed.position
                node.last_seen_at = now

        stale_ids = set(existing) - active_ids
        if stale_ids:
            await session.execute(delete(Node).where(Node.id.in_(stale_ids)))

        subscription.status = "healthy"
        subscription.node_count = len(parsed_nodes)
        subscription.last_error = None
        subscription.last_sync_at = now
        run.status = "success"
        run.node_count = len(parsed_nodes)
        run.finished_at = now
        await session.commit()
        return len(parsed_nodes)
    except Exception as exc:
        now = datetime.now(timezone.utc)
        subscription.status = "error"
        subscription.last_error = str(exc)[:1000]
        run.status = "error"
        run.error = str(exc)[:1000]
        run.finished_at = now
        await session.commit()
        raise
