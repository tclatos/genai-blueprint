"""Streamlit page for Deer-flow Agent demo.

Provides an interactive interface to run Deer-flow agents with configurable profiles and modes.
Uses a two-column layout (execution trace left, conversation right) with streaming output.

Deer-flow agents offer advanced capabilities over the basic ReAct agent:
- Subagent orchestration (parallel task delegation)
- Sandbox code execution (local or Docker)
- Skills system (loadable workflows from directories)
- Conversation summarization and memory
- File operations (read/write/replace)
- Multiple modes: flash (fast), thinking (reasoning), pro (planning), ultra (all features)

The agent is a standard LangGraph CompiledStateGraph, using the same streaming
pattern as reAct_agent.py but with full middleware support when running in web context.
"""

import asyncio
import uuid
from typing import Any, cast

import streamlit as st
from dotenv import load_dotenv
from genai_tk.core.llm_factory import get_llm
from genai_tk.extra.agents.deer_flow.config_thread_data_middleware import ConfigThreadDataMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger
from streamlit import session_state as sss
from streamlit.delta_generator import DeltaGenerator

from genai_blueprint.webapp.ui_components.config_editor import edit_config_dialog
from genai_blueprint.webapp.ui_components.llm_selector import llm_selector_widget
from genai_blueprint.webapp.ui_components.message_renderer import render_message_with_mermaid
from genai_blueprint.webapp.ui_components.trace_middleware import (
    TraceMiddleware,
    display_interleaved_traces,
)

load_dotenv()

CONFIG_FILE = "config/agents/deerflow.yaml"
PAGE_TITLE = "🦌 Deer-flow Agent"
HEIGHT = 700

# Available deer-flow modes
DEER_FLOW_MODES = {
    "flash": "⚡ Flash - Fast responses, minimal overhead",
    "thinking": "🧠 Thinking - Reasoning enabled, structured analysis",
    "pro": "🎯 Pro - Planning + thinking, complex tasks",
    "ultra": "🚀 Ultra - All features enabled, maximum capability",
}


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
    if "df_agent_mode" not in sss:
        sss.df_agent_mode = "pro"  # Default mode
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
    if "df_show_help" not in sss:
        sss.df_show_help = False
    if "df_show_info" not in sss:
        sss.df_show_info = False
    if "df_thread_data_mw" not in sss:
        sss.df_thread_data_mw = ConfigThreadDataMiddleware()
    if "df_example_input" not in sss:
        sss.df_example_input = None


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
        from genai_tk.extra.agents.deer_flow.agent import DeerFlowError, load_deer_flow_profiles

        profiles = load_deer_flow_profiles(CONFIG_FILE)
        return [
            {
                "name": p.name,
                "description": p.description,
                "mode": p.mode,  # Include mode from profile
                "tool_groups": p.tool_groups,
                "subagent_enabled": p.subagent_enabled,
                "thinking_enabled": p.thinking_enabled,
                "is_plan_mode": p.is_plan_mode,
                "mcp_servers": p.mcp_servers,
                "tool_configs": p.tool_configs,
                "system_prompt": p.system_prompt,
                "examples": p.examples,
                "skills": p.skills,
                "skill_directories": p.skill_directories,
            }
            for p in profiles
        ]
    except (DeerFlowError, FileNotFoundError, ValueError) as e:
        logger.error(f"Failed to load profiles: {e}")
        st.error(f"❌ Error loading Deer-flow profiles: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error loading profiles: {e}")
        st.error(f"❌ Unexpected error: {e}")
        return []


def get_profile_by_name(profiles: list[dict], name: str) -> dict[str, Any] | None:
    """Find a profile dict by name."""
    return next((p for p in profiles if p["name"] == name), None)


# ============================================================================
# Agent Creation
# ============================================================================


def create_agent_for_profile(profile_dict: dict[str, Any], mode_override: str | None = None) -> Any:
    """Create a Deer-flow agent for the given profile.

    Uses the simplified creation path that takes GenAI Toolkit's LLM directly.
    In web UI context, uses interactive_mode=True for full middleware support.

    Args:
        profile_dict: Profile configuration dictionary
        mode_override: Optional mode override (flash, thinking, pro, ultra)

    Raises:
        DeerFlowError: If profile configuration is invalid (e.g., invalid MCP servers)
        Exception: If agent creation fails for other reasons
    """
    from genai_tk.extra.agents.deer_flow.agent import (
        DeerFlowAgentConfig,
        create_deer_flow_agent_simple,
        validate_mcp_servers,
    )

    # Validate MCP servers if specified
    mcp_servers = profile_dict.get("mcp_servers", [])
    if mcp_servers:
        try:
            validated_mcp = validate_mcp_servers(mcp_servers)
            profile_dict["mcp_servers"] = validated_mcp
        except Exception as e:
            # Re-raise with more context
            raise ValueError(f"Invalid MCP servers in profile '{profile_dict['name']}': {e}") from e

    # Apply mode override if provided
    agent_mode = mode_override or profile_dict.get("mode", "pro")

    profile = DeerFlowAgentConfig(
        name=profile_dict["name"],
        description=profile_dict.get("description", ""),
        mode=agent_mode,  # Use selected mode
        tool_groups=profile_dict.get("tool_groups", ["web"]),
        subagent_enabled=profile_dict.get("subagent_enabled", False),
        thinking_enabled=profile_dict.get("thinking_enabled", True),
        is_plan_mode=profile_dict.get("is_plan_mode", False),
        mcp_servers=profile_dict.get("mcp_servers", []),
        tool_configs=profile_dict.get("tool_configs", []),
        system_prompt=profile_dict.get("system_prompt"),
        examples=profile_dict.get("examples", []),
        skills=profile_dict.get("skills", []),
        skill_directories=profile_dict.get("skill_directories", []),
    )

    llm = get_llm()
    checkpointer = get_cached_checkpointer()
    trace_mw = sss.df_trace_middleware
    thread_data_mw = sss.df_thread_data_mw

    # Use interactive_mode=True since we're in a web UI context with more capabilities
    # This enables ClarificationMiddleware and ThreadDataMiddleware
    agent = create_deer_flow_agent_simple(
        profile=profile,
        llm=llm,
        checkpointer=checkpointer,
        trace_middleware=trace_mw,
        thread_data_middleware=thread_data_mw,  # Enable file I/O for Python skills
        interactive_mode=True,  # Web UI has more context than CLI
    )

    return agent


