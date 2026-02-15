"""Streamlit page for Deer-flow Agent demo.

Provides an interactive interface to run Deer-flow agents with configurable profiles.
Uses a two-column layout (execution trace left, conversation right) with streaming output.

Deer-flow agents offer advanced capabilities over the basic ReAct agent:
- Subagent orchestration (parallel task delegation)
- Sandbox code execution (local or Docker)
- Skills system (loadable workflows)
- Conversation summarization and memory
- File operations (read/write/replace)

The agent is a standard LangGraph CompiledStateGraph, using the same streaming
pattern as reAct_agent.py.
"""

import asyncio
import uuid
from typing import Any, cast

import streamlit as st
from dotenv import load_dotenv
from genai_tk.core.llm_factory import get_llm
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger
from streamlit import session_state as sss
from streamlit.delta_generator import DeltaGenerator

from genai_blueprint.webapp.ui_components.config_editor import edit_config_dialog
from genai_blueprint.webapp.ui_components.llm_selector import llm_selector_widget
from genai_blueprint.webapp.ui_components.trace_middleware import (
    TraceMiddleware,
    display_interleaved_traces,
)

load_dotenv()

CONFIG_FILE = "config/agents/deerflow.yaml"
PAGE_TITLE = "🦌 Deer-flow Agent"
HEIGHT = 700


# ============================================================================
# Session State
# ============================================================================


def initialize_session_state() -> None:
    """Initialize session state variables."""
    if "df_messages" not in sss:
        sss.df_messages = [AIMessage(content="Hello! I'm a Deer-flow agent. How can I help you today?")]
    if "df_agent" not in sss:
        sss.df_agent = None
    if "df_agent_profile" not in sss:
        sss.df_agent_profile = None
    if "df_just_processed" not in sss:
        sss.df_just_processed = False
    if "df_trace_middleware" not in sss:
        sss.df_trace_middleware = TraceMiddleware()
    if "df_thread_id" not in sss:
        sss.df_thread_id = str(uuid.uuid4())
    if "df_agent_running" not in sss:
        sss.df_agent_running = False
    if "df_error" not in sss:
        sss.df_error = None
    if "df_setup_done" not in sss:
        sss.df_setup_done = False


def clear_chat() -> None:
    """Reset chat history while preserving traces."""
    sss.df_messages = [AIMessage(content="Hello! I'm a Deer-flow agent. How can I help you today?")]
    sss.df_thread_id = str(uuid.uuid4())


def clear_all() -> None:
    """Reset everything."""
    clear_chat()
    sss.df_trace_middleware = TraceMiddleware()
    sss.df_agent = None
    sss.df_agent_profile = None
    sss.df_setup_done = False


@st.cache_resource
def get_cached_checkpointer() -> MemorySaver:
    """Cached checkpointer shared across agent recreations."""
    return MemorySaver()


# ============================================================================
# Profile Loading
# ============================================================================


@st.cache_data(ttl=60)
def load_profiles() -> list[dict[str, Any]]:
    """Load Deer-flow profiles from YAML config (cached 60s)."""
    try:
        from genai_blueprint.deer_flow.agent import load_deer_flow_profiles

        profiles = load_deer_flow_profiles(CONFIG_FILE)
        return [
            {
                "name": p.name,
                "description": p.description,
                "tool_groups": p.tool_groups,
                "subagent_enabled": p.subagent_enabled,
                "thinking_enabled": p.thinking_enabled,
                "mcp_servers": p.mcp_servers,
                "tool_configs": p.tool_configs,
                "system_prompt": p.system_prompt,
                "examples": p.examples,
            }
            for p in profiles
        ]
    except Exception as e:
        logger.error(f"Failed to load profiles: {e}")
        return []


def get_profile_by_name(profiles: list[dict], name: str) -> dict[str, Any] | None:
    """Find a profile dict by name."""
    return next((p for p in profiles if p["name"] == name), None)


