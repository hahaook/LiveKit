import json
import os
import uuid
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from google.protobuf.timestamp_pb2 import Timestamp
from livekit import api
from pydantic import BaseModel, Field

load_dotenv(".env.local")


app = FastAPI(title="LiveKit Dispatch Bridge", version="1.0.0")

DEFAULT_AGENT_NAME = os.getenv("AGENT_NAME", "nehos-outbound-agent")


def _timestamp_to_iso(value: Any) -> Optional[str]:
    if not isinstance(value, Timestamp):
        return None
    if value.seconds == 0 and value.nanos == 0:
        return None
    return value.ToJsonString()


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
    metadata: Optional[dict[str, Any]] = Field(
        None, description="Extra metadata fields to merge into the dispatch payload"
    )
    session_options: Optional[dict[str, Any]] = Field(
        None, description="Overrides for session models, voices, and pipeline behaviour"
    )


def _compose_metadata(payload: DispatchRequest) -> dict[str, Any]:
    base: dict[str, Any] = {
        "destination": payload.destination,
        "account_code": payload.account_code,
        "transfer_target": payload.transfer_target,
        "caller_id": payload.caller_id,
        "caller_number": payload.caller_number,
        "caller_name": payload.caller_name,
    }
    if payload.metadata:
        base.update(payload.metadata)
    if payload.session_options:
        base.setdefault("session_options", {})
        if isinstance(base["session_options"], dict):
            base["session_options"].update(payload.session_options)
        else:
            base["session_options"] = payload.session_options
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
            dispatch = await client.agent_dispatch.create_dispatch(request)
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

    job_id: Optional[str] = None
    resolved_room: Optional[str] = dispatch.room or room_name

    def _job_summary(job: Any) -> dict[str, Any]:
        job_room = getattr(job, "room", None)
        room_name = getattr(job_room, "name", None) if job_room else None
        job_state = getattr(job, "state", None)
        state_summary = None
        if job_state is not None:
            state_summary = {
                "status": getattr(job_state, "status", None),
                "error": getattr(job_state, "error", None),
                "participant_identity": getattr(job_state, "participant_identity", None),
                "worker_id": getattr(job_state, "worker_id", None),
                "agent_id": getattr(job_state, "agent_id", None),
                "started_at": _timestamp_to_iso(getattr(job_state, "started_at", None)),
                "ended_at": _timestamp_to_iso(getattr(job_state, "ended_at", None)),
                "updated_at": _timestamp_to_iso(getattr(job_state, "updated_at", None)),
            }
        return {
            "id": getattr(job, "id", None),
            "dispatch_id": getattr(job, "dispatch_id", None),
            "room": room_name,
            "metadata": getattr(job, "metadata", None),
            "state": {k: v for k, v in (state_summary or {}).items() if v not in (None, "")},
        }

    job_summaries: list[dict[str, Any]] = []
    if getattr(dispatch, "state", None) and dispatch.state.jobs:
        job_summaries = [_job_summary(job) for job in dispatch.state.jobs]
        first_job = job_summaries[0]
        job_id = first_job.get("id") or first_job.get("dispatch_id")
        resolved_room = first_job.get("room") or resolved_room

    dispatch_state = {"jobs": job_summaries} if job_summaries else None

    return {
        "dispatch_id": getattr(dispatch, "id", None),
        "job_id": job_id,
        "room": resolved_room,
        "agent_name": agent_name,
        "metadata": metadata,
        "state": dispatch_state,
    }


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
