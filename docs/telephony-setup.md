# LiveKit Agent Telephony Setup Guide

This document captures the steps and configuration used so far to get the Python agent placing outbound calls through `sip.nehos.com.au`, including account-code headers, SIP transfers, and Cartesia TTS.

## 1. Dependencies

Run once from the project root to install the Cartesia plugin:

```bash
uv add livekit-plugins-cartesia
```

All other dependencies are managed through `uv` using the versions in `pyproject.toml`.

## 2. Environment variables (`.env.local`)

Populate the following keys; restart the worker any time you change them.

```ini
LIVEKIT_URL=...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
SIP_TRUNK_ID=ST_xxxxx

# Optional caller identity defaults
SIP_FROM_NUMBER=+61XXXXXXXXX
SIP_FROM_IDENTITY=LiveKitNehosHosted
SIP_DISPLAY_NAME="LiveKit Nehos Hosted"

# Cartesia TTS (optional – use if you prefer your own API key)
CARTESIA_API_KEY=sk_live_...
CARTESIA_VOICE_ID=9626c31c-bec5-4cca-baa8-f8ba9e84c8bc  # override if you want a different voice

# Logging verbosity (INFO|DEBUG)
LOG_LEVEL=INFO
```

> `SIP_FROM_NUMBER` / `SIP_FROM_IDENTITY` supply the caller ID presented to Nehos. If omitted, the code falls back to the destination number, which most carriers reject.

## 3. Outbound SIP headers & metadata

`src/agent.py` now:

- Reads job metadata to obtain `destination`, `account_code`, `transfer_target`, `caller_id`, and `caller_name`.
- Calls `CreateSIPParticipant` with `headers={"X-Account-Code": ...}` so Nehos sees the account code on the initial INVITE.
- Adds the same fields to the participant metadata for downstream logic.
- Normalises the caller identity/number so the SIP `From` header contains `SIP_FROM_NUMBER`/`SIP_FROM_IDENTITY`.

Dispatch metadata example:

```json
{
  "destination": "61402012298",
  "account_code": "em-tech-01",
  "transfer_target": "61731071901",
  "caller_id": "LiveKitNehosHosted",
  "caller_name": "LiveKit Nehos Hosted"
}
```

## 4. Starting the worker

From the project root:

```bash
uv run python src/agent.py
```

With `LOG_LEVEL=DEBUG`, you should see logs such as:

- `parsed job metadata: {...}`
- `dialing destination 61402012298 with fields {'sip_call_to': '61402012298'}`
- `outbound SIP call initiated to ...`
- `using Cartesia TTS with custom API key` (when `CARTESIA_API_KEY` is set)

## 5. Dispatching test calls

Use the LiveKit CLI (ensure you’re targeting the correct project):

```bash
lk dispatch create \
  --new-room \
  --agent-name nehos-outbound-agent \
  --metadata '{
    "destination":"61402012298",
    "account_code":"em-tech-01",
    "transfer_target":"61731071901",
    "caller_id":"LiveKitNehosHosted",
    "caller_name":"LiveKit Nehos Hosted"
  }'
```

Watch the worker log for SIP errors. A `403 Forbidden auth ID` indicates the trunk rejected the caller ID—update `caller_id`/`SIP_FROM_NUMBER` to a Nehos-approved CLI.

## 6. Transfers

`transfer_call` now normalises the transfer target into a proper `tel:` URI before calling `TransferSIPParticipant`. Ensure `transfer_target` in metadata is a full E.164 number (`61...`) or SIP URI.

> **Limitations:** SIP REFER cannot add new SIP headers such as `X-Account-Code`. Make sure any required headers are already present on the main leg. If you must send new metadata, perform a hang-up and start a new outbound call instead of REFER.

## 7. Cartesia TTS

- If `CARTESIA_API_KEY` is provided, the agent instantiates `CartesiaTTS` with your key. Otherwise it falls back to the LiveKit-managed model (`cartesia/sonic-2`).
- You can override the default voice via `CARTESIA_VOICE_ID`.

Frequent `i/o timeout` errors from Cartesia indicate network issues; verify outbound HTTPS to `api.cartesia.ai` is permitted or switch to a different TTS while troubleshooting.

## 8. Testing

Run the unit tests before deploying:

```bash
uv run pytest
```

Current coverage includes:

- Outbound call metadata/header behaviour.
- Transfer target URI normalisation.
- Safety and grounding checks inherited from the starter project.

## 9. Operational notes

- Silero VAD warnings (`inference is slower than realtime`) suggest CPU saturation. Consider running the worker on a higher-performance host, disabling Silero, or selecting a lighter STT model if latency becomes excessive.
- LiveKit dashboard → Telephony → Calls shows SIP status codes; use it to trace authentication failures or INVITE header issues.
- Nehos must whitelist LiveKit Cloud IPs and accept the caller ID you present; coordinate with their support to finalise the trunk.

## 10. n8n integration

See `docs/n8n-integration.md` for a dedicated guide covering the FastAPI dispatch bridge, expected payloads, response data, and security recommendations (including using Mikrotik firewall rules).
