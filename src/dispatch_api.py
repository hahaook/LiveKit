import json
import os
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from livekit import api


app = FastAPI(title="LiveKit Dispatch Bridge", version="1.0.0")

DEFAULT_AGENT_NAME = os.getenv("AGENT_NAME", "nehos-outbound-agent")


class DispatchRequest(BaseModel):
    destination: str = Field(..., description="Destination phone number in E.164 format")
    account_code: str = Field(..., description="Account code header to include on the outbound call")
    transfer_target: Optional[str] = Field(
        None, description="Number or SIP URI the agent should transfer to if asked"
    )
    caller_id: Optional[str] = Field(
        None,
        description="Identity to present in SIP From header (falls back to caller_number or destination)",
    )
    caller_number: Optional[str] = Field(
        None, description="CLI number for the From header, defaults to caller_id if omitted"
    )
    caller_name: Optional[str] = Field(
        None, description="Display name for the SIP From header"
    )
    room_prefix: Optional[str] = Field(
        "outbound", description="Prefix for generated LiveKit room names"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Extra metadata fields to merge into the dispatch payload"
    )


def _compose_metadata(payload: DispatchRequest) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "destination": payload.destination,
        "account_code": payload.account_code,
        "transfer_target": payload.transfer_target,
        "caller_id": payload.caller_id,
        "caller_number": payload.caller_number,
        "caller_name": payload.caller_name,
    }
    if payload.metadata:
        base.update(payload.metadata)
    return {k: v for k, v in base.items() if v is not None}


@app.post("/dispatch")
async def dispatch_call(payload: DispatchRequest):
    agent_name = os.getenv("AGENT_NAME", DEFAULT_AGENT_NAME)
    metadata = _compose_metadata(payload)
    room_name = f"{payload.room_prefix}-{uuid.uuid4().hex[:10]}"

    request = api.CreateAgentDispatchRequest(
        agent_name=agent_name,
        room=room_name,
        metadata=json.dumps(metadata),
    )

    async with api.LiveKitAPI() as client:
        try:
            response = await client.agent_dispatch.create_dispatch(request)
        except api.TwirpError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": exc.message,
                    "code": exc.code,
                    "metadata": dict(exc.metadata),
                },
            ) from exc
        except Exception as exc:  # pragma: no cover - unexpected failures
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "dispatch_id": response.dispatch.dispatch_id,
        "job_id": response.dispatch.job.job_id,
        "room": response.dispatch.job.room.name,
        "agent_name": agent_name,
        "metadata": metadata,
    }


@app.get("/healthz")
async def healthcheck() -> Dict[str, str]:
    return {"status": "ok"}
