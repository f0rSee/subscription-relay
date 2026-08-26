import asyncio
import base64
from pathlib import Path

import httpx

from backend.app.config import Settings, _normalize_database_url
from backend.app.main import create_app
from backend.app.services.subscriptions import (
    UPSTREAM_HEADERS,
    UPSTREAM_USER_AGENT,
    parse_subscription,
)


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
        allow_insecure_http=False,
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

        default_profile = (await client.get("/api/profiles")).json()[0]
        rotate_default = await client.patch(
            f"/api/profiles/{default_profile['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"rotate_token": True},
        )
        assert rotate_default.status_code == 409

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
        b"vless://one@one.example:443#One\ntrojan://two@two.example:443#Two\n"
    )

    async def fake_fetch(url, settings):
        assert url == "https://provider.example/sub?id=secret"
        return upstream, httpx.Headers({"content-type": "text/plain"})

    monkeypatch.setattr(
        "backend.app.services.subscriptions.fetch_subscription", fake_fetch
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


def test_refreshes_all_sources_concurrently_before_each_response(
    tmp_path,
    monkeypatch,
):
    app = create_app(settings_for(tmp_path))
    active_fetches = 0
    max_active_fetches = 0
    calls_by_url: dict[str, int] = {}

    async def fake_fetch(url, settings):
        nonlocal active_fetches, max_active_fetches
        calls_by_url[url] = calls_by_url.get(url, 0) + 1
        version = calls_by_url[url]
        active_fetches += 1
        max_active_fetches = max(max_active_fetches, active_fetches)
        try:
            await asyncio.sleep(0.05)
        finally:
            active_fetches -= 1
        host = "one.example" if "provider.example" in url else "two.example"
        body = f"vless://v{version}@{host}:443#{host}\n".encode()
        return body, httpx.Headers({"content-type": "text/plain"})

    monkeypatch.setattr(
        "backend.app.services.subscriptions.fetch_subscription",
        fake_fetch,
    )

    async def scenario(client: httpx.AsyncClient):
        csrf = await login(client)
        created = await client.post(
            "/api/subscriptions",
            headers={"X-CSRF-Token": csrf},
            json={"name": "Second", "url": "https://second.example/sub"},
        )
        assert created.status_code == 201

        first = await client.get("/s/test-relay-token-at-least-16")
        assert first.status_code == 200
        assert max_active_fetches == 2
        assert all(count == 1 for count in calls_by_url.values())

        second = await client.get("/s/test-relay-token-at-least-16")
        assert second.status_code == 200
        decoded = base64.b64decode(second.content).decode().splitlines()
        assert len(decoded) == 2
        assert all("vless://v2@" in uri for uri in decoded)
        assert all(count == 2 for count in calls_by_url.values())

    asyncio.run(with_client(app, scenario))


def test_default_profile_and_empty_upstream_error(tmp_path, monkeypatch):
    app = create_app(settings_for(tmp_path))

    async def fake_fetch(url, settings):
        return b"device is not supported", httpx.Headers()

    monkeypatch.setattr(
        "backend.app.services.subscriptions.fetch_subscription", fake_fetch
    )

    async def scenario(client: httpx.AsyncClient):
        response = await client.get("/s/test-relay-token-at-least-16")
        assert response.status_code == 502
        assert response.json()["detail"] == (
            "No healthy nodes are available for this profile"
        )

        subscriptions = (await login_and_list(client))[0]
        assert subscriptions["status"] == "error"
        assert "supported nodes" in subscriptions["last_error"]

    async def login_and_list(client: httpx.AsyncClient):
        await login(client)
        return (await client.get("/api/subscriptions")).json()

    asyncio.run(with_client(app, scenario))


def test_removed_legacy_route_and_missing_dashboard_assets(tmp_path):
    app = create_app(settings_for(tmp_path))
    route_paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/api/sync-runs" not in route_paths
    assert "/subscription" not in route_paths

    async def scenario(client: httpx.AsyncClient):
        for path in (
            "/subscription?token=test-relay-token-at-least-16",
            "/subscription/?token=test-relay-token-at-least-16",
        ):
            removed_subscription = await client.get(path)
            assert removed_subscription.status_code == 404

        missing_assets = await client.get("/admin/settings")
        assert missing_assets.status_code == 503
        assert missing_assets.json() == {"detail": "Dashboard assets are not built"}

        unknown_api = await client.get("/api/unknown")
        assert unknown_api.status_code == 404

    asyncio.run(with_client(app, scenario))


def test_request_logs_devices_settings_and_deduplication(tmp_path, monkeypatch):
    app = create_app(settings_for(tmp_path))
    upstream = base64.b64encode(
        b"vless://same@same.example:443#Same\nvless://same@same.example:443#Same copy\n"
    )
    fetch_count = 0

    async def fake_fetch(url, settings):
        nonlocal fetch_count
        fetch_count += 1
        return upstream, httpx.Headers({"content-type": "text/plain"})

    monkeypatch.setattr(
        "backend.app.services.subscriptions.fetch_subscription", fake_fetch
    )

    async def scenario(client: httpx.AsyncClient):
        csrf = await login(client)
        subscriptions = (await client.get("/api/subscriptions")).json()
        first_source_id = subscriptions[0]["id"]

        first_request = await client.get(
            "/s/test-relay-token-at-least-16",
            headers={
                "User-Agent": "v2rayNG/1.10.11",
            },
        )
        assert first_request.status_code == 200
        assert fetch_count == 1
        assert UPSTREAM_USER_AGENT == "Happ/5.6.0/ios/2731171157721"
        assert UPSTREAM_HEADERS == {
            "User-Agent": "Happ/5.6.0/ios/2731171157721",
            "Accept": "text/plain, */*",
            "X-HWID": "4139def9-6877-4771-b313-49e3119ba158",
            "X-Device-OS": "iOS",
            "X-Ver-OS": "27.0",
            "X-Device-Model": "iPhone 17 Pro Max",
        }

        logs = (await client.get("/api/request-logs")).json()
        assert len(logs) == 1
        assert logs[0]["client_name"] == "v2rayNG"
        assert logs[0]["request_type"] == "profile"
        assert logs[0]["status_code"] == 200
        assert logs[0]["node_count"] == 2
        assert "test-relay-token" not in str(logs[0])

        devices = (await client.get("/api/devices")).json()
        assert len(devices) == 1
        assert devices[0]["name"] == "v2rayNG"
        assert devices[0]["request_count"] == 1

        settings = (await client.get("/api/settings")).json()
        assert settings["deduplicate_servers"] is False
        assert settings["request_logging_enabled"] is True
        assert settings["device_tracking_enabled"] is True
        assert settings["auto_refresh_enabled"] is True

        second_source = await client.post(
            "/api/subscriptions",
            headers={"X-CSRF-Token": csrf},
            json={"name": "Second", "url": "https://second.example/sub"},
        )
        assert second_source.status_code == 201
        second_source_id = second_source.json()["id"]
        second_sync = await client.post(
            f"/api/subscriptions/{second_source_id}/sync",
            headers={"X-CSRF-Token": csrf},
        )
        assert second_sync.status_code == 200

        profile_response = await client.post(
            "/api/profiles",
            headers={"X-CSRF-Token": csrf},
            json={
                "name": "Duplicates",
                "subscription_ids": [first_source_id, second_source_id],
            },
        )
        profile = profile_response.json()
        duplicated = await client.get(profile["url"])
        assert len(base64.b64decode(duplicated.content).decode().splitlines()) == 4

        updated = await client.patch(
            "/api/settings",
            headers={"X-CSRF-Token": csrf},
            json={
                "deduplicate_servers": True,
                "request_logging_enabled": False,
                "device_tracking_enabled": False,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["deduplicate_servers"] is True

        deduplicated = await client.get(profile["url"])
        assert len(base64.b64decode(deduplicated.content).decode().splitlines()) == 1
        assert len((await client.get("/api/request-logs")).json()) == 2
        devices_after_disable = (await client.get("/api/devices")).json()
        assert len(devices_after_disable) == 2
        assert sum(device["request_count"] for device in devices_after_disable) == 2

    asyncio.run(with_client(app, scenario))
