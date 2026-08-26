from __future__ import annotations

import hashlib
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import ConfigurationError, Settings, get_settings
from .database import Database
from .models import (
    ClientDevice,
    Node,
    Profile,
    ProfileNodePreference,
    ProfileSubscription,
    RelaySettings,
    RequestLog,
    Subscription,
    SyncRun,
)
from .schemas import (
    LoginRequest,
    NodeOrderUpdate,
    ProfileCreate,
    ProfileUpdate,
    RelaySettingsUpdate,
    SubscriptionCreate,
    SubscriptionUpdate,
)
from .security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    AdminSession,
    SecretBox,
    SessionManager,
    require_admin,
)
from .subscription_service import (
    UPSTREAM_USER_AGENT,
    encode_subscription,
    sync_subscription,
)


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


def _validate_source_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="URL must be valid http(s)")
    if parsed.scheme == "http" and not get_settings_allow_http():
        raise HTTPException(status_code=422, detail="Only HTTPS sources are allowed")


def get_settings_allow_http() -> bool:
    import os

    return os.getenv("ALLOW_INSECURE_HTTP", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _url_hint(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path
    if len(path) > 48:
        path = path[:45] + "…"
    suffix = "?•••" if parsed.query else ""
    return f"{parsed.scheme}://{parsed.netloc}{path}{suffix}"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _is_stale(value: datetime | None, refresh_seconds: int) -> bool:
    if value is None:
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value < datetime.now(timezone.utc) - timedelta(seconds=refresh_seconds)


async def _bootstrap(database: Database, settings: Settings, secret_box: SecretBox) -> None:
    async with database.sessions() as session:
        if await session.get(RelaySettings, 1) is None:
            session.add(RelaySettings(id=1))

        profile = await session.scalar(
            select(Profile).where(Profile.token == settings.relay_token)
        )
        if profile is None:
            profile = Profile(name="Default", token=settings.relay_token)
            session.add(profile)
            await session.flush()

        subscription_count = await session.scalar(
            select(func.count()).select_from(Subscription)
        )
        if not subscription_count and settings.upstream_url:
            subscription = Subscription(
                name="Primary subscription",
                url_ciphertext=secret_box.encrypt(settings.upstream_url),
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
            for index, subscription in enumerate(subscriptions):
                if subscription.id not in linked_ids:
                    session.add(
                        ProfileSubscription(
                            profile_id=profile.id,
                            subscription_id=subscription.id,
                            position=index,
                        )
                    )
        await session.commit()


async def _relay_settings(session: AsyncSession) -> RelaySettings:
    relay_settings = await session.get(RelaySettings, 1)
    if relay_settings is None:
        relay_settings = RelaySettings(id=1)
        session.add(relay_settings)
        await session.flush()
    return relay_settings


def _settings_view(settings: RelaySettings) -> dict:
    return {
        "deduplicate_servers": settings.deduplicate_servers,
        "request_logging_enabled": settings.request_logging_enabled,
        "device_tracking_enabled": settings.device_tracking_enabled,
        "auto_refresh_enabled": settings.auto_refresh_enabled,
        "updated_at": _iso(settings.updated_at),
    }


def _client_identity(request: Request) -> tuple[str, str, str]:
    user_agent = request.headers.get("user-agent", "Unknown client").strip()[:512]
    ip_address = (request.client.host if request.client else "unknown")[:64]
    product = user_agent.split(" ", 1)[0].split("/", 1)[0].strip()
    client_name = (product or "Unknown client")[:160]
    return client_name, user_agent, ip_address


async def _record_subscription_request(
    request: Request,
    profile: Profile,
    *,
    request_type: str,
    status_code: int,
    node_count: int = 0,
    error: str | None = None,
) -> None:
    database: Database = request.app.state.database
    app_settings: Settings = request.app.state.settings
    client_name, user_agent, ip_address = _client_identity(request)
    now = datetime.now(timezone.utc)

    try:
        async with database.sessions() as session:
            relay_settings = await _relay_settings(session)
            device_id: str | None = None

            if relay_settings.device_tracking_enabled:
                device_id = hashlib.sha256(
                    f"{app_settings.session_secret}\0{ip_address}\0{user_agent}".encode()
                ).hexdigest()
                device = await session.get(ClientDevice, device_id)
                if device is None:
                    device = ClientDevice(
                        id=device_id,
                        name=client_name,
                        user_agent=user_agent,
                        ip_address=ip_address,
                        request_count=1,
                        last_profile_name=profile.name,
                        last_status_code=status_code,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                    session.add(device)
                else:
                    device.name = client_name
                    device.user_agent = user_agent
                    device.ip_address = ip_address
                    device.request_count += 1
                    device.last_profile_name = profile.name
                    device.last_status_code = status_code
                    device.last_seen_at = now

            if relay_settings.request_logging_enabled:
                session.add(
                    RequestLog(
                        profile_id=profile.id,
                        profile_name=profile.name,
                        request_type=request_type,
                        device_id=device_id,
                        client_name=client_name,
                        user_agent=user_agent,
                        ip_address=ip_address,
                        status_code=status_code,
                        node_count=node_count,
                        error=error[:1000] if error else None,
                        requested_at=now,
                    )
                )
            await session.commit()
    except Exception:
        # Observability must never make a working subscription unavailable.
        return


def _subscription_view(subscription: Subscription, secret_box: SecretBox) -> dict:
    try:
        hint = _url_hint(secret_box.decrypt(subscription.url_ciphertext))
    except ValueError:
        hint = "Encrypted value unavailable"
    return {
        "id": subscription.id,
        "name": subscription.name,
        "url_hint": hint,
        "enabled": subscription.enabled,
        "priority": subscription.priority,
        "status": subscription.status,
        "node_count": subscription.node_count,
        "last_error": subscription.last_error,
        "last_sync_at": _iso(subscription.last_sync_at),
        "created_at": _iso(subscription.created_at),
        "updated_at": _iso(subscription.updated_at),
    }


async def _profile_nodes(
    session: AsyncSession, profile_id: str
) -> list[tuple[Node, Subscription, ProfileNodePreference | None]]:
    preference_join = and_(
        ProfileNodePreference.profile_id == profile_id,
        ProfileNodePreference.node_id == Node.id,
    )
    rows = (
        await session.execute(
            select(Node, Subscription, ProfileNodePreference)
            .join(Subscription, Subscription.id == Node.subscription_id)
            .join(
                ProfileSubscription,
                and_(
                    ProfileSubscription.profile_id == profile_id,
                    ProfileSubscription.subscription_id == Subscription.id,
                ),
            )
            .outerjoin(ProfileNodePreference, preference_join)
            .where(Subscription.enabled.is_(True), Node.enabled.is_(True))
        )
    ).all()

    def sort_key(
        item: tuple[Node, Subscription, ProfileNodePreference | None]
    ) -> tuple:
        node, subscription, preference = item
        pinned = bool(preference and preference.pinned)
        explicit = preference.position if preference else None
        return (
            0 if pinned else 1,
            explicit if explicit is not None else 1_000_000,
            subscription.priority,
            node.source_position,
            node.name.casefold(),
        )

    return sorted(rows, key=sort_key)


async def _refresh_profile_sources(app: FastAPI, profile_id: str) -> None:
    database: Database = app.state.database
    settings: Settings = app.state.settings
    secret_box: SecretBox = app.state.secret_box
    async with database.sessions() as session:
        if not (await _relay_settings(session)).auto_refresh_enabled:
            return
        subscriptions = (
            await session.scalars(
                select(Subscription)
                .join(
                    ProfileSubscription,
                    ProfileSubscription.subscription_id == Subscription.id,
                )
                .where(
                    ProfileSubscription.profile_id == profile_id,
                    Subscription.enabled.is_(True),
                )
                .order_by(Subscription.priority)
            )
        ).all()

    for subscription in subscriptions:
        if not _is_stale(subscription.last_sync_at, settings.refresh_seconds):
            continue
        async with database.sessions() as session:
            current = await session.get(Subscription, subscription.id)
            if current is None:
                continue
            try:
                await sync_subscription(
                    session, current, settings, secret_box, UPSTREAM_USER_AGENT
                )
            except (httpx.HTTPError, ValueError):
                # A stale source must not take down profiles backed by other sources.
                continue


async def _render_profile(
    request: Request, profile: Profile, *, request_type: str
) -> Response:
    if not profile.enabled:
        await _record_subscription_request(
            request,
            profile,
            request_type=request_type,
            status_code=404,
            error="Profile disabled",
        )
        return JSONResponse(status_code=404, content={"detail": "Profile disabled"})

    await _refresh_profile_sources(request.app, profile.id)
    database: Database = request.app.state.database
    secret_box: SecretBox = request.app.state.secret_box
    async with database.sessions() as session:
        relay_settings = await _relay_settings(session)
        rows = await _profile_nodes(session, profile.id)
        uris: list[str] = []
        seen: set[str] = set()
        for node, _, preference in rows:
            if preference and not preference.enabled:
                continue
            if relay_settings.deduplicate_servers and node.fingerprint in seen:
                continue
            seen.add(node.fingerprint)
            try:
                uris.append(secret_box.decrypt(node.uri_ciphertext))
            except ValueError:
                continue

    if not uris:
        await _record_subscription_request(
            request,
            profile,
            request_type=request_type,
            status_code=502,
            error="No healthy nodes are available for this profile",
        )
        return JSONResponse(
            status_code=502,
            content={"detail": "No healthy nodes are available for this profile"},
            headers={"Cache-Control": "no-store"},
        )
    await _record_subscription_request(
        request,
        profile,
        request_type=request_type,
        status_code=200,
        node_count=len(uris),
    )
    return Response(
        content=encode_subscription(uris),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-store",
            "Profile-Title": profile.name,
            "Profile-Update-Interval": "15",
        },
    )


def create_app(settings_override: Settings | None = None) -> FastAPI:
    settings = settings_override or get_settings()
    database = Database(settings)
    secret_box = SecretBox(settings.app_encryption_key)
    session_manager = SessionManager(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await database.create_schema()
        await _bootstrap(database, settings, secret_box)
        yield
        await database.close()

    app = FastAPI(
        title="Subscription Relay",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.secret_box = secret_box
    app.state.sessions = session_manager

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> Response:
        try:
            async with database.sessions() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"status": "database_unavailable"},
                headers={"Cache-Control": "no-store"},
            )
        return JSONResponse(
            {
                "status": "ok",
                "storage": "persistent" if settings.persistent_database else "ephemeral",
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/subscription", include_in_schema=False)
    async def legacy_subscription(
        request: Request,
        token: str | None = Query(default=None),
        authorization: str | None = Header(default=None),
        x_relay_token: str | None = Header(default=None),
    ) -> Response:
        supplied = x_relay_token or token or ""
        if not supplied and authorization and authorization.lower().startswith(
            "bearer "
        ):
            supplied = authorization[7:].strip()
        if not secrets.compare_digest(supplied, settings.relay_token):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid relay token"},
                headers={"Cache-Control": "no-store"},
            )
        async with database.sessions() as session:
            profile = await session.scalar(
                select(Profile).where(Profile.token == settings.relay_token)
            )
            if profile is None:
                return JSONResponse(status_code=503, content={"detail": "No profile"})
            return await _render_profile(request, profile, request_type="legacy")

    @app.get("/s/{token}", include_in_schema=False)
    async def public_profile(request: Request, token: str) -> Response:
        async with database.sessions() as session:
            profile = await session.scalar(select(Profile).where(Profile.token == token))
            if profile is None:
                return JSONResponse(status_code=404, content={"detail": "Profile not found"})
            return await _render_profile(request, profile, request_type="profile")

    @app.post("/api/auth/login")
    async def login(payload: LoginRequest) -> Response:
        if settings.admin_password is None:
            raise HTTPException(status_code=503, detail="Admin login is not configured")
        if not session_manager.authenticate(payload.username, payload.password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        cookie, session = session_manager.create_cookie(payload.username)
        response = JSONResponse(
            {"authenticated": True, "username": session.username, "csrf_token": session.csrf_token}
        )
        response.set_cookie(
            SESSION_COOKIE,
            cookie,
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="strict",
            path="/",
        )
        return response

    @app.get("/api/auth/session")
    async def auth_session(request: Request) -> dict:
        session = session_manager.read_cookie(request.cookies.get(SESSION_COOKIE))
        if session is None:
            return {
                "authenticated": False,
                "admin_configured": settings.admin_password is not None,
            }
        return {
            "authenticated": True,
            "username": session.username,
            "csrf_token": session.csrf_token,
            "admin_configured": True,
        }

    @app.post("/api/auth/logout")
    async def logout(_: AdminSession = Depends(require_admin)) -> Response:
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.get("/api/dashboard")
    async def dashboard(_: AdminSession = Depends(require_admin)) -> dict:
        async with database.sessions() as session:
            subscriptions = await session.scalar(
                select(func.count()).select_from(Subscription)
            )
            healthy = await session.scalar(
                select(func.count()).select_from(Subscription).where(
                    Subscription.status == "healthy"
                )
            )
            nodes = await session.scalar(select(func.count()).select_from(Node))
            profiles = await session.scalar(select(func.count()).select_from(Profile))
            request_logs = await session.scalar(
                select(func.count()).select_from(RequestLog)
            )
            devices = await session.scalar(
                select(func.count()).select_from(ClientDevice)
            )
        return {
            "subscriptions": subscriptions or 0,
            "healthy_subscriptions": healthy or 0,
            "nodes": nodes or 0,
            "profiles": profiles or 0,
            "request_logs": request_logs or 0,
            "devices": devices or 0,
            "persistent_storage": settings.persistent_database,
        }

    @app.get("/api/subscriptions")
    async def list_subscriptions(
        _: AdminSession = Depends(require_admin),
    ) -> list[dict]:
        async with database.sessions() as session:
            subscriptions = (
                await session.scalars(
                    select(Subscription).order_by(
                        Subscription.priority, Subscription.created_at
                    )
                )
            ).all()
            return [_subscription_view(item, secret_box) for item in subscriptions]

    @app.post("/api/subscriptions", status_code=201)
    async def create_subscription(
        payload: SubscriptionCreate,
        _: AdminSession = Depends(require_admin),
    ) -> dict:
        _validate_source_url(payload.url)
        async with database.sessions() as session:
            subscription = Subscription(
                name=payload.name,
                url_ciphertext=secret_box.encrypt(payload.url),
                enabled=payload.enabled,
                priority=payload.priority,
            )
            session.add(subscription)
            await session.flush()
            profiles = (await session.scalars(select(Profile))).all()
            for index, profile in enumerate(profiles):
                session.add(
                    ProfileSubscription(
                        profile_id=profile.id,
                        subscription_id=subscription.id,
                        position=index,
                    )
                )
            await session.commit()
            return _subscription_view(subscription, secret_box)

    @app.patch("/api/subscriptions/{subscription_id}")
    async def update_subscription(
        subscription_id: str,
        payload: SubscriptionUpdate,
        _: AdminSession = Depends(require_admin),
    ) -> dict:
        async with database.sessions() as session:
            subscription = await session.get(Subscription, subscription_id)
            if subscription is None:
                raise HTTPException(status_code=404, detail="Subscription not found")
            updates = payload.model_dump(exclude_unset=True)
            if "url" in updates:
                _validate_source_url(updates.pop("url"))
                subscription.url_ciphertext = secret_box.encrypt(payload.url or "")
                subscription.status = "never"
            for key, value in updates.items():
                setattr(subscription, key, value)
            await session.commit()
            return _subscription_view(subscription, secret_box)

    @app.delete("/api/subscriptions/{subscription_id}", status_code=204)
    async def delete_subscription(
        subscription_id: str,
        _: AdminSession = Depends(require_admin),
    ) -> Response:
        async with database.sessions() as session:
            subscription = await session.get(Subscription, subscription_id)
            if subscription is None:
                raise HTTPException(status_code=404, detail="Subscription not found")
            await session.delete(subscription)
            await session.commit()
        return Response(status_code=204)

    @app.post("/api/subscriptions/{subscription_id}/sync")
    async def sync_source(
        subscription_id: str,
        request: Request,
        _: AdminSession = Depends(require_admin),
    ) -> dict:
        async with database.sessions() as session:
            subscription = await session.get(Subscription, subscription_id)
            if subscription is None:
                raise HTTPException(status_code=404, detail="Subscription not found")
            try:
                count = await sync_subscription(
                    session,
                    subscription,
                    settings,
                    secret_box,
                    request.headers.get("user-agent", "subscription-relay-dashboard/2.0"),
                )
            except httpx.HTTPStatusError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Upstream returned HTTP {exc.response.status_code}",
                ) from exc
            except (httpx.HTTPError, ValueError) as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            return {"status": "healthy", "node_count": count}

    @app.get("/api/profiles")
    async def list_profiles(_: AdminSession = Depends(require_admin)) -> list[dict]:
        async with database.sessions() as session:
            profiles = (
                await session.scalars(select(Profile).order_by(Profile.created_at))
            ).all()
            result = []
            for profile in profiles:
                source_ids = (
                    await session.scalars(
                        select(ProfileSubscription.subscription_id).where(
                            ProfileSubscription.profile_id == profile.id
                        )
                    )
                ).all()
                result.append(
                    {
                        "id": profile.id,
                        "name": profile.name,
                        "token": profile.token,
                        "enabled": profile.enabled,
                        "subscription_ids": source_ids,
                        "url": f"/s/{profile.token}",
                        "created_at": _iso(profile.created_at),
                    }
                )
            return result

    @app.post("/api/profiles", status_code=201)
    async def create_profile(
        payload: ProfileCreate,
        _: AdminSession = Depends(require_admin),
    ) -> dict:
        async with database.sessions() as session:
            profile = Profile(name=payload.name, token=secrets.token_urlsafe(32))
            session.add(profile)
            await session.flush()
            source_ids = payload.subscription_ids
            if not source_ids:
                source_ids = list((await session.scalars(select(Subscription.id))).all())
            for position, source_id in enumerate(source_ids):
                if await session.get(Subscription, source_id) is None:
                    raise HTTPException(status_code=422, detail="Unknown subscription")
                session.add(
                    ProfileSubscription(
                        profile_id=profile.id,
                        subscription_id=source_id,
                        position=position,
                    )
                )
            await session.commit()
            return {
                "id": profile.id,
                "name": profile.name,
                "token": profile.token,
                "enabled": profile.enabled,
                "subscription_ids": source_ids,
                "url": f"/s/{profile.token}",
            }

    @app.patch("/api/profiles/{profile_id}")
    async def update_profile(
        profile_id: str,
        payload: ProfileUpdate,
        _: AdminSession = Depends(require_admin),
    ) -> dict:
        async with database.sessions() as session:
            profile = await session.get(Profile, profile_id)
            if profile is None:
                raise HTTPException(status_code=404, detail="Profile not found")
            if payload.name is not None:
                profile.name = payload.name
            if payload.enabled is not None:
                profile.enabled = payload.enabled
            if payload.rotate_token:
                profile.token = secrets.token_urlsafe(32)
            if payload.subscription_ids is not None:
                await session.execute(
                    delete(ProfileSubscription).where(
                        ProfileSubscription.profile_id == profile_id
                    )
                )
                for position, source_id in enumerate(payload.subscription_ids):
                    if await session.get(Subscription, source_id) is None:
                        raise HTTPException(status_code=422, detail="Unknown subscription")
                    session.add(
                        ProfileSubscription(
                            profile_id=profile_id,
                            subscription_id=source_id,
                            position=position,
                        )
                    )
            await session.commit()
            source_ids = list(
                (
                    await session.scalars(
                        select(ProfileSubscription.subscription_id).where(
                            ProfileSubscription.profile_id == profile_id
                        )
                    )
                ).all()
            )
            return {
                "id": profile.id,
                "name": profile.name,
                "token": profile.token,
                "enabled": profile.enabled,
                "subscription_ids": source_ids,
                "url": f"/s/{profile.token}",
            }

    @app.delete("/api/profiles/{profile_id}", status_code=204)
    async def delete_profile(
        profile_id: str,
        _: AdminSession = Depends(require_admin),
    ) -> Response:
        async with database.sessions() as session:
            profile = await session.get(Profile, profile_id)
            if profile is None:
                raise HTTPException(status_code=404, detail="Profile not found")
            if secrets.compare_digest(profile.token, settings.relay_token):
                raise HTTPException(status_code=409, detail="Default profile cannot be deleted")
            await session.delete(profile)
            await session.commit()
        return Response(status_code=204)

    @app.get("/api/profiles/{profile_id}/nodes")
    async def list_profile_nodes(
        profile_id: str,
        _: AdminSession = Depends(require_admin),
    ) -> list[dict]:
        async with database.sessions() as session:
            if await session.get(Profile, profile_id) is None:
                raise HTTPException(status_code=404, detail="Profile not found")
            rows = await _profile_nodes(session, profile_id)
            seen: set[str] = set()
            result = []
            for node, subscription, preference in rows:
                duplicate = node.fingerprint in seen
                seen.add(node.fingerprint)
                result.append(
                    {
                        "id": node.id,
                        "name": node.name,
                        "protocol": node.protocol,
                        "host": node.host,
                        "subscription_id": subscription.id,
                        "subscription_name": subscription.name,
                        "enabled": not preference or preference.enabled,
                        "pinned": bool(preference and preference.pinned),
                        "duplicate": duplicate,
                    }
                )
            return result

    @app.put("/api/profiles/{profile_id}/node-order")
    async def update_node_order(
        profile_id: str,
        payload: NodeOrderUpdate,
        _: AdminSession = Depends(require_admin),
    ) -> dict:
        if len(payload.node_ids) != len(set(payload.node_ids)):
            raise HTTPException(status_code=422, detail="Node ids must be unique")
        async with database.sessions() as session:
            if await session.get(Profile, profile_id) is None:
                raise HTTPException(status_code=404, detail="Profile not found")
            valid_rows = await _profile_nodes(session, profile_id)
            valid_ids = {node.id for node, _, _ in valid_rows}
            if not set(payload.node_ids).issubset(valid_ids):
                raise HTTPException(status_code=422, detail="Unknown node in order")
            await session.execute(
                delete(ProfileNodePreference).where(
                    ProfileNodePreference.profile_id == profile_id
                )
            )
            for position, node_id in enumerate(payload.node_ids):
                session.add(
                    ProfileNodePreference(
                        profile_id=profile_id,
                        node_id=node_id,
                        position=position,
                    )
                )
            await session.commit()
        return {"updated": len(payload.node_ids)}

    @app.get("/api/sync-runs")
    async def list_sync_runs(
        limit: int = Query(default=20, ge=1, le=100),
        _: AdminSession = Depends(require_admin),
    ) -> list[dict]:
        async with database.sessions() as session:
            rows = (
                await session.execute(
                    select(SyncRun, Subscription.name)
                    .join(Subscription, Subscription.id == SyncRun.subscription_id)
                    .order_by(SyncRun.started_at.desc())
                    .limit(limit)
                )
            ).all()
            return [
                {
                    "id": run.id,
                    "subscription_name": name,
                    "status": run.status,
                    "node_count": run.node_count,
                    "error": run.error,
                    "started_at": _iso(run.started_at),
                    "finished_at": _iso(run.finished_at),
                }
                for run, name in rows
            ]

    @app.get("/api/request-logs")
    async def list_request_logs(
        limit: int = Query(default=100, ge=1, le=500),
        _: AdminSession = Depends(require_admin),
    ) -> list[dict]:
        async with database.sessions() as session:
            logs = (
                await session.scalars(
                    select(RequestLog)
                    .order_by(RequestLog.requested_at.desc())
                    .limit(limit)
                )
            ).all()
            return [
                {
                    "id": log.id,
                    "profile_id": log.profile_id,
                    "profile_name": log.profile_name,
                    "request_type": log.request_type,
                    "device_id": log.device_id,
                    "client_name": log.client_name,
                    "user_agent": log.user_agent,
                    "ip_address": log.ip_address,
                    "status_code": log.status_code,
                    "node_count": log.node_count,
                    "error": log.error,
                    "requested_at": _iso(log.requested_at),
                }
                for log in logs
            ]

    @app.get("/api/devices")
    async def list_devices(
        limit: int = Query(default=100, ge=1, le=500),
        _: AdminSession = Depends(require_admin),
    ) -> list[dict]:
        async with database.sessions() as session:
            devices = (
                await session.scalars(
                    select(ClientDevice)
                    .order_by(ClientDevice.last_seen_at.desc())
                    .limit(limit)
                )
            ).all()
            return [
                {
                    "id": device.id,
                    "name": device.name,
                    "user_agent": device.user_agent,
                    "ip_address": device.ip_address,
                    "request_count": device.request_count,
                    "last_profile_name": device.last_profile_name,
                    "last_status_code": device.last_status_code,
                    "first_seen_at": _iso(device.first_seen_at),
                    "last_seen_at": _iso(device.last_seen_at),
                }
                for device in devices
            ]

    @app.get("/api/settings")
    async def get_relay_settings(
        _: AdminSession = Depends(require_admin),
    ) -> dict:
        async with database.sessions() as session:
            return _settings_view(await _relay_settings(session))

    @app.patch("/api/settings")
    async def update_relay_settings(
        payload: RelaySettingsUpdate,
        _: AdminSession = Depends(require_admin),
    ) -> dict:
        async with database.sessions() as session:
            relay_settings = await _relay_settings(session)
            for key, value in payload.model_dump(exclude_none=True).items():
                setattr(relay_settings, key, value)
            relay_settings.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return _settings_view(relay_settings)

    frontend_dist: Path = settings.frontend_dist
    assets_dir = frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/{path:path}", include_in_schema=False)
    async def dashboard_spa(path: str = "") -> Response:
        index_file = frontend_dist / "index.html"
        if not index_file.is_file():
            return JSONResponse(
                status_code=503,
                content={"detail": "Dashboard assets are not built"},
            )
        return FileResponse(index_file)

    return app


try:
    app = create_app()
except ConfigurationError as exc:
    configuration_error = str(exc)
    fallback = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @fallback.get("/healthz", include_in_schema=False)
    async def misconfigured_health() -> Response:
        return JSONResponse(
            status_code=503,
            content={"status": "misconfigured", "detail": configuration_error},
            headers={"Cache-Control": "no-store"},
        )

    app = fallback
