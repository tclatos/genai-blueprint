# LangChain / DeepAgent Integration with Microsoft Copilot Studio

> **Terminology note**
> - **Microsoft Copilot Studio** — Microsoft's low-code platform (part of Microsoft 365) for building, configuring, and publishing AI agents to Teams, M365 apps, and other channels. Formerly Power Virtual Agents.
> - **GitHub Copilot** — The AI coding assistant in VS Code. Unrelated to this document.
> - **Microsoft 365 Agents SDK** — The Python SDK for building bots/agents that connect to Microsoft Copilot Studio, Teams, and other M365 channels via Azure Bot Service.

---

## Overview

This document describes how to expose LangChain/DeepAgent-based agents (with Skills, Tools, and shell command execution) as a bot registered in **Microsoft Copilot Studio**, using the **Microsoft 365 Agents SDK for Python**. Streamlit remains a parallel direct-call UI to the same agent backend.

---

## Architecture

```
                     ┌─────────────────────────────────────────┐
                     │          Python Backend                  │
                     │                                          │
  Copilot Studio ←→ Azure Bot Service ←→  M365 Agent endpoint  │
  (Teams, M365)       (channel routing)   (M365 Agents SDK)    │
                                                 ↓             │
  Streamlit UI ───────────────────────→  LangChain Agent       │
  (direct in-process)                     (DeepAgent/ReAct)    │
                                           ↓    ↓    ↓         │
                                         Tools Skills Shell    │
                                          (genai-tk sandbox)   │
                     └─────────────────────────────────────────┘
```

The Streamlit pages in `genai_blueprint/webapp/pages/demos/` continue to call LangChain agents **directly in-process** — no M365 Agents SDK layer involved. Microsoft Copilot Studio is an additional channel.

---

## Integration Models

### Model A — LangChain as Orchestrator (Recommended)

LangChain handles **all** orchestration. Microsoft Copilot Studio acts solely as a user-facing channel and conversation router.

- Your DeepAgent retains full control of planning, tool selection, skill loading, and shell execution
- Copilot Studio's built-in generative AI orchestration is bypassed
- Users interact via Teams, M365 Chat, or any connected channel

### Model B — Copilot Studio as Orchestrator (Actions)

Copilot Studio's built-in AI orchestrates and calls your LangChain capabilities as **OpenAPI Actions**.

- **Not recommended** for DeepAgent use cases — Copilot Studio's orchestrator overrides your agent's planning loop
- Suitable only for exposing discrete, stateless tool endpoints

---

## Implementation

### 1. Microsoft 365 Agents SDK for Python

