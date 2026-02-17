# 06 - Integration Platform (HubSpot + QuickBooks + Slack-style Alerts)

This project implements an integration core with operational controls expected by commercial teams.

## Delivered capabilities

- webhook ingestion for HubSpot and QuickBooks
- HMAC signature validation
- event idempotency control
- canonical customer sync
- invoice sync with failure detection
- alert log stream for failed events (Slack-style operational notifications)
- retry endpoint with payload patch support

## Business positioning

1. **Starter** - single integration flow with webhook reliability
2. **Growth** - multi-system sync + retries + operational alerts
3. **Enterprise** - mapping governance, SLAs, and support runbooks

## API highlights

- `POST /webhooks/hubspot`
- `POST /webhooks/quickbooks`
- `GET /events`
- `POST /events/{event_id}/retry`
- `GET /alerts`
- `GET /sync/summary`
- `POST /reset`

## Local setup

```bash
cd projects/06-integration-hubspot-quickbooks-slack
pip3 install -r requirements.txt
uvicorn app.main:app --reload --port 8005
```

## Run tests

```bash
cd projects/06-integration-hubspot-quickbooks-slack
pytest -q
```

## Docker

```bash
cd projects/06-integration-hubspot-quickbooks-slack
docker compose up --build
```