# ============================================================================
# Agent Creation
# ============================================================================


def create_agent_for_profile(profile_dict: dict[str, Any]) -> Any:
    """Create a Deer-flow agent for the given profile.

    Uses the simplified creation path that takes GenAI Blueprint's LLM directly.
    """
    from genai_blueprint.deer_flow.agent import DeerFlowAgentConfig, create_deer_flow_agent_simple

    profile = DeerFlowAgentConfig(
        name=profile_dict["name"],
        description=profile_dict.get("description", ""),
        tool_groups=profile_dict.get("tool_groups", ["web"]),
        subagent_enabled=profile_dict.get("subagent_enabled", False),
        thinking_enabled=profile_dict.get("thinking_enabled", True),
        mcp_servers=profile_dict.get("mcp_servers", []),
        tool_configs=profile_dict.get("tool_configs", []),
        system_prompt=profile_dict.get("system_prompt"),
        examples=profile_dict.get("examples", []),
    )

    llm = get_llm()
    checkpointer = get_cached_checkpointer()
    trace_mw = sss.df_trace_middleware

    agent = create_deer_flow_agent_simple(
        profile=profile,
        llm=llm,
        checkpointer=checkpointer,
        trace_middleware=trace_mw,
    )

    return agent


# ============================================================================
# UI Components
# ============================================================================


def display_sidebar(profiles: list[dict[str, Any]]) -> str | None:
    """Render sidebar with LLM selector, profile picker, and info."""
    with st.sidebar:
        llm_selector_widget(st.sidebar)

        if st.button(":material/edit: Edit Config", help="Edit Deer-flow profile configuration"):
            edit_config_dialog(CONFIG_FILE)

        st.divider()

        if not profiles:
            st.error("No Deer-flow profiles found. Check config/agents/deerflow.yaml")
            return None

        # Profile selector
        current_index = 0
        if sss.df_agent_profile:
            names = [p["name"] for p in profiles]
            if sss.df_agent_profile in names:
                current_index = names.index(sss.df_agent_profile)

        selected = st.selectbox(
            "🦌 Deer-flow Profile:",
            options=[p["name"] for p in profiles],
            index=current_index,
            key="df_profile_selector",
        )

        # Detect profile change
        if sss.df_agent_profile and sss.df_agent_profile != selected:
            clear_chat()
            sss.df_agent = None
            sss.df_setup_done = False

        # Show profile details
        profile = get_profile_by_name(profiles, selected)
        if profile:
            if profile.get("description"):
                st.caption(profile["description"])

            # Feature badges
            features = []
            if profile.get("subagent_enabled"):
                features.append("🔀 Subagents")
            if profile.get("thinking_enabled"):
                features.append("🧠 Thinking")
            if "bash" in profile.get("tool_groups", []):
                features.append("💻 Sandbox")
            if "file:write" in profile.get("tool_groups", []):
                features.append("📝 File I/O")
            if features:
                st.markdown(" · ".join(features))

            # Tool groups
            if profile.get("tool_groups"):
                groups = ", ".join(f"`{g}`" for g in profile["tool_groups"])
                st.markdown(f"**Tool groups**: {groups}")

            # MCP servers
            if profile.get("mcp_servers"):
                mcp_list = ", ".join(f"`{m}`" for m in profile["mcp_servers"])
                st.markdown(f"**MCP**: {mcp_list}")

            # Extra tools
            if profile.get("tool_configs"):
                tool_names = []
                for tc in profile["tool_configs"]:
                    name = tc.get("factory", tc.get("class", tc.get("function", "unknown")))
                    tool_names.append(name.split(":")[-1] if ":" in name else name)
                st.markdown(f"**Extra tools**: {', '.join(tool_names)}")

            # Examples
            if profile.get("examples"):
                with st.container(border=True):
                    st.markdown(
                        "**Examples:**",
                        help="Copy an example and paste it into the chat input",
                    )
                    for example in profile["examples"]:
                        st.code(example, language="text", wrap_lines=True)

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗑️ Chat", help="Clear chat history"):
                clear_chat()
                st.rerun()
        with col2:
            if st.button("🗑️ All", help="Clear chat and traces"):
                clear_all()
                st.rerun()

        # Deer-flow info
        st.divider()
        st.caption("Powered by [Deer-flow](https://github.com/bytedance/deer-flow)")

    return selected


