import json
import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from livekit import api
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    cli,
    function_tool,
    RunContext,
    get_job_context,
    metrics,
)
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.cartesia import TTS as CartesiaTTS
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")

log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_name, logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def _parse_metadata(raw_metadata: Optional[str]) -> Dict[str, Any]:
    if not raw_metadata:
        return {}

    try:
        parsed = json.loads(raw_metadata)
        if isinstance(parsed, dict):
            logger.debug("parsed job metadata: %s", parsed)
            return parsed
        logger.warning("job metadata is not a JSON object; ignoring")
    except json.JSONDecodeError:
        logger.warning("failed to parse job metadata as JSON", exc_info=True)
    return {}


def _destination_fields(destination: str) -> Dict[str, str]:
    dest = destination.strip()
    if not dest:
        return {}

    normalized = dest
    if normalized.lower().startswith("sip:"):
        normalized = normalized[4:]
    elif normalized.lower().startswith("tel:"):
        normalized = normalized[4:]

    return {"sip_call_to": normalized}


def _format_tel_uri(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return cleaned

    lower = cleaned.lower()
    if lower.startswith(("sip:", "tel:")):
        return cleaned

    if "@" in cleaned:
        return f"sip:{cleaned}"

    if cleaned.startswith("+"):
        return f"tel:{cleaned}"

    return f"tel:+{cleaned}"


def _resolve_caller_number(call_context: Dict[str, Any]) -> Optional[str]:
    return (
        call_context.get("caller_number")
        or call_context.get("caller_cli")
        or call_context.get("caller_id")
        or os.getenv("SIP_FROM_NUMBER")
        or os.getenv("SIP_FROM_IDENTITY")
        or os.getenv("DEFAULT_CALLER_ID")
    )


def _resolve_caller_identity(call_context: Dict[str, Any], fallback: str) -> str:
    return (
        call_context.get("participant_identity")
        or call_context.get("caller_identity")
        or call_context.get("caller_id")
        or os.getenv("SIP_FROM_IDENTITY")
        or os.getenv("DEFAULT_CALLER_ID")
        or fallback
    )


async def initiate_outbound_call(ctx: JobContext, call_context: Dict[str, Any]) -> None:
    destination = call_context.get("destination")
    if not destination:
        return

    sip_trunk_id = os.getenv("SIP_TRUNK_ID")
    if not sip_trunk_id:
        logger.error("SIP_TRUNK_ID environment variable is required for outbound SIP calls")
        return

    participant_identity = _resolve_caller_identity(call_context, fallback=destination)
    call_context["sip_participant_identity"] = participant_identity
    call_context.setdefault("from_identity", participant_identity)

    account_code = call_context.get("account_code")
    headers: Dict[str, str] = {}
    if account_code:
        headers["X-Account-Code"] = account_code

    metadata_payload = {
        "destination": destination,
        "account_code": account_code,
        "transfer_target": call_context.get("transfer_target"),
        "from_identity": participant_identity,
        "caller_number": call_context.get("caller_number"),
        "caller_name": call_context.get("caller_name"),
        "caller_id": call_context.get("caller_id"),
    }

    destination_fields = _destination_fields(destination)
    if not destination_fields:
        logger.error("destination did not resolve to a valid SIP target: %s", destination)
        return
    logger.debug("dialing destination %s with fields %s", destination, destination_fields)

    request_args = {
        "room_name": ctx.room.name,
        "sip_trunk_id": sip_trunk_id,
        "participant_identity": participant_identity,
        "wait_until_answered": True,
        "participant_metadata": json.dumps(metadata_payload),
        **destination_fields,
    }
    caller_number = _resolve_caller_number(call_context)
    if caller_number:
        request_args["sip_number"] = caller_number

    if headers:
        request_args["headers"] = headers
    display_name = call_context.get("caller_name") or os.getenv("SIP_DISPLAY_NAME")
    if display_name:
        request_args["display_name"] = display_name

    try:
        await ctx.api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(**request_args)
        )
        logger.info(
            "outbound SIP call initiated to %s via trunk %s",
            destination,
            sip_trunk_id,
        )
    except api.TwirpError as exc:
        logger.error(
            "failed to create SIP participant: %s (SIP %s %s)",
            exc.message,
            exc.metadata.get("sip_status_code"),
            exc.metadata.get("sip_status"),
        )
        ctx.shutdown()
    except Exception:
        logger.exception("unexpected error creating SIP participant")
        ctx.shutdown()


