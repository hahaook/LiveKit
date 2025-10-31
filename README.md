<a href="https://livekit.io/">
  <img src="./.github/assets/livekit-mark.png" alt="LiveKit logo" width="100" height="100">
</a>

# LiveKit Agents Starter - Python

A complete starter project for building voice AI apps with [LiveKit Agents for Python](https://github.com/livekit/agents) and [LiveKit Cloud](https://cloud.livekit.io/).

The starter project includes:

- A simple voice AI assistant, ready for extension and customization
- A voice AI pipeline with [models](https://docs.livekit.io/agents/models) from OpenAI, Cartesia, and AssemblyAI served through LiveKit Cloud
  - Easily integrate your preferred [LLM](https://docs.livekit.io/agents/models/llm/), [STT](https://docs.livekit.io/agents/models/stt/), and [TTS](https://docs.livekit.io/agents/models/tts/) instead, or swap to a realtime model like the [OpenAI Realtime API](https://docs.livekit.io/agents/models/realtime/openai)
- Eval suite based on the LiveKit Agents [testing & evaluation framework](https://docs.livekit.io/agents/build/testing/)
- [LiveKit Turn Detector](https://docs.livekit.io/agents/build/turns/turn-detector/) for contextually-aware speaker detection, with multilingual support
- [Background voice cancellation](https://docs.livekit.io/home/cloud/noise-cancellation/)
- Integrated [metrics and logging](https://docs.livekit.io/agents/build/metrics/)
- A Dockerfile ready for [production deployment](https://docs.livekit.io/agents/ops/deployment/)

This starter app is compatible with any [custom web/mobile frontend](https://docs.livekit.io/agents/start/frontend/) or [SIP-based telephony](https://docs.livekit.io/agents/start/telephony/).

## Coding agents and MCP

This project is designed to work with coding agents like [Cursor](https://www.cursor.com/) and [Claude Code](https://www.anthropic.com/claude-code). 

To get the most out of these tools, install the [LiveKit Docs MCP server](https://docs.livekit.io/mcp).

For Cursor, use this link:

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-light.svg)](https://cursor.com/en-US/install-mcp?name=livekit-docs&config=eyJ1cmwiOiJodHRwczovL2RvY3MubGl2ZWtpdC5pby9tY3AifQ%3D%3D)

For Claude Code, run this command:

```
claude mcp add --transport http livekit-docs https://docs.livekit.io/mcp
```

For Codex CLI, use this command to install the server:
```
codex mcp add --url https://docs.livekit.io/mcp livekit-docs
```

For Gemini CLI, use this command to install the server:
```
gemini mcp add --transport http livekit-docs https://docs.livekit.io/mcp
```

The project includes a complete [AGENTS.md](AGENTS.md) file for these assistants. You can modify this file  your needs. To learn more about this file, see [https://agents.md](https://agents.md).

## Dev Setup

Clone the repository and install dependencies to a virtual environment:

```console
cd agent-starter-python
uv sync
```

Sign up for [LiveKit Cloud](https://cloud.livekit.io/) then set up the environment by copying `.env.example` to `.env.local` and filling in the required keys:

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`

Optional telemetry & workflow integrations:

- `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` to forward OpenTelemetry traces to Langfuse.
- `N8N_WEBHOOK_URL` to receive an end-of-call JSON report with usage metrics and collected session events.
- `DEFAULT_LLM_MODEL`, `DEFAULT_STT_MODEL`, and `CARTESIA_MODEL` to tweak the default session models when n8n does not override them.
- `VOICEMAIL_SILENCE_TIMEOUT` (seconds) to adjust how long the agent waits for a human response before auto-hanging up on suspected voicemail.
- `MAX_CALL_DURATION_SECONDS`, `CALL_DURATION_OVERRIDE_URL`, and `CALL_DURATION_OVERRIDE_POLL_SECONDS` to enforce automatic hangups for runaway calls (details below).
- `EGRESS_ENDPOINT`, `EGRESS_BUCKET`, `EGRESS_ACCESS_KEY`, `EGRESS_SECRET_KEY`, optional `EGRESS_REGION`, `EGRESS_PATH_PREFIX`, `EGRESS_FORCE_PATH_STYLE`, and `EGRESS_ROOM_PREFIX` (e.g. `N101222`) to control recording uploads and filename prefixes.

You can load the LiveKit environment automatically using the [LiveKit CLI](https://docs.livekit.io/home/cli/cli-setup):

```bash
lk cloud auth
lk app env -w -d .env.local
```

## Run the agent

Before your first run, you must download certain models such as [Silero VAD](https://docs.livekit.io/agents/build/turns/vad/) and the [LiveKit turn detector](https://docs.livekit.io/agents/build/turns/turn-detector/):

```console
uv run python src/agent.py download-files
```

Next, run this command to speak to your agent directly in your terminal:

```console
uv run python src/agent.py console
```

To run the agent for use with a frontend or telephony, use the `dev` command:

```console
uv run python src/agent.py dev
```

In production, use the `start` command:

```console
uv run python src/agent.py start
```

## Frontend & Telephony

Get started quickly with our pre-built frontend starter apps, or add telephony support:

| Platform | Link | Description |
|----------|----------|-------------|
| **Web** | [`livekit-examples/agent-starter-react`](https://github.com/livekit-examples/agent-starter-react) | Web voice AI assistant with React & Next.js |
| **iOS/macOS** | [`livekit-examples/agent-starter-swift`](https://github.com/livekit-examples/agent-starter-swift) | Native iOS, macOS, and visionOS voice AI assistant |
| **Flutter** | [`livekit-examples/agent-starter-flutter`](https://github.com/livekit-examples/agent-starter-flutter) | Cross-platform voice AI assistant app |
| **React Native** | [`livekit-examples/voice-assistant-react-native`](https://github.com/livekit-examples/voice-assistant-react-native) | Native mobile app with React Native & Expo |
| **Android** | [`livekit-examples/agent-starter-android`](https://github.com/livekit-examples/agent-starter-android) | Native Android app with Kotlin & Jetpack Compose |
| **Web Embed** | [`livekit-examples/agent-starter-embed`](https://github.com/livekit-examples/agent-starter-embed) | Voice AI widget for any website |
| **Telephony** | [📚 Documentation](https://docs.livekit.io/agents/start/telephony/) | Add inbound or outbound calling to your agent |

For advanced customization, see the [complete frontend guide](https://docs.livekit.io/agents/start/frontend/).

## Tests and evals

This project includes a complete suite of evals, based on the LiveKit Agents [testing & evaluation framework](https://docs.livekit.io/agents/build/testing/). To run them, use `pytest`.

```console
uv run pytest
```

## Call duration watchdog & n8n overrides

Outbound SIP runs can occasionally stall if the PSTN leg drops without a clean BYE. The agent now includes a watchdog that hangs up automatically when a soft limit is hit.

- Set `MAX_CALL_DURATION_SECONDS` (defaults to 120) to establish the base timeout.
- Optional per-job overrides can be supplied in the dispatch metadata as `max_call_duration_seconds`.
- To tune the timeout dynamically, expose an HTTP endpoint (for example with n8n) and point `CALL_DURATION_OVERRIDE_URL` at it. The watcher polls this endpoint every `CALL_DURATION_OVERRIDE_POLL_SECONDS` (default 30s) and updates its deadline if the response changes.

The override endpoint must return JSON with one of the following keys. Values must be whole seconds (>=0); returning `0` or a negative value disables the watchdog entirely.

```json
{
  "max_duration_seconds": 300
}
```

Recognised field names:

- `max_duration_seconds`
- `max_call_duration_seconds`
- `maxDurationSeconds`
- `maxCallDurationSeconds`

### Example n8n flow

1. **HTTP Request node** (method GET)  
   - Path: `/livekit/call-limit`
   - Authentication as desired.
2. **Function node** (optional)  
   - Use previous call context (e.g. via `/metrics` webhook or an n8n data store) to decide on a limit:

   ```javascript
   // items[0].json contains whatever state you track
   const defaultLimit = 120; // seconds
   const vipNumber = '61402012298';

   const outboundNumber = $json.destination ?? null;
   const limit = outboundNumber === vipNumber ? 0 : defaultLimit;

   return [{ json: { max_duration_seconds: limit } }];
   ```

3. **Respond to Webhook node**  
   - Return the JSON body produced by the Function node. n8n will emit it back to the agent.

With that pipeline in place the agent:

- Starts every call at the configured base limit.
- Polls the n8n endpoint on the configured interval.
- Immediately hangs up once the deadline is reached, logging `Maximum call duration reached`.
- Stops polling if the endpoint returns `0` (disabled) or the call terminates normally.

The override URL is read both from the environment and the job metadata (`session_options.max_call_duration_override_url` or `call_context.max_call_duration_override_url`), so you can control a subset of calls independently while keeping a global default in `.env.local`.

## Using this template repo for your own project

Once you've started your own project based on this repo, you should:

1. **Check in your `uv.lock`**: This file is currently untracked for the template, but you should commit it to your repository for reproducible builds and proper configuration management. (The same applies to `livekit.toml`, if you run your agents in LiveKit Cloud)

2. **Remove the git tracking test**: Delete the "Check files not tracked in git" step from `.github/workflows/tests.yml` since you'll now want this file to be tracked. These are just there for development purposes in the template repo itself.

3. **Add your own repository secrets**: You must [add secrets](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/using-secrets-in-github-actions) for `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` so that the tests can run in CI.

## Deploying to production

This project is production-ready and includes a working `Dockerfile`. To deploy it to LiveKit Cloud or another environment, see the [deploying to production](https://docs.livekit.io/agents/ops/deployment/) guide.

## Self-hosted LiveKit

You can also self-host LiveKit instead of using LiveKit Cloud. See the [self-hosting](https://docs.livekit.io/home/self-hosting/) guide for more information. If you choose to self-host, you'll need to also use [model plugins](https://docs.livekit.io/agents/models/#plugins) instead of LiveKit Inference and will need to remove the [LiveKit Cloud noise cancellation](https://docs.livekit.io/home/cloud/noise-cancellation/) plugin.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
