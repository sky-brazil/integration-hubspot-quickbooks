"""Event processing logic for integrations."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CanonicalCustomer, IntegrationEvent, InvoiceRecord, NotificationLog


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _log_notification(db: Session, severity: str, message: str) -> None:
    db.add(
        NotificationLog(
            channel="slack",
            severity=severity,
            message=message,
        )
    )


def process_hubspot_event(db: Session, event: IntegrationEvent) -> None:
    data = event.payload
    email = str(data.get("email", "")).strip().lower()
    name = str(data.get("name", "")).strip()
    if not email or not name:
        raise ValueError("HubSpot payload missing required customer fields.")

    customer = db.scalar(select(CanonicalCustomer).where(CanonicalCustomer.email == email))
    if not customer:
        customer = CanonicalCustomer(
            email=email,
            name=name,
            external_contact_id=str(data.get("contact_id", "")) or None,
            external_company_id=str(data.get("company_id", "")) or None,
            lifecycle_stage=str(data.get("lifecycle_stage", "lead")),
        )
        db.add(customer)
    else:
        customer.name = name
        customer.external_contact_id = str(data.get("contact_id", customer.external_contact_id or "")) or None
        customer.external_company_id = str(data.get("company_id", customer.external_company_id or "")) or None
        customer.lifecycle_stage = str(data.get("lifecycle_stage", customer.lifecycle_stage))
        customer.last_synced_at = utc_now()


def process_quickbooks_event(db: Session, event: IntegrationEvent) -> None:
    data = event.payload
    invoice_id = str(data.get("invoice_id", "")).strip()
    customer_email = str(data.get("customer_email", "")).strip().lower()
    amount = float(data.get("amount", 0))

    if not invoice_id or not customer_email:
        raise ValueError("QuickBooks payload missing invoice fields.")

    if amount <= 0:
        raise ValueError("QuickBooks invoice amount must be positive.")

    invoice = db.scalar(
        select(InvoiceRecord).where(InvoiceRecord.external_invoice_id == invoice_id)
    )
    if not invoice:
        invoice = InvoiceRecord(
            external_invoice_id=invoice_id,
            customer_email=customer_email,
            amount=amount,
            currency=str(data.get("currency", "USD")).upper(),
            status=str(data.get("status", "posted")),
        )
        db.add(invoice)
    else:
        invoice.customer_email = customer_email
        invoice.amount = amount
        invoice.currency = str(data.get("currency", invoice.currency)).upper()
        invoice.status = str(data.get("status", invoice.status))
        invoice.last_synced_at = utc_now()


def process_integration_event(db: Session, event: IntegrationEvent) -> None:
    try:
        if event.source == "hubspot":
            process_hubspot_event(db, event)
        elif event.source == "quickbooks":
            process_quickbooks_event(db, event)
        else:
            raise ValueError(f"Unsupported source: {event.source}")

        event.status = "processed"
        event.error_message = None
        event.processed_at = utc_now()
    except Exception as exc:  # noqa: BLE001
        event.status = "failed"
        event.error_message = str(exc)
        event.processed_at = utc_now()
        _log_notification(
            db,
            severity="error",
            message=f"Integration event {event.idempotency_key} failed: {exc}",
        )