def _transfer_target_uri(target: str) -> Optional[str]:
    if not target:
        return None

    fields = _destination_fields(target)
    candidate = fields.get("sip_call_to") or fields.get("sip_number")
    if not candidate:
        return None
    return _format_tel_uri(candidate)


class Assistant(Agent):
    def __init__(self, call_context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            instructions="""You are a helpful voice AI assistant. The user is interacting with you via voice, even if you perceive the conversation as text.
            You eagerly assist users with their questions by providing information from your extensive knowledge.
            Your responses are concise, to the point, and without any complex formatting or punctuation including emojis, asterisks, or other symbols.
            You are curious, friendly, and have a sense of humor.""",
        )
        self.call_context: Dict[str, Any] = call_context or {}

    def update_call_context(self, context: Dict[str, Any]) -> None:
        self.call_context.update(context)

    @function_tool()
    async def transfer_call(self, ctx: RunContext) -> str:
        """Transfer the caller to a pre-configured destination."""

        transfer_target = self.call_context.get("transfer_target")
        if not transfer_target:
            logger.warning("transfer requested without transfer_target in context")
            return "No transfer target is configured for this call."

        job_ctx = get_job_context()
        if job_ctx is None:
            logger.warning("transfer requested without active job context")
            return "I cannot transfer the call right now."

        participant_identity = self.call_context.get("sip_participant_identity")
        if not participant_identity:
            logger.warning("transfer requested without sip participant identity")
            return "I cannot transfer the call right now."

        transfer_uri = _transfer_target_uri(transfer_target)
        if not transfer_uri:
            logger.error("transfer target is invalid: %s", transfer_target)
            return "I cannot transfer the call right now."

        announcement = ctx.session.generate_reply(
            instructions="Let the caller know that you are transferring them to another agent."
        )
        await announcement.wait_for_playout()

        try:
            await job_ctx.api.sip.transfer_sip_participant(
                api.TransferSIPParticipantRequest(
                    room_name=job_ctx.room.name,
                    participant_identity=participant_identity,
                    transfer_to=transfer_uri,
                )
            )
        except Exception:
            logger.exception("failed to transfer SIP participant")
            return "I could not transfer the call."

        return "Transfer initiated."

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    call_context = _parse_metadata(ctx.job.metadata)
    assistant = Assistant(call_context=call_context)

    cartesia_api_key = os.getenv("CARTESIA_API_KEY")
    cartesia_voice = os.getenv("CARTESIA_VOICE_ID", DEFAULT_CARTESIA_VOICE)
    if cartesia_api_key:
        logger.info("using Cartesia TTS with custom API key")
        tts_backend: Any = CartesiaTTS(
            api_key=cartesia_api_key,
            model="sonic-2",
            voice=cartesia_voice,
        )
    else:
        tts_backend = f"cartesia/sonic-2:{cartesia_voice}"
        logger.debug("CARTESIA_API_KEY not set; using LiveKit-managed Cartesia TTS")

    # Set up a voice AI pipeline using OpenAI, Cartesia, AssemblyAI, and the LiveKit turn detector
    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        stt="assemblyai/universal-streaming:en",
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        llm="openai/gpt-4.1-mini",
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
        tts=tts_backend,
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
    )

    # To use a realtime model instead of a voice pipeline, use the following session setup instead.
    # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))
    # 1. Install livekit-agents[openai]
    # 2. Set OPENAI_API_KEY in .env.local
    # 3. Add `from livekit.plugins import openai` to the top of this file
    # 4. Use the following session setup instead of the version above
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel(voice="marin")
    # )

    # Metrics collection, to measure pipeline performance
    # For more information, see https://docs.livekit.io/agents/build/metrics/
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/models/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=assistant,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # For telephony applications, use `BVCTelephony` for best results
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Join the room and connect to the user
    await ctx.connect()

    await initiate_outbound_call(ctx, call_context)


if __name__ == "__main__":
    agent_name = os.getenv("AGENT_NAME", "nehos-outbound-agent")
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=agent_name,
        )
    )
DEFAULT_CARTESIA_VOICE = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
