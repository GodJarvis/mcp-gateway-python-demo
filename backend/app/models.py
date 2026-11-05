from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BusinessSystem(Base):
    __tablename__ = "business_systems"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    tools: Mapped[list[ToolConfig]] = relationship(back_populates="business_system")


class ToolConfig(Base):
    __tablename__ = "tool_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_system_id: Mapped[int] = mapped_column(ForeignKey("business_systems.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    endpoint_url: Mapped[str] = mapped_column(String(1000))
    http_method: Mapped[str] = mapped_column(String(10), default="POST")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    static_headers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    auth_type: Mapped[str] = mapped_column(String(20), default="none")
    auth_header_name: Mapped[str] = mapped_column(String(100), default="Authorization")
    auth_username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    auth_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    business_system: Mapped[BusinessSystem] = relationship(back_populates="tools")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(30), default="mcp")
    success: Mapped[bool] = mapped_column(Boolean, index=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    argument_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

