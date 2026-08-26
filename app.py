from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, Response


DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024

# These headers are commonly used by Clash, sing-box, v2ray clients and
# subscription panels. Hop-by-hop and encoding headers are intentionally absent.
PASSTHROUGH_RESPONSE_HEADERS = {
    "content-type",
    "content-disposition",
    "subscription-userinfo",
    "profile-update-interval",
    "profile-title",
    "profile-web-page-url",
    "support-url",
    "announce",
}


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    upstream_url: str
    relay_token: str
    timeout_seconds: float
    max_response_bytes: int

    @classmethod
    def from_env(cls) -> "Settings":
        upstream_url = os.getenv("UPSTREAM_URL", "").strip()
        relay_token = os.getenv("RELAY_TOKEN", "").strip()

        if not upstream_url:
            raise ConfigurationError("UPSTREAM_URL is not configured")
        parsed_url = urlsplit(upstream_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ConfigurationError("UPSTREAM_URL must be a valid http(s) URL")
        if parsed_url.scheme == "http" and not _env_bool("ALLOW_INSECURE_HTTP", False):
            raise ConfigurationError(
                "UPSTREAM_URL must use HTTPS (set ALLOW_INSECURE_HTTP=true to override)"
            )

        if len(relay_token) < 16:
            raise ConfigurationError("RELAY_TOKEN must contain at least 16 characters")

        timeout_seconds = _env_float(
            "UPSTREAM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, minimum=1, maximum=120
        )
        max_response_bytes = _env_int(
            "MAX_RESPONSE_BYTES",
            DEFAULT_MAX_RESPONSE_BYTES,
            minimum=1024,
            maximum=50 * 1024 * 1024,
        )

        return cls(
            upstream_url=upstream_url,
            relay_token=relay_token,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


def _provided_token(query_token: str | None, authorization: str | None) -> str:
    if query_token:
        return query_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _safe_response_headers(headers: httpx.Headers) -> dict[str, str]:
    result = {
        name: value
        for name, value in headers.items()
        if name.lower() in PASSTHROUGH_RESPONSE_HEADERS
    }
    result["cache-control"] = "no-store"
    return result


app = FastAPI(
    title="Subscription Relay",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> Response:
    try:
        get_settings()
    except ConfigurationError as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "misconfigured", "detail": str(exc)},
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse({"status": "ok"}, headers={"Cache-Control": "no-store"})


@app.get("/subscription", include_in_schema=False)
async def subscription(
    request: Request,
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
    x_relay_token: str | None = Header(default=None),
) -> Response:
    try:
        settings = get_settings()
    except ConfigurationError:
        return JSONResponse(
            status_code=503,
            content={"detail": "Relay is not configured"},
            headers={"Cache-Control": "no-store"},
        )

    supplied_token = x_relay_token or _provided_token(token, authorization)
    if not secrets.compare_digest(supplied_token, settings.relay_token):
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid relay token"},
            headers={"Cache-Control": "no-store"},
        )

    upstream_headers = {
        "User-Agent": request.headers.get("user-agent", "subscription-relay/1.0"),
        "Accept": request.headers.get("accept", "*/*"),
    }

    try:
        timeout = httpx.Timeout(settings.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream(
                "GET", settings.upstream_url, headers=upstream_headers
            ) as upstream_response:
                body = bytearray()
                async for chunk in upstream_response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > settings.max_response_bytes:
                        return JSONResponse(
                            status_code=502,
                            content={"detail": "Upstream response is too large"},
                            headers={"Cache-Control": "no-store"},
                        )

                return Response(
                    content=bytes(body),
                    status_code=upstream_response.status_code,
                    headers=_safe_response_headers(upstream_response.headers),
                )
    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={"detail": "Upstream request timed out"},
            headers={"Cache-Control": "no-store"},
        )
    except httpx.HTTPError:
        return JSONResponse(
            status_code=502,
            content={"detail": "Unable to fetch the upstream subscription"},
            headers={"Cache-Control": "no-store"},
        )