The SDK is at [github.com/microsoft/agents-sdk-python](https://github.com/microsoft/agents-sdk-python) (preview as of 2026).

```bash
uv add microsoft-agents-hosting-aiohttp microsoft-agents-bot-builder
```

Add to `pyproject.toml`:
```toml
[project.optional-dependencies]
m365-agent = [
    "microsoft-agents-hosting-aiohttp",
    "microsoft-agents-bot-builder",
]
```

### 2. Agent Handler

```python
# genai_blueprint/main/m365_agent.py
from microsoft.agents.bot_builder import ActivityHandler, TurnContext, MessageFactory
from microsoft.agents.core.models import ChannelAccount

from genai_tk.agents.langchain.config import resolve_profile
from genai_tk.config_mgmt.config_mngr import global_config
from genai_blueprint.main.agent_factory import build_agent  # your existing factory


class LangChainAgent(ActivityHandler):
    """M365 Agents SDK handler that delegates to the LangChain DeepAgent."""

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        user_input = turn_context.activity.text or ""
        if not user_input.strip():
            return

        config = global_config()
        profile_key = config.get("m365_agent.agent_profile", "research")
        profile = resolve_profile(config, profile_key)
        agent = build_agent(profile)

        result = await agent.ainvoke(
            {"input": user_input},
            config={
                "configurable": {
                    # Key on conversation ID for per-session memory isolation
                    "session_id": turn_context.activity.conversation.id,
                }
            },
        )
        await turn_context.send_activity(
            MessageFactory.text(result.get("output", ""))
        )

    async def on_members_added_activity(
        self, members_added: list[ChannelAccount], turn_context: TurnContext
    ) -> None:
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    MessageFactory.text("Hello! How can I help you today?")
                )
```

### 3. Bot Endpoint (aiohttp)

```python
# genai_blueprint/main/m365_app.py
from aiohttp import web
from microsoft.agents.hosting.aiohttp import CloudAdapter, Request, Response
from microsoft.agents.core import ConfigurationBotFrameworkAuthentication

from genai_tk.config_mgmt.config_mngr import global_config
from genai_blueprint.main.m365_agent import LangChainAgent


def _make_adapter() -> CloudAdapter:
    config = global_config()
    auth_config = ConfigurationBotFrameworkAuthentication(
        MicrosoftAppId=config.get("m365_agent.app_id", ""),
        MicrosoftAppPassword=config.get("m365_agent.app_password", ""),
    )
    return CloudAdapter(auth_config)


_adapter = _make_adapter()
_agent = LangChainAgent()


async def messages(req: web.Request) -> web.Response:
    return await _adapter.process(Request(req), _agent, Response())


app = web.Application()
app.router.add_post("/api/messages", messages)
```

### 4. Conversation Memory / Session Keying

Key on `turn_context.activity.conversation.id` for isolated per-conversation memory:

```python
from langchain_community.chat_message_histories import SQLChatMessageHistory

history = SQLChatMessageHistory(
    session_id=turn_context.activity.conversation.id,
    connection_string="sqlite:///data/sessions/m365_sessions.db",
)
```

### 5. Configuration

Add to `config/app_conf.yaml`:

```yaml
m365_agent:
  app_id: ${oc.env:M365_BOT_APP_ID,}
  app_password: ${oc.env:M365_BOT_APP_PASSWORD,}
  agent_profile: research   # default genai-tk agent profile key
```

### 6. Azure Bot Resource Registration

1. Create an **Azure Bot** resource in the Azure Portal (free F0 tier for development)
2. Under **Configuration**, set the **Messaging endpoint**:
   - Production: `https://<your-host>/api/messages`
   - Local dev: use `ngrok http 8000` and set the ngrok HTTPS URL
3. Copy the **App ID** and generate a **Client Secret** (App Password) — store them in `.env`, never in YAML committed to source control:
   ```bash
   export M365_BOT_APP_ID=<your-app-id>
   export M365_BOT_APP_PASSWORD=<your-client-secret>
   ```

### 7. Connect to Microsoft Copilot Studio

1. Open **Microsoft Copilot Studio** → create or open an agent
2. Go to **Settings → Channels → Azure Bot Service**
3. Provide the Azure Bot resource App ID and connection details
4. Under the agent's **Generative AI** settings, configure fallback to your registered Azure Bot so Copilot Studio routes to your LangChain agent
5. Publish the agent to Teams or other M365 channels

---

## Compatibility Matrix

| Feature | Status | Notes |
|---|---|---|
| LangChain Tools (`@tool`) | ✅ Full | Executed server-side; invisible to Copilot Studio |
| SKILL.md / Skills system | ✅ Full | Agent reads skills during planning; not exposed to M365 |
| Shell / sandbox (`genai-tk sandbox`) | ✅ Full | Runs in Docker on your server |
| DeepAgent / ReAct planning loop | ✅ Full | Model A only — Copilot Studio orchestration bypassed |
| Streamlit UI | ✅ Full | Direct in-process calls; no M365 SDK layer needed |
| Streaming responses | ⚠️ Partial | M365 Agents SDK supports activity streaming; requires extra implementation |
| Conversation memory | ⚠️ Explicit | Key on `conversation.id` — see section 4 above |
| File attachments | ⚠️ Manual | SDK passes attachment URLs; your agent handles download |
| Copilot Studio topics/dialogs | ❌ Bypassed | Intentional — LangChain handles all orchestration |

---

## Security Considerations

- **App Password (client secret)** — store exclusively in environment variables; never commit to source control
- All shell commands and tool executions run on **your server** inside the genai-tk sandbox — Microsoft Copilot Studio never has access to the execution environment
- Request authentication is validated automatically by `CloudAdapter.process()` using Azure Bot Service tokens
- Use HTTPS for the `/api/messages` endpoint — Azure Bot Service requires it in production

---

## SDK Status (as of mid-2026)

| Package | Status | Notes |
|---|---|---|
| `microsoft-agents-hosting-aiohttp` | Preview | Part of the M365 Agents SDK; actively developed |
| `microsoft-agents-bot-builder` | Preview | Activity handler abstractions |
| `botbuilder-python` | Stable / maintenance | Older SDK; still works but not the recommended path for new M365 projects |

Track the official SDK at [github.com/microsoft/agents-sdk-python](https://github.com/microsoft/agents-sdk-python) for API changes before going to production.

---

## Local Development Checklist

```bash
# 1. Start the M365 agent endpoint
uv run python -m aiohttp.web genai_blueprint.main.m365_app:app --port 8000

# 2. Tunnel to localhost (Azure Bot Service requires a public HTTPS URL)
ngrok http 8000

# 3. Set Azure Bot messaging endpoint to the ngrok HTTPS URL
# 4. Use Bot Framework Emulator for offline local testing (bypasses auth)
```

---

## References

- [Microsoft 365 Agents SDK for Python](https://github.com/microsoft/agents-sdk-python)
- [Microsoft Copilot Studio documentation](https://learn.microsoft.com/en-us/microsoft-copilot-studio/)
- [Azure Bot Service — Connect to channels](https://learn.microsoft.com/en-us/azure/bot-service/bot-service-manage-channels)
- [Copilot Studio — Use Azure Bot Service bots](https://learn.microsoft.com/en-us/microsoft-copilot-studio/publication-connect-bot-to-azure-bot-service-channels)
- [genai-tk agents documentation](../../genai-tk/docs/agents.md)
- [genai-blueprint FastAPI app](../genai_blueprint/main/fastapi_app.py)
