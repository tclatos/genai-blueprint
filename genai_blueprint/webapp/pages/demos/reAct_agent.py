"""Streamlit page for ReAct Agent demo.

Provides an interactive chat interface to run ReAct agents with different configurations.
Supports custom tools, MCP servers integration, demo presets, and command handling.
Features a two-column layout with tool calls tracking and conversation display.
Example prompts are displayed for easy copy/paste into the chat input.

"""

import asyncio
import uuid
from pathlib import Path
from typing import Any, cast

import streamlit as st
from dotenv import load_dotenv
from genai_tk.agents.langchain.config import AgentProfileConfig, load_unified_config
from genai_tk.core.llm_factory import get_llm
from genai_tk.core.mcp_client import get_mcp_servers_dict
from genai_tk.core.prompts import dedent_ws
from genai_tk.tools.langchain.shared_config_loader import process_langchain_tools_from_config
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from streamlit import session_state as sss
from streamlit.delta_generator import DeltaGenerator

from genai_blueprint.webapp.ui_components.agent_layout import (
    PANEL_HEIGHT,
    render_agent_sidebar,
    render_sidebar_demo_section,
)
from genai_blueprint.webapp.ui_components.message_renderer import render_message_with_mermaid
from genai_blueprint.webapp.ui_components.trace_middleware import (
    TraceMiddleware,
    display_interleaved_traces,
)

load_dotenv()


CONFIG_FILE = "config/agents/langchain.yaml"
assert Path(CONFIG_FILE).exists(), f"Cannot load {CONFIG_FILE}"

# Default system prompt
SYSTEM_PROMPT = dedent_ws(
    """
    Your are a helpful assistant. Use provided tools to answer questions. \n
    - If the user asks for a list of something and that the tool returns a list, print it as Markdown table. 
"""
)


def initialize_session_state() -> None:
    """Initialize session state variables."""
    if "messages" not in sss:
        sss.messages = [AIMessage(content="Hello! I'm your ReAct agent. How can I help you today?")]
    if "agent" not in sss:
        sss.agent = None
    if "agent_config" not in sss:
        sss.agent_config = None
    if "current_demo" not in sss:
        sss.current_demo = None
    if "just_processed" not in sss:
        sss.just_processed = False
    if "trace_middleware" not in sss:
        sss.trace_middleware = TraceMiddleware()


def clear_chat_history(keep_traces: bool = False) -> None:
    """Reset the chat history and related state.

    Args:
        keep_traces: If True, preserve execution traces while clearing chat messages
    """
    if "messages" in sss:
        sss.messages = [AIMessage(content="Hello! I'm your ReAct agent. How can I help you today?")]

    # Only clear traces if not preserving them
    if not keep_traces and "trace_middleware" in sss:
        sss.trace_middleware.clear()
    # Don't clear agent/config - let them persist to avoid recreation


def clear_all_history() -> None:
    """Reset both chat and execution trace history."""
    clear_chat_history(keep_traces=False)


def _react_demo_info(demo: AgentProfileConfig) -> None:
    """Render per-demo metadata (tools, MCP) inside the page header."""
    parts = []
    if demo.tools:
        tool_names = [
            getattr(t, "tool_class", None) or getattr(t, "function", None) or getattr(t, "factory", "?")
            for t in demo.tools
        ]
        parts.append("**Tools:** " + ", ".join(f"`{n}`" for n in tool_names))
    if demo.mcp_servers:
        parts.append("**MCP:** " + ", ".join(f"`{m}`" for m in demo.mcp_servers))
    if parts:
        st.markdown("  \n".join(parts))


@st.cache_resource()
def get_cached_checkpointer():
    """Get a cached checkpointer to avoid recreating it."""
    return MemorySaver()


def get_or_create_agent(demo: AgentProfileConfig) -> tuple[Any, RunnableConfig, BaseCheckpointSaver]:
    """Get or create agent for the current demo configuration.

    Returns:
        Tuple of (agent, config, checkpointer)
    """
    # Check if we need to create a new agent
    if sss.agent is None or sss.agent_config is None:
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        checkpointer = get_cached_checkpointer()

        # This will be set up later in the async function
        sss.agent_config = config
        sss.current_demo = demo.name

        return None, cast(RunnableConfig, config), checkpointer

    # If demo changed, we need to recreate the agent
    if sss.current_demo != demo.name:
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        checkpointer = get_cached_checkpointer()

        # Update demo name and config
        sss.agent_config = config
        sss.current_demo = demo.name

        # Force agent recreation while preserving traces
        return None, cast(RunnableConfig, config), checkpointer

    return sss.agent, sss.agent_config, get_cached_checkpointer()


