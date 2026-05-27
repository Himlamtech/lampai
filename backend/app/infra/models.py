import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Integer, Boolean, Text, DateTime, Numeric, Index, CheckConstraint,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.infra.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeviceModel(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(17), primary_key=True)
    client_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="OFFLINE", nullable=False)
    light_power: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    brightness: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#FFD27D", nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="NORMAL", nullable=False)
    volume: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    is_playing_music: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("brightness >= 0 AND brightness <= 100", name="chk_brightness"),
        CheckConstraint("volume >= 0 AND volume <= 100", name="chk_volume"),
    )


class CommandModel(Base):
    __tablename__ = "commands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    command_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(17), ForeignKey("devices.device_id"), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(15), default="PENDING", nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_commands_device_id", "device_id"),
        Index("idx_commands_status", "status"),
    )


class ConversationModel(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id: Mapped[str] = mapped_column(String(17), ForeignKey("devices.device_id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_text: Mapped[str] = mapped_column(Text, nullable=False)
    ai_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str] = mapped_column(String(30), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage_latencies: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("idx_conversations_device_session", "device_id", "session_id"),
        Index("idx_conversations_created_at", "created_at"),
    )


class MusicCatalogModel(Base):
    __tablename__ = "music_catalog"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("idx_music_catalog_type", "type"),
    )


class SessionModel(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(17), ForeignKey("devices.device_id"), nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="connected", nullable=False)
    mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    protocol_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
