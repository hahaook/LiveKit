# n8n Integration Guide

This document explains how to trigger LiveKit outbound calls from n8n using the FastAPI bridge included in this project (`src/dispatch_api.py`).

## 1. Overview

n8n sends a simple HTTP `POST` to the bridge. The bridge:

1. Enriches the payload with dispatch metadata (destination, account code, caller identity, etc.).
2. Calls `CreateAgentDispatch` via the LiveKit Python SDK.
3. Returns a JSON response containing IDs you can store or use for follow-up automation.

## 2. Running the bridge

Make sure `.env.local` contains the LiveKit credentials and agent name (see `docs/telephony-setup.md`). Then start the API:

```bash
uv run uvicorn src.dispatch_api:app --host 0.0.0.0 --port 8000
```

- `GET /healthz` – returns `{ "status": "ok" }` for health checks.
- `POST /dispatch` – creates a new LiveKit dispatch.

> Secure the endpoint. A straightforward option is to expose it only inside your network and restrict access using Mikrotik firewall rules (allow n8n’s IP, block everything else).

## 3. Request payload

Send a JSON body with the following fields:

```json
{
  "destination": "61402012298",
  "account_code": "em-tech-01",
  "transfer_target": "61731071901",
  "caller_id": "LiveKitNehosHosted",
  "caller_number": "+61123456789",
  "caller_name": "LiveKit Nehos Hosted",
  "metadata": {
    "ticket_id": "INC-1234"
  }
}
```

- `destination` and `account_code` are required.
- `transfer_target` supplies the number the agent should use if it hands off the call.
- `caller_id` / `caller_number` / `caller_name` override the SIP `From` identity.
- `metadata` is optional; any keys you include are merged into the dispatch metadata and forwarded to the agent session.

## 4. Response payload

Example success response:

```json
{
  "dispatch_id": "AD_abc123",
  "job_id": "AJ_def456",
  "room": "outbound-9f1a2b3c4d",
  "agent_name": "nehos-outbound-agent",
  "metadata": {
    "destination": "61402012298",
    "account_code": "em-tech-01",
    "transfer_target": "61731071901",
    "caller_id": "LiveKitNehosHosted",
    "caller_number": "+61123456789",
    "caller_name": "LiveKit Nehos Hosted",
    "ticket_id": "INC-1234"
  }
}
```

Store these identifiers in n8n if you need to reconcile the LiveKit call later (e.g., writing to a CRM or support ticket).

If LiveKit returns an error (invalid trunk, bad credentials, etc.) the API responds with HTTP 502 and includes the Twirp error payload for debugging.

## 5. Example n8n workflow

1. **Trigger node** – receive call parameters (e.g., webhook from CRM).
2. **Set / Function node** – build the JSON payload.
3. **HTTP Request node** – configure:
   - Method: `POST`
   - URL: `http://<bridge-host>:8000/dispatch`
   - Headers: `Content-Type: application/json`
   - Body: Raw JSON from step 2.
4. **Switch / IF node** – inspect `statusCode` and `json.dispatch_id`.
5. **Additional nodes** – record the job/dispatch IDs, send notifications, etc.

Because the bridge handles LiveKit authentication, n8n doesn’t need to manage JWTs. Keep the endpoint private and front it with Mikrotik firewall rules (allow n8n, deny public traffic), or put it behind an authenticated reverse proxy if it must cross the public internet.

## 6. Troubleshooting tips

- A 502 response with `"message": "403 Forbidden auth ID"` indicates Nehos rejected the caller ID. Adjust the `caller_id` / `caller_number` values to an approved number.
- Verify the bridge can reach LiveKit by hitting `/healthz`. If the worker isn’t running or credentials are wrong, dispatch attempts will fail.
- For high availability, consider running the bridge and worker on separate hosts behind your firewall, both restricted via Mikrotik rules.
