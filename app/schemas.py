"""Pydantic schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IntegrationPayloadIn(BaseModel):
    event_type: str = Field(min_length=3, max_length=80)
    data: dict


class RetryEventIn(BaseModel):
    patched_payload: dict | None = None


class EventOut(BaseModel):
    id: int
    source: str
    event_type: str
    idempotency_key: str
    status: Literal["pending", "processed", "failed"]
    error_message: str | None


class AlertOut(BaseModel):
    severity: str
    message: str
