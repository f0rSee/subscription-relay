from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=512)


class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    url: str = Field(min_length=8, max_length=4096)
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=10000)


class SubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    url: str | None = Field(default=None, min_length=8, max_length=4096)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=10000)


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    subscription_ids: list[str] = Field(default_factory=list)


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    enabled: bool | None = None
    subscription_ids: list[str] | None = None
    rotate_token: bool = False


class NodeOrderUpdate(BaseModel):
    node_ids: list[str] = Field(max_length=10000)


class RelaySettingsUpdate(BaseModel):
    deduplicate_servers: bool | None = None
    request_logging_enabled: bool | None = None
    device_tracking_enabled: bool | None = None
    auto_refresh_enabled: bool | None = None


class AuthSessionResponse(BaseModel):
    authenticated: bool
    admin_configured: bool
    username: str | None = None
    csrf_token: str | None = None


class DashboardResponse(BaseModel):
    subscriptions: int
    healthy_subscriptions: int
    nodes: int
    profiles: int
    request_logs: int
    devices: int
    persistent_storage: bool


class SubscriptionResponse(BaseModel):
    id: str
    name: str
    url_hint: str
    enabled: bool
    priority: int
    status: str
    node_count: int
    last_error: str | None
    last_sync_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SyncResponse(BaseModel):
    status: str
    node_count: int


class ProfileResponse(BaseModel):
    id: str
    name: str
    token: str
    enabled: bool
    subscription_ids: list[str]
    url: str
    created_at: datetime | None = None


class ProfileNodeResponse(BaseModel):
    id: str
    name: str
    protocol: str
    host: str | None
    subscription_id: str
    subscription_name: str
    duplicate: bool


class UpdatedResponse(BaseModel):
    updated: int


class RequestLogResponse(BaseModel):
    id: str
    profile_id: str | None
    profile_name: str
    request_type: str
    device_id: str | None
    client_name: str
    user_agent: str
    ip_address: str
    status_code: int
    node_count: int
    error: str | None
    requested_at: datetime


class ClientDeviceResponse(BaseModel):
    id: str
    name: str
    user_agent: str
    ip_address: str
    request_count: int
    last_profile_name: str | None
    last_status_code: int | None
    first_seen_at: datetime
    last_seen_at: datetime


class RelaySettingsResponse(BaseModel):
    deduplicate_servers: bool
    request_logging_enabled: bool
    device_tracking_enabled: bool
    auto_refresh_enabled: bool
    updated_at: datetime