# ============================================================================
# UI Components
# ============================================================================


def display_sidebar(profiles: list[dict[str, Any]]) -> tuple[str | None, str]:
    """Render sidebar with LLM selector, profile picker, mode selector, and info.

    Returns:
        Tuple of (selected_profile_name, selected_mode)
    """
    with st.sidebar:
        llm_selector_widget(st.sidebar)

        if st.button(":material/edit: Edit Config", help="Edit Deer-flow profile configuration"):
            edit_config_dialog(CONFIG_FILE)

        st.divider()

        if not profiles:
            st.error("No Deer-flow profiles found. Check config/agents/deerflow.yaml")
            return None, "pro"

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

        # Mode selector
        profile = get_profile_by_name(profiles, selected)
        if profile:
            default_mode = profile.get("mode", "pro")
            # Find index of default mode, defaulting to "pro" if not found
            mode_keys = list(DEER_FLOW_MODES.keys())
            try:
                mode_index = (
                    mode_keys.index(sss.df_agent_mode)
                    if sss.df_agent_mode in mode_keys
                    else mode_keys.index(default_mode)
                )
            except ValueError:
                mode_index = mode_keys.index("pro")  # Fallback to pro

            selected_mode = st.selectbox(
                "⚙️ Agent Mode:",
                options=list(DEER_FLOW_MODES.keys()),
                format_func=lambda x: DEER_FLOW_MODES[x],
                index=mode_index,
                key="df_mode_selector",
                help="Mode determines agent capabilities and behavior",
            )

            # Detect mode change
            if sss.df_agent_mode != selected_mode:
                sss.df_agent_mode = selected_mode
                # Recreate agent with new mode
                if sss.df_agent is not None:
                    sss.df_agent = None
                    st.info(f"Mode changed to {selected_mode}. Agent will be recreated.")

            # Show profile details
            if profile.get("description"):
                st.caption(profile["description"])

            # Feature badges
            features = []
            if selected_mode == "pro":
                features.append("🎯 Planning")
            if selected_mode == "ultra":
                features.append("🚀 All Features")
            if profile.get("thinking_enabled") or selected_mode in ["thinking", "pro", "ultra"]:
                features.append("🧠 Thinking")
            if profile.get("subagent_enabled"):
                features.append("🔀 Subagents")
            if "bash" in profile.get("tool_groups", []):
                features.append("💻 Sandbox")
            if any("file" in g for g in profile.get("tool_groups", [])):
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

            # Skills
            skill_count = len(profile.get("skills", []))
            skill_dirs = profile.get("skill_directories", [])
            if skill_count or skill_dirs:
                parts = []
                if skill_count:
                    parts.append(f"{skill_count} configured")
                if skill_dirs:
                    parts.append(f"loading from {len(skill_dirs)} directories")
                st.markdown(f"**Skills**: {', '.join(parts)}")

            # Extra tools
            if profile.get("tool_configs"):
                tool_names = []
                for tc in profile["tool_configs"]:
                    name = tc.get("factory", tc.get("class", tc.get("function", "unknown")))
                    tool_names.append(name.split(":")[-1] if ":" in name else name)
                st.markdown(f"**Extra tools**: {', '.join(tool_names)}")

            # Examples
            if profile.get("examples"):
                with st.expander("💡 Example Queries", expanded=False):
                    for example in profile["examples"]:
                        if st.button(example, key=f"example_{hash(example)}", use_container_width=True):
                            # Set the example as the next input
                            sss.df_example_input = example
                            st.rerun()

        st.divider()

        # Commands info
        with st.expander("📖 Commands", expanded=False):
            st.markdown(
                """
                **Available commands:**
                - `/help` - Show help information
                - `/info` - Display agent configuration
                - `/clear` - Clear conversation history
                - `/trace` - Open LangSmith traces
                """
            )

        # Workspace file browser
        if hasattr(sss, "df_thread_data_mw") and sss.df_thread_id:
            display_workspace_files()

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

    return selected, selected_mode


