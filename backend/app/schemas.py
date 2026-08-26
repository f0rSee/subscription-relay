from __future__ import annotations

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
