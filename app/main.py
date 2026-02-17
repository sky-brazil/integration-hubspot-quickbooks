"""FastAPI app for CRM/finance integration workflows."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db, init_db
from .models import CanonicalCustomer, IntegrationEvent, InvoiceRecord, NotificationLog
from .processor import process_integration_event
from .schemas import AlertOut, EventOut, IntegrationPayloadIn, RetryEventIn
from .security import verify_hmac_signature


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Integration Platform API",
    description="HubSpot + QuickBooks integration core with idempotency, retries, and alerts.",
    version="0.1.0",
    lifespan=lifespan,
)


def _get_existing_event(db: Session, idempotency_key: str) -> IntegrationEvent | None:
    return db.scalar(
        select(IntegrationEvent).where(IntegrationEvent.idempotency_key == idempotency_key)
    )


def _save_and_process_event(
    db: Session,
    *,
    source: str,
    event_type: str,
    idempotency_key: str,
    payload: dict,
) -> IntegrationEvent:
    event = IntegrationEvent(
        source=source,
        event_type=event_type,
        idempotency_key=idempotency_key,
        payload=payload,
        status="pending",
    )
    db.add(event)
    db.flush()
    process_integration_event(db, event)
    db.commit()
    db.refresh(event)
    return event


async def _ingest_webhook(
    request: Request,
    db: Session,
    *,
    source: str,
    secret_env: str,
    event_id_header: str,
    signature_header: str,
) -> dict:
    raw_payload = await request.body()
    signature = request.headers.get(signature_header)
    secret = os.getenv(secret_env)
    if not verify_hmac_signature(raw_payload, signature, secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        ) from None

    parsed = IntegrationPayloadIn.model_validate(payload)
    idempotency_key = request.headers.get(event_id_header) or str(payload.get("id", "")).strip()
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing event id for idempotency.",
        )

    existing_event = _get_existing_event(db, idempotency_key)
    if existing_event:
        return {
            "status": "duplicate",
            "event": EventOut(
                id=existing_event.id,
                source=existing_event.source,
                event_type=existing_event.event_type,
                idempotency_key=existing_event.idempotency_key,
                status=existing_event.status,
                error_message=existing_event.error_message,
            ).model_dump(),
        }

    event = _save_and_process_event(
        db,
        source=source,
        event_type=parsed.event_type,
        idempotency_key=idempotency_key,
        payload=parsed.data,
    )
    return {
        "status": "processed",
        "event": EventOut(
            id=event.id,
            source=event.source,
            event_type=event.event_type,
            idempotency_key=event.idempotency_key,
            status=event.status,
            error_message=event.error_message,
        ).model_dump(),
    }


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/hubspot")
async def hubspot_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    return await _ingest_webhook(
        request,
        db,
        source="hubspot",
        secret_env="HUBSPOT_WEBHOOK_SECRET",
        event_id_header="X-HubSpot-Event-Id",
        signature_header="X-HubSpot-Signature",
    )


@app.post("/webhooks/quickbooks")
async def quickbooks_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    return await _ingest_webhook(
        request,
        db,
        source="quickbooks",
        secret_env="QUICKBOOKS_WEBHOOK_SECRET",
        event_id_header="X-QuickBooks-Event-Id",
        signature_header="X-QuickBooks-Signature",
    )


@app.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)) -> list[EventOut]:
    rows = list(db.scalars(select(IntegrationEvent).order_by(IntegrationEvent.id.desc())).all())
    return [
        EventOut(
            id=row.id,
            source=row.source,
            event_type=row.event_type,
            idempotency_key=row.idempotency_key,
            status=row.status,
            error_message=row.error_message,
        )
        for row in rows
    ]


@app.post("/events/{event_id}/retry")
def retry_event(
    event_id: int,
    payload: RetryEventIn,
    db: Session = Depends(get_db),
) -> EventOut:
    event = db.get(IntegrationEvent, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    if payload.patched_payload:
        event.payload = {**event.payload, **payload.patched_payload}
    event.status = "pending"
    event.error_message = None
    process_integration_event(db, event)
    db.commit()
    db.refresh(event)
    return EventOut(
        id=event.id,
        source=event.source,
        event_type=event.event_type,
        idempotency_key=event.idempotency_key,
        status=event.status,
        error_message=event.error_message,
    )


@app.get("/alerts", response_model=list[AlertOut])
def list_alerts(db: Session = Depends(get_db)) -> list[AlertOut]:
    rows = list(db.scalars(select(NotificationLog).order_by(NotificationLog.id.desc())).all())
    return [AlertOut(severity=row.severity, message=row.message) for row in rows]


@app.get("/sync/summary")
def sync_summary(db: Session = Depends(get_db)) -> dict[str, int]:
    customers = len(list(db.scalars(select(CanonicalCustomer.id)).all()))
    invoices = len(list(db.scalars(select(InvoiceRecord.id)).all()))
    failed_events = len(
        list(
            db.scalars(
                select(IntegrationEvent.id).where(IntegrationEvent.status == "failed")
            ).all()
        )
    )
    return {
        "canonical_customers": customers,
        "invoices": invoices,
        "failed_events": failed_events,
    }


@app.post("/reset")
def reset_data(db: Session = Depends(get_db)) -> dict[str, int]:
    deleted_notifications = db.query(NotificationLog).delete()
    deleted_invoices = db.query(InvoiceRecord).delete()
    deleted_customers = db.query(CanonicalCustomer).delete()
    deleted_events = db.query(IntegrationEvent).delete()
    db.commit()
    return {
        "deleted_events": int(deleted_events),
        "deleted_customers": int(deleted_customers),
        "deleted_invoices": int(deleted_invoices),
        "deleted_notifications": int(deleted_notifications),
    }
