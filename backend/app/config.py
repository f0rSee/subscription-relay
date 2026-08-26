from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class ConfigurationError(ValueError):
    pass


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(
    name: str, default: float, *, minimum: float, maximum: float
) -> float:
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


def _normalize_database_url(value: str) -> str:
    if value.startswith("postgres://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgres://")
    elif value.startswith("postgresql://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")

    if not value.startswith("postgresql+asyncpg://"):
        return value

    # Neon returns libpq-style parameters. asyncpg calls the TLS parameter
    # `ssl` and does not implement libpq's `channel_binding` option.
    parsed = urlsplit(value)
    query = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        if key == "sslmode":
            query.append(("ssl", item))
        elif key != "channel_binding":
            query.append((key, item))
    return urlunsplit(parsed._replace(query=urlencode(query)))


@dataclass(frozen=True)
class Settings:
    upstream_url: str | None
    relay_token: str
    database_url: str
    app_encryption_key: str
    admin_username: str
    admin_password: str | None
    session_secret: str
    secure_cookies: bool
    timeout_seconds: float
    max_response_bytes: int
    refresh_seconds: int
    frontend_dist: Path

    @property
    def persistent_database(self) -> bool:
        return not self.database_url.startswith("sqlite")

    @classmethod
    def from_env(cls) -> "Settings":
        upstream_url = os.getenv("UPSTREAM_URL", "").strip() or None
        if upstream_url:
            parsed_url = urlsplit(upstream_url)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                raise ConfigurationError("UPSTREAM_URL must be a valid http(s) URL")
            if parsed_url.scheme == "http" and not _env_bool(
                "ALLOW_INSECURE_HTTP", False
            ):
                raise ConfigurationError(
                    "UPSTREAM_URL must use HTTPS "
                    "(set ALLOW_INSECURE_HTTP=true to override)"
                )

        relay_token = os.getenv("RELAY_TOKEN", "").strip()
        if len(relay_token) < 16:
            raise ConfigurationError("RELAY_TOKEN must contain at least 16 characters")

        database_url = _normalize_database_url(
            os.getenv(
                "DATABASE_URL", "sqlite+aiosqlite:///./subscription_relay.db"
            ).strip()
        )
        if not database_url:
            raise ConfigurationError("DATABASE_URL cannot be empty")

        app_encryption_key = os.getenv("APP_ENCRYPTION_KEY", "").strip()
        session_secret = os.getenv("SESSION_SECRET", "").strip()
        # Backward-compatible fallback. Production setup should provide both
        # dedicated values before moving the database to persistent storage.
        app_encryption_key = app_encryption_key or relay_token
        session_secret = session_secret or relay_token

        admin_password = os.getenv("ADMIN_PASSWORD", "").strip() or None

        return cls(
            upstream_url=upstream_url,
            relay_token=relay_token,
            database_url=database_url,
            app_encryption_key=app_encryption_key,
            admin_username=os.getenv("ADMIN_USERNAME", "admin").strip() or "admin",
            admin_password=admin_password,
            session_secret=session_secret,
            secure_cookies=_env_bool("SECURE_COOKIES", True),
            timeout_seconds=_env_float(
                "UPSTREAM_TIMEOUT_SECONDS", 20.0, minimum=1, maximum=120
            ),
            max_response_bytes=_env_int(
                "MAX_RESPONSE_BYTES",
                5 * 1024 * 1024,
                minimum=1024,
                maximum=50 * 1024 * 1024,
            ),
            refresh_seconds=_env_int(
                "SUBSCRIPTION_REFRESH_SECONDS",
                900,
                minimum=30,
                maximum=86400,
            ),
            frontend_dist=Path(
                os.getenv("FRONTEND_DIST", "frontend/dist")
            ).resolve(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