def display_deer_flow_status() -> None:
    """Show Deer-flow availability status."""
    try:
        from genai_blueprint.deer_flow._path_setup import get_deer_flow_backend_path

        path = get_deer_flow_backend_path()
        st.success(f"Deer-flow backend: `{path}`", icon="🦌")
        sss.df_setup_done = True
    except FileNotFoundError:
        st.error(
            "🦌 Deer-flow backend not found.\n\n"
            "**Install with:**\n"
            "```bash\n"
            "make deer-flow-install\n"
            "```\n"
            "Or set `DEER_FLOW_PATH` environment variable.",
            icon="⚠️",
        )
        st.stop()


# ============================================================================
# Agent Execution (Async Streaming)
# ============================================================================


async def run_agent_streaming(
    agent: Any,
    user_input: str,
    trace_container: DeltaGenerator,
    chat_container: DeltaGenerator,
    status_container: DeltaGenerator,
) -> None:
    """Run the agent with streaming output, updating UI in real-time.

    Args:
        agent: CompiledStateGraph from deer-flow
        user_input: The user's query
        trace_container: Left-column container for execution traces
        chat_container: Right-column container for chat messages
        status_container: Container for status updates
    """
    sss.df_messages.append(HumanMessage(content=user_input))
    with chat_container:
        st.chat_message("human").write(user_input)

    config = cast(RunnableConfig, {"configurable": {"thread_id": sss.df_thread_id}})

    try:
        with status_container.status("🦌 Agent is thinking...", expanded=True) as status:
            status.write("Processing your request...")

            inputs = {"messages": [HumanMessage(content=user_input)]}
            response_content = ""
            final_response = None

            async for step in agent.astream(inputs, config):
                # Handle tuple steps
                if isinstance(step, tuple):
                    step = step[1]

                if isinstance(step, dict):
                    for node, update in step.items():
                        status.write(f"Node: `{node}`")

                        # Update traces in real-time
                        if "df_trace_middleware" in sss:
                            with trace_container:
                                display_interleaved_traces(sss.df_trace_middleware, key_prefix="df_streaming")

                        if "messages" in update and update["messages"]:
                            latest = update["messages"][-1]
                            if isinstance(latest, AIMessage) and latest.content:
                                response_content = latest.content
                                final_response = latest

                                # Record in trace middleware
                                trace_mw = sss.get("df_trace_middleware")
                                if trace_mw:
                                    trace_mw.add_llm_call(
                                        node=node,
                                        content=str(latest.content),
                                    )

                                status.write(f"Response: {len(response_content)} chars")

            status.update(label="✅ Complete!", state="complete", expanded=False)

        # Add response to chat
        if final_response and final_response.content:
            sss.df_messages.append(final_response)
            with chat_container:
                st.chat_message("ai").write(final_response.content)
        elif response_content:
            ai_msg = AIMessage(content=response_content)
            sss.df_messages.append(ai_msg)
            with chat_container:
                st.chat_message("ai").write(response_content)
        else:
            error_msg = "I couldn't generate a response. Please try again."
            sss.df_messages.append(AIMessage(content=error_msg))
            with chat_container:
                st.chat_message("ai").write(error_msg)

        sss.df_just_processed = True
        st.rerun()

    except Exception as e:
        import traceback

        error_msg = f"Agent error: {e}"
        logger.error(error_msg)
        status_container.error(error_msg)
        with st.expander("🐛 Full Traceback"):
            st.code(traceback.format_exc(), language="python")
        sss.df_messages.append(AIMessage(content=f"Error: {e}"))
        sss.df_just_processed = True


