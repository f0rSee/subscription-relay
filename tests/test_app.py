import asyncio
import importlib

import httpx
import pytest


HTTPX_ASYNC_CLIENT = httpx.AsyncClient


def app_request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with HTTPX_ASYNC_CLIENT(
            transport=transport, base_url="http://relay.test"
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


@pytest.fixture()
def relay(monkeypatch):
    monkeypatch.setenv("UPSTREAM_URL", "https://provider.example/sub?id=secret")
    monkeypatch.setenv("RELAY_TOKEN", "a-secure-relay-token")

    import app

    importlib.reload(app)
    app.get_settings.cache_clear()
    return app


def test_healthcheck(relay):
    response = app_request(relay.app, "GET", "/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rejects_invalid_token_without_contacting_upstream(relay, monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("upstream must not be contacted")

    monkeypatch.setattr(httpx.AsyncClient, "stream", fail_if_called)
    response = app_request(relay.app, "GET", "/subscription?token=wrong")
    assert response.status_code == 401


def test_relays_body_status_and_subscription_headers(relay, monkeypatch):
    def upstream(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "v2rayNG/1.9"
        assert "x-forwarded-for" not in request.headers
        return httpx.Response(
            200,
            content=b"dmxlc3M6Ly9leGFtcGxlCg==",
            headers={
                "Content-Type": "text/plain",
                "Subscription-Userinfo": "upload=1; download=2; total=3",
                "Set-Cookie": "must-not-leak=yes",
            },
        )

    transport = httpx.MockTransport(upstream)
    def client_factory(*args, **kwargs):
        return HTTPX_ASYNC_CLIENT(transport=transport, **kwargs)

    monkeypatch.setattr(relay.httpx, "AsyncClient", client_factory)

    response = app_request(
        relay.app,
        "GET",
        "/subscription?token=a-secure-relay-token",
        headers={"User-Agent": "v2rayNG/1.9", "X-Forwarded-For": "192.0.2.1"},
    )

    assert response.status_code == 200
    assert response.content == b"dmxlc3M6Ly9leGFtcGxlCg=="
    assert response.headers["subscription-userinfo"] == "upload=1; download=2; total=3"
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"


def test_rejects_oversized_response(relay, monkeypatch):
    monkeypatch.setenv("MAX_RESPONSE_BYTES", "1024")
    relay.get_settings.cache_clear()

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * 1025)
    )
    def client_factory(*args, **kwargs):
        return HTTPX_ASYNC_CLIENT(transport=transport, **kwargs)

    monkeypatch.setattr(relay.httpx, "AsyncClient", client_factory)

    response = app_request(
        relay.app,
        "GET",
        "/subscription",
        headers={"X-Relay-Token": "a-secure-relay-token"},
    )
    assert response.status_code == 502
    assert response.json()["detail"] == "Upstream response is too large"