def handle_command(command: str) -> bool:
    """Handle special commands like /trace, /help, etc.

    Returns:
        True if command was handled, False otherwise
    """
    command = command.strip().lower()

    if command in ["/quit", "/exit", "/q"]:
        st.info("👋 To quit, simply close this browser tab or navigate away.")
        return True

    elif command == "/help":
        st.info("""
        **Available Commands:**
        - `/help` - Show this help message
        - `/trace` - Open last LangSmith trace in browser (if available)
        - `/clear` - Clear chat history
        - `/quit` - Instructions to quit
        
        **Tips:**
        - Type normally to chat with the agent
        - Use the sidebar to change demo configurations
        - Tool calls will appear in the left column
        """)
        return True

    elif command == "/trace":
        st.info("Opening LangSmith traces...")
        st.link_button("🔗 Open Traces", "https://smith.langchain.com/")
        return True

    elif command == "/clear":
        clear_chat_history()
        st.success("Chat history cleared!")
        st.rerun()
        return True

    elif command.startswith("/"):
        st.error(f"Unknown command: {command}. Type `/help` for available commands.")
        return True

    return False


async def setup_agent_if_needed(demo: AgentProfileConfig) -> Any:
    """Set up the agent if it doesn't exist or configuration changed."""
    agent, config, checkpointer = get_or_create_agent(demo)

    if agent is None:
        with st.spinner("Setting up agent..."):
            llm = get_llm()

            # Get MCP servers from selected demo
            mcp_servers_params = get_mcp_servers_dict(demo.mcp_servers) if demo.mcp_servers else {}
            all_tools = process_langchain_tools_from_config(demo.tools)

            if mcp_servers_params:
                try:
                    client = MultiServerMCPClient(mcp_servers_params)
                    mcp_tools = await client.get_tools()
                    all_tools.extend(mcp_tools)
                except Exception as e:
                    st.error(f"Failed to connect to MCP servers: {e}")

            # Create agent with demo's system prompt or default
            system_prompt = demo.system_prompt or SYSTEM_PROMPT

            # Store the current middleware to preserve traces
            current_middleware = sss.get("trace_middleware", None)
            if current_middleware is None:
                current_middleware = TraceMiddleware()
                sss.trace_middleware = current_middleware

            # Use custom trace middleware for detailed execution display
            middleware = [current_middleware]

            agent = create_agent(
                model=llm,
                tools=all_tools,
                system_prompt=system_prompt,
                checkpointer=checkpointer,
                middleware=middleware,
            )

            # Cache the agent
            sss.agent = agent

    return sss.agent


async def process_user_input(
    demo: AgentProfileConfig,
    user_input: str,
    status_container: DeltaGenerator,
    chat_container: DeltaGenerator | None = None,
    trace_container: DeltaGenerator | None = None,
) -> None:
    """Process user input and generate agent response.

    Args:
        demo: The demo configuration to use
        user_input: The user's input message
        status_container: Container for displaying agent execution status
        chat_container: Container for displaying chat messages
        trace_container: Container for updating tool traces during execution
    """
    # Add user message to chat
    sss.messages.append(HumanMessage(content=user_input))

    # Display user message immediately if chat container is provided
    if chat_container:
        with chat_container:
            st.chat_message("human").write(user_input)

    # Set up agent
    agent = await setup_agent_if_needed(demo)

    # Get current config
    _, config, _ = get_or_create_agent(demo)

    try:
        with status_container.status("Agent is thinking...", expanded=True) as status:
            status.write("Processing your request...")

            # Prepare inputs
            inputs = {"messages": [HumanMessage(content=user_input)]}

            response_content = ""
            final_response = None

            # Stream the response
            astream = agent.astream(inputs, config)
            async for step in astream:
                status.write(f"Processing step: {type(step).__name__}")

                # Update traces in real-time if container provided
                if trace_container and "trace_middleware" in sss:
                    with trace_container:
                        display_interleaved_traces(sss.trace_middleware, key_prefix="streaming")

                # Handle different step formats
                if isinstance(step, tuple):
                    step = step[1]

                # Process each node in the step
                if isinstance(step, dict):
                    for node, update in step.items():
                        status.write(f"Node: {node}")

                        if "messages" in update and update["messages"]:
                            latest_message = update["messages"][-1]

                            if isinstance(latest_message, AIMessage):
                                if latest_message.content:
                                    response_content = latest_message.content
                                    final_response = latest_message

                                    # Record this LLM output in the shared trace middleware
                                    trace_middleware = sss.get("trace_middleware")
                                    if trace_middleware is not None:
                                        trace_middleware.add_llm_call(
                                            node=node,
                                            content=str(latest_message.content),
                                        )

                                    status.write(f"Got AI response: {len(response_content)} chars")

            status.update(label="Complete!", state="complete", expanded=False)

        # Add the response to messages and display immediately
        if final_response and final_response.content:
            sss.messages.append(final_response)
            # Display AI response immediately if chat container is provided
            if chat_container:
                with chat_container:
                    with st.chat_message("ai"):
                        render_message_with_mermaid(final_response.content, st)
        elif response_content:
            ai_message = AIMessage(content=response_content)
            sss.messages.append(ai_message)
            # Display AI response immediately if chat container is provided
            if chat_container:
                with chat_container:
                    with st.chat_message("ai"):
                        render_message_with_mermaid(response_content, st)
        else:
            error_msg = "I apologize, but I couldn't generate a proper response."
            sss.messages.append(AIMessage(content=error_msg))
            # Display error message immediately if chat_container is provided
            if chat_container:
                with chat_container:
                    with st.chat_message("ai"):
                        render_message_with_mermaid(error_msg, st)

        # Mark that we just processed input to prevent re-execution
        sss.just_processed = True

        # Force a rerun to display the updated traces
        # The just_processed flag will prevent re-execution of the query
        st.rerun()

    except Exception as e:
        status_container.error(f"An error occurred: {str(e)}")
        sss.messages.append(AIMessage(content=f"I encountered an error: {str(e)}"))
        # Also set flag for error case to prevent re-execution
        sss.just_processed = True
        import traceback

        st.error(f"Full traceback: {traceback.format_exc()}")


