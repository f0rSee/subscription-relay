from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    url_ciphertext: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[str] = mapped_column(String(32), default="never")
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    nodes: Mapped[list[Node]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )
    profile_links: Mapped[list[ProfileSubscription]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )
    usage: Mapped[SubscriptionUsage | None] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
        uselist=False,
    )


class SubscriptionUsage(Base):
    __tablename__ = "subscription_usage"

    subscription_id: Mapped[str] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), primary_key=True
    )
    upload: Mapped[int] = mapped_column(BigInteger, default=0)
    download: Mapped[int] = mapped_column(BigInteger, default=0)
    total: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expire: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    subscription: Mapped[Subscription] = relationship(back_populates="usage")


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subscription_id: Mapped[str] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    protocol: Mapped[str] = mapped_column(String(32))
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uri_ciphertext: Mapped[str] = mapped_column(Text)
    source_position: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    subscription: Mapped[Subscription] = relationship(back_populates="nodes")
    preferences: Mapped[list[ProfileNodePreference]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    subscription_links: Mapped[list[ProfileSubscription]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    node_preferences: Mapped[list[ProfileNodePreference]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class ProfileSubscription(Base):
    __tablename__ = "profile_subscriptions"

    profile_id: Mapped[str] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    subscription_id: Mapped[str] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)

    profile: Mapped[Profile] = relationship(back_populates="subscription_links")
    subscription: Mapped[Subscription] = relationship(back_populates="profile_links")


class ProfileNodePreference(Base):
    __tablename__ = "profile_node_preferences"

    profile_id: Mapped[str] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    profile: Mapped[Profile] = relationship(back_populates="node_preferences")
    node: Mapped[Node] = relationship(back_populates="preferences")


class RelaySettings(Base):
    __tablename__ = "relay_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    deduplicate_servers: Mapped[bool] = mapped_column(Boolean, default=False)
    request_logging_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    device_tracking_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_refresh_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ClientDevice(Base):
    __tablename__ = "client_devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    user_agent: Mapped[str] = mapped_column(Text)
    ip_address: Mapped[str] = mapped_column(String(64))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    last_profile_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    profile_name: Mapped[str] = mapped_column(String(160))
    request_type: Mapped[str] = mapped_column(String(32))
    device_id: Mapped[str | None] = mapped_column(
        ForeignKey("client_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    client_name: Mapped[str] = mapped_column(String(160))
    user_agent: Mapped[str] = mapped_column(Text)
    ip_address: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
