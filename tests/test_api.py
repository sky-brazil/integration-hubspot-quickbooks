from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app


@pytest.fixture()
def client(tmp_path):
    database_url = f"sqlite:///{tmp_path}/test.db"
    db.reset_engine(database_url)
    db.init_db()
    with TestClient(app) as test_client:
        yield test_client


def sign_payload(payload: dict, secret: str) -> tuple[bytes, str]:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return raw, signature


def test_hubspot_webhook_idempotency_and_customer_sync(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUBSPOT_WEBHOOK_SECRET", "hubspot-secret")

    payload = {
        "id": "evt_h_001",
        "event_type": "contact.created",
        "data": {
            "contact_id": "contact_01",
            "company_id": "comp_01",
            "email": "owner@northwind.com",
            "name": "Northwind Owner",
            "lifecycle_stage": "customer",
        },
    }
    raw, signature = sign_payload(payload, "hubspot-secret")

    first = client.post(
        "/webhooks/hubspot",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-HubSpot-Event-Id": "evt_h_001",
            "X-HubSpot-Signature": signature,
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["event"]["status"] == "processed"

    second = client.post(
        "/webhooks/hubspot",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-HubSpot-Event-Id": "evt_h_001",
            "X-HubSpot-Signature": signature,
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "duplicate"

    summary = client.get("/sync/summary")
    assert summary.status_code == 200
    assert summary.json()["canonical_customers"] == 1


def test_quickbooks_failed_event_generates_alert_and_retry_works(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUICKBOOKS_WEBHOOK_SECRET", "qb-secret")

    bad_payload = {
        "id": "evt_q_001",
        "event_type": "invoice.posted",
        "data": {
            "invoice_id": "inv_001",
            "customer_email": "finance@contoso.com",
            "amount": 0,
            "currency": "USD",
            "status": "posted",
        },
    }
    raw_bad, bad_signature = sign_payload(bad_payload, "qb-secret")

    first = client.post(
        "/webhooks/quickbooks",
        content=raw_bad,
        headers={
            "Content-Type": "application/json",
            "X-QuickBooks-Event-Id": "evt_q_001",
            "X-QuickBooks-Signature": bad_signature,
        },
    )
    assert first.status_code == 200, first.text
    event = first.json()["event"]
    assert event["status"] == "failed"

    alerts = client.get("/alerts")
    assert alerts.status_code == 200
    assert len(alerts.json()) >= 1

    retried = client.post(
        f"/events/{event['id']}/retry",
        json={"patched_payload": {"amount": 240}},
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "processed"

    summary = client.get("/sync/summary")
    assert summary.status_code == 200
    assert summary.json()["invoices"] == 1


def test_reset_endpoint(client: TestClient) -> None:
    reset = client.post("/reset")
    assert reset.status_code == 200
    payload = reset.json()
    assert payload["deleted_events"] == 0