async def main() -> None:
    """Main async function to run the ReAct agent demo."""
    initialize_session_state()

    sample_demos = load_unified_config(CONFIG_FILE).profiles
    if not sample_demos:
        st.error(f"No demo configurations found in {CONFIG_FILE}")
        st.stop()

    # ── Sidebar ───────────────────────────────────────────────────────────
    render_agent_sidebar(CONFIG_FILE)
    with st.sidebar:
        st.divider()
        demo = render_sidebar_demo_section(
            sample_demos,
            current_name=sss.current_demo,
            info_fn=_react_demo_info,
        )
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🗑️ Chat", help="Clear conversation"):
                clear_chat_history(keep_traces=True)
                st.rerun()
        with c2:
            if st.button("🗑️ All", help="Clear conversation + traces"):
                clear_all_history()
                st.rerun()

    if demo is None:
        st.stop()

    # ── Title ─────────────────────────────────────────────────────────────
    st.title("🤖 ReAct Agent")

    # Detect demo change → reset agent (keep traces)
    if sss.current_demo and sss.current_demo != demo.name:
        clear_chat_history(keep_traces=True)
        sss.agent = None
        sss.agent_config = None

    if sss.just_processed:
        sss.just_processed = False

    # ── Two-panel main layout ─────────────────────────────────────────────
    col_trace, col_chat = st.columns([2, 3], gap="medium")

    with col_trace:
        st.subheader("🔍 Execution Trace")
        trace_container = st.container(height=PANEL_HEIGHT, border=True)
        with trace_container:
            if "trace_middleware" in sss:
                display_interleaved_traces(sss.trace_middleware, key_prefix="main")
            else:
                st.info("No activity yet. Send a message to start.")

    with col_chat:
        st.subheader("💬 Conversation")
        chat_container = st.container(height=PANEL_HEIGHT, border=True)
        with chat_container:
            for msg in sss.messages:
                if isinstance(msg, HumanMessage):
                    st.chat_message("human").write(msg.content)
                elif isinstance(msg, AIMessage):
                    with st.chat_message("ai"):
                        render_message_with_mermaid(msg.content, st)
        status_container = st.empty()

    # ── Chat input ────────────────────────────────────────────────────────
    user_input = st.chat_input("Type your message… (or /help)", key="chat_input")

    if not user_input:
        return
    user_input = user_input.strip()

    if handle_command(user_input):
        return

    await process_user_input(
        demo,
        user_input,
        status_container,
        chat_container,
        trace_container,
    )


# Run the async main function only when executing in Streamlit context
try:
    # This will only work when running in a Streamlit context
    _ = st.session_state  # This will raise an exception if not in Streamlit context
    asyncio.run(main())
except (AttributeError, RuntimeError, Exception):
    # We're being imported, not running in Streamlit - skip execution
    pass
