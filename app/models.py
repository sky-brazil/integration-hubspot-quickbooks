"""SQLAlchemy models for integration processing."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IntegrationEvent(Base):
    __tablename__ = "integration_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(150), nullable=False, unique=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CanonicalCustomer(Base):
    __tablename__ = "canonical_customers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_contact_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    external_company_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    lifecycle_stage: Mapped[str] = mapped_column(String(40), nullable=False, default="lead")
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class InvoiceRecord(Base):
    __tablename__ = "invoice_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_invoice_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="posted")
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="slack")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
