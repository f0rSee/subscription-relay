import asyncio
import base64
from pathlib import Path

import httpx
import pytest

from backend.app.config import Settings, _normalize_database_url
from backend.app.main import create_app
from backend.app.subscription_service import parse_subscription


def settings_for(tmp_path: Path) -> Settings:
    return Settings(
        upstream_url="https://provider.example/sub?id=secret",
        relay_token="test-relay-token-at-least-16",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'relay.db'}",
        app_encryption_key="test-encryption-key",
        admin_username="admin",
        admin_password="correct-horse-battery-staple",
        session_secret="test-session-secret",
        secure_cookies=False,
        timeout_seconds=5,
        max_response_bytes=1024 * 1024,
        refresh_seconds=900,
        frontend_dist=tmp_path / "missing-dist",
    )


async def with_client(app, scenario):
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://relay.test"
        ) as client:
            return await scenario(client)


async def login(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_parses_plain_base64_and_vmess_metadata():
    vmess_payload = base64.b64encode(
        b'{"ps":"Amsterdam 01","add":"nl.example.com","port":"443"}'
    ).decode()
    plain = f"vless://id@example.com:443#Paris\nvmess://{vmess_payload}\n"
    encoded = base64.b64encode(plain.encode())

    nodes = parse_subscription(encoded)

    assert [node.name for node in nodes] == ["Paris", "Amsterdam 01"]
    assert [node.host for node in nodes] == ["example.com", "nl.example.com"]


def test_normalizes_neon_url_for_asyncpg():
    normalized = _normalize_database_url(
        "postgresql://user:pass@host/db?sslmode=require&channel_binding=require"
    )
    assert normalized == "postgresql+asyncpg://user:pass@host/db?ssl=require"


def test_health_authentication_and_csrf(tmp_path):
    app = create_app(settings_for(tmp_path))

    async def scenario(client: httpx.AsyncClient):
        health = await client.get("/healthz")
        assert health.status_code == 200
        assert health.json() == {"status": "ok", "storage": "ephemeral"}

        unauthorized = await client.get("/api/dashboard")
        assert unauthorized.status_code == 401

        bad_login = await client.post(
            "/api/auth/login", json={"username": "admin", "password": "wrong"}
        )
        assert bad_login.status_code == 401

        csrf = await login(client)
        dashboard = await client.get("/api/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["subscriptions"] == 1

        missing_csrf = await client.post(
            "/api/subscriptions",
            json={"name": "Other", "url": "https://other.example/sub"},
        )
        assert missing_csrf.status_code == 403

        created = await client.post(
            "/api/subscriptions",
            headers={"X-CSRF-Token": csrf},
            json={"name": "Other", "url": "https://other.example/sub"},
        )
        assert created.status_code == 201
        assert "secret" not in created.json()["url_hint"]

    asyncio.run(with_client(app, scenario))


def test_combines_sources_and_persists_profile_order(tmp_path, monkeypatch):
    app = create_app(settings_for(tmp_path))
    upstream = base64.b64encode(
        b"vless://one@one.example:443#One\n"
        b"trojan://two@two.example:443#Two\n"
    )

    async def fake_fetch(url, user_agent, settings):
        assert url == "https://provider.example/sub?id=secret"
        assert user_agent
        return upstream, httpx.Headers({"content-type": "text/plain"})

    monkeypatch.setattr(
        "backend.app.subscription_service.fetch_subscription", fake_fetch
    )

    async def scenario(client: httpx.AsyncClient):
        csrf = await login(client)
        subscriptions = (await client.get("/api/subscriptions")).json()
        source_id = subscriptions[0]["id"]

        synced = await client.post(
            f"/api/subscriptions/{source_id}/sync",
            headers={"X-CSRF-Token": csrf},
        )
        assert synced.status_code == 200
        assert synced.json()["node_count"] == 2

        created = await client.post(
            "/api/profiles",
            headers={"X-CSRF-Token": csrf},
            json={"name": "Phone", "subscription_ids": [source_id]},
        )
        assert created.status_code == 201
        profile = created.json()

        nodes = (await client.get(f"/api/profiles/{profile['id']}/nodes")).json()
        assert [node["name"] for node in nodes] == ["One", "Two"]

        reversed_ids = [node["id"] for node in reversed(nodes)]
        reordered = await client.put(
            f"/api/profiles/{profile['id']}/node-order",
            headers={"X-CSRF-Token": csrf},
            json={"node_ids": reversed_ids},
        )
        assert reordered.status_code == 200
        assert reordered.json() == {"updated": 2}

        public = await client.get(profile["url"])
        assert public.status_code == 200
        decoded = base64.b64decode(public.content).decode()
        assert decoded.splitlines() == [
            "trojan://two@two.example:443#Two",
            "vless://one@one.example:443#One",
        ]

    asyncio.run(with_client(app, scenario))


def test_legacy_token_and_empty_upstream_error(tmp_path, monkeypatch):
    app = create_app(settings_for(tmp_path))

    async def fake_fetch(url, user_agent, settings):
        return b"device is not supported", httpx.Headers()

    monkeypatch.setattr(
        "backend.app.subscription_service.fetch_subscription", fake_fetch
    )

    async def scenario(client: httpx.AsyncClient):
        rejected = await client.get("/subscription?token=wrong")
        assert rejected.status_code == 401

        response = await client.get(
            "/subscription", headers={"X-Relay-Token": "test-relay-token-at-least-16"}
        )
        assert response.status_code == 502
        assert response.json()["detail"] == "No healthy nodes are available for this profile"

        subscriptions = (await login_and_list(client))[0]
        assert subscriptions["status"] == "error"
        assert "supported nodes" in subscriptions["last_error"]

    async def login_and_list(client: httpx.AsyncClient):
        await login(client)
        return (await client.get("/api/subscriptions")).json()

    asyncio.run(with_client(app, scenario))