def display_workspace_files() -> None:
    """Display workspace files in sidebar with download buttons."""
    thread_data_mw = sss.df_thread_data_mw
    thread_id = sss.df_thread_id

    files = thread_data_mw.list_workspace_files(thread_id)

    if not files:
        with st.expander("📁 Workspace Files", expanded=False):
            st.caption("No files generated yet. Generate files with skills like ppt-generation.")
        return

    with st.expander(f"📁 Workspace Files ({len(files)})", expanded=True):
        for file_info in files[:10]:  # Show max 10 most recent
            file_path = file_info["path"]
            file_name = file_info["name"]
            file_size = file_info["size"]

            # Format file size
            if file_size < 1024:
                size_str = f"{file_size}B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.1f}KB"
            else:
                size_str = f"{file_size / (1024 * 1024):.1f}MB"

            # File info with download button
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{file_name}**")
                st.caption(f"{size_str} · {file_info['relative_path']}")
            with col2:
                try:
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label="⬇️",
                            data=f,
                            file_name=file_name,
                            key=f"download_{hash(file_path)}",
                            use_container_width=True,
                        )
                except Exception as e:
                    st.caption(f"❌ {e}")

        if len(files) > 10:
            st.caption(f"Showing 10 of {len(files)} files (most recent)")

        # Workspace path info
        workspace_path = thread_data_mw.get_workspace_dir(thread_id)
        st.caption(f"📂 {workspace_path}")


def display_deer_flow_status() -> None:
    """Show Deer-flow availability status."""
    try:
        from genai_tk.extra.agents.deer_flow._path_setup import get_deer_flow_backend_path

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
                with st.chat_message("ai"):
                    render_message_with_mermaid(final_response.content, st)
        elif response_content:
            ai_msg = AIMessage(content=response_content)
            sss.df_messages.append(ai_msg)
            with chat_container:
                with st.chat_message("ai"):
                    render_message_with_mermaid(response_content, st)
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

    # Sidebar: profile selection and mode
    result = display_sidebar(profiles)
    if result[0] is None:
        st.stop()

    selected_name, selected_mode = result
    sss.df_agent_profile = selected_name
    sss.df_agent_mode = selected_mode

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
                    with st.chat_message("ai"):
                        render_message_with_mermaid(msg.content, st)

    # Status container (between columns and input)
    status_container = st.container()

    # Display errors
    if sss.df_error:
        st.error(sss.df_error)
        if st.button("Clear Error"):
            sss.df_error = None
            st.rerun()

    # Display help if requested
    if sss.df_show_help:
        st.info(
            """
**🦌 Deer-flow Agent Help**

**Commands:**
- `/help` - Show this help message
- `/info` - Display current agent configuration 
- `/clear` - Clear conversation history and start fresh
- `/trace` - Open LangSmith for detailed execution traces

**Tips:**
- Use the sidebar to switch profiles and select modes
- Click example queries in the sidebar to try them
- Use mode selector to balance speed vs. capability
- Check execution traces to understand agent reasoning
            """,
            icon="📖",
        )
        sss.df_show_help = False

    # Agent info display
    if hasattr(sss, "df_show_info") and sss.df_show_info:
        with st.container(border=True):
            st.markdown("### 🦌 Current Agent Configuration")
            st.markdown(f"**Profile:** {selected_name}")
            st.markdown(f"**Mode:** {selected_mode} - {DEER_FLOW_MODES[selected_mode]}")
            if profile.get("mcp_servers"):
                st.markdown(f"**MCP Servers:** {', '.join(profile['mcp_servers'])}")
            if profile.get("tool_groups"):
                st.markdown(f"**Tool Groups:** {', '.join(profile['tool_groups'])}")
            st.markdown(f"**Thread ID:** `{sss.df_thread_id}`")
        sss.df_show_info = False

    # Handle example input from sidebar or chat input widget
    # Always show chat input widget. If an example is selected, show it as a suggestion above the input.
    chat_placeholder = "Type your message or a command (/help, /info, /clear)..."
    if hasattr(sss, "df_example_input"):
        st.info(f"💡 Example: {sss.df_example_input}")
        del sss.df_example_input
    user_input = st.chat_input(
        chat_placeholder,
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
                sss.df_show_help = True
                st.rerun()
            elif user_input == "/info":
                sss.df_show_info = True
                st.rerun()
            elif user_input == "/trace":
                st.link_button(
                    "📊 Open LangSmith",
                    "https://smith.langchain.com/",
                )
                return
            else:
                st.warning(f"Unknown command: {user_input}. Try /help for available commands.")
            return

        # Create agent if needed (or if mode changed)
        if sss.df_agent is None:
            with st.spinner(f"🦌 Setting up Deer-flow agent ({selected_mode} mode)..."):
                try:
                    agent = create_agent_for_profile(profile, mode_override=selected_mode)
                    sss.df_agent = agent
                    logger.info(f"Created Deer-flow agent with profile '{selected_name}' in mode '{selected_mode}'")
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