# ============================================================================
# Main Page
# ============================================================================


async def main() -> None:
    """Main async function for the Deer-flow agent page."""
    initialize_session_state()

    # Load profiles
    profiles = load_profiles()

    # Title
    st.title(PAGE_TITLE)

    # Sidebar: profile selection
    selected_name = display_sidebar(profiles)
    if not selected_name:
        st.stop()

    sss.df_agent_profile = selected_name
    profile = get_profile_by_name(profiles, selected_name)
    if not profile:
        st.error(f"Profile '{selected_name}' not found")
        st.stop()

    # Check deer-flow availability (once)
    if not sss.df_setup_done:
        with st.spinner("Checking Deer-flow setup..."):
            display_deer_flow_status()

    # Clear just_processed flag
    if sss.df_just_processed:
        sss.df_just_processed = False

    # Two-column layout: Traces (left) | Chat (right)
    col_trace, col_chat = st.columns([1, 1], gap="medium")

    with col_trace:
        st.subheader("🔍 Execution Trace")
        trace_container = st.container(height=HEIGHT, border=True)
        with trace_container:
            if "df_trace_middleware" in sss:
                mw = sss.df_trace_middleware
                if mw.tool_calls or getattr(mw, "llm_calls", []):
                    display_interleaved_traces(mw, key_prefix="df_main")
                else:
                    st.info("Send a message to see agent execution traces")
            else:
                st.info("Send a message to see agent execution traces")

    with col_chat:
        st.subheader("💬 Conversation")
        chat_container = st.container(height=HEIGHT, border=True)
        with chat_container:
            for msg in sss.df_messages:
                if isinstance(msg, HumanMessage):
                    st.chat_message("human").write(msg.content)
                elif isinstance(msg, AIMessage):
                    st.chat_message("ai").write(msg.content)

    # Status container (between columns and input)
    status_container = st.container()

    # Display errors
    if sss.df_error:
        st.error(sss.df_error)
        if st.button("Clear Error"):
            sss.df_error = None
            st.rerun()

    # Chat input
    user_input = st.chat_input(
        "Type your message... (try an example from the sidebar)",
        key="df_chat_input",
    )

    # LangSmith link
    st.link_button(
        "📊 View Traces in LangSmith",
        "https://smith.langchain.com/",
        help="View detailed execution traces",
    )

    # Handle user input
    if user_input and not sss.df_just_processed:
        user_input = user_input.strip()
        if not user_input:
            return

        # Handle commands
        if user_input.startswith("/"):
            if user_input in ("/clear", "/reset"):
                clear_all()
                st.rerun()
            elif user_input == "/help":
                st.info(
                    "**Commands:** `/clear` - reset all, `/help` - this message\n\n"
                    "**Tips:** Use sidebar to switch profiles and find examples."
                )
            else:
                st.warning(f"Unknown command: {user_input}")
            return

        # Create agent if needed
        if sss.df_agent is None:
            with st.spinner("🦌 Setting up Deer-flow agent..."):
                try:
                    agent = create_agent_for_profile(profile)
                    sss.df_agent = agent
                except Exception as e:
                    import traceback

                    error = f"Failed to create agent: {e}"
                    st.error(error)
                    with st.expander("🐛 Traceback"):
                        st.code(traceback.format_exc(), language="python")
                    sss.df_error = error
                    return

        # Run agent
        await run_agent_streaming(
            agent=sss.df_agent,
            user_input=user_input,
            trace_container=trace_container,
            chat_container=chat_container,
            status_container=status_container,
        )


# ============================================================================
# Entry Point
# ============================================================================

try:
    _ = st.session_state  # Verify Streamlit context
    asyncio.run(main())
except (AttributeError, RuntimeError):
    pass  # Not running in Streamlit context (e.g., being imported)
