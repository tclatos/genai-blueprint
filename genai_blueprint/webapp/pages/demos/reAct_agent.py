"""Streamlit page for ReAct Agent demo.

Provides an interactive chat interface to run ReAct agents with different configurations.
Supports custom tools, MCP servers integration, demo presets, and command handling.
Features a two-column layout with tool calls tracking and conversation display.
Example prompts are displayed for easy copy/paste into the chat input.

"""

import asyncio
import textwrap
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple, cast

import streamlit as st
from dotenv import load_dotenv
from genai_tk.core.llm_factory import get_llm
from genai_tk.core.mcp_client import get_mcp_servers_dict
from genai_tk.core.prompts import dedent_ws
from genai_tk.tools.langchain.shared_config_loader import LangChainAgentConfig, load_all_langchain_agent_configs
from langchain.callbacks import tracing_v2_enabled
from langchain.callbacks.base import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from streamlit import session_state as sss

from genai_blueprint.webapp.ui_components.config_editor import edit_config_dialog
from genai_blueprint.webapp.ui_components.llm_selector import llm_selector_widget

load_dotenv()

from langchain_community.tools import DuckDuckGoSearchRun  # noqa: E402

duckduck_search_tool = DuckDuckGoSearchRun()

CONFIG_FILE = "config/agents/langchain.yaml"
assert Path(CONFIG_FILE).exists(), f"Cannot load {CONFIG_FILE}"

# Default system prompt
SYSTEM_PROMPT = dedent_ws(
    """
    Your are a helpful assistant. Use provided tools to answer questions. \n
    - If the user asks for a list of something and that the tool returns a list, print it as Markdown table. 
"""
)


class StreamlitToolCallbackHandler(BaseCallbackHandler):
    """Callback handler for tracking tool calls in Streamlit."""

    def __init__(self) -> None:
        self.tool_calls = []
        self.current_tool_call = None

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        # Don't track LLM calls as tool calls
        pass

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        tool_name = serialized.get("name", "Unknown Tool")
        print(f"Tool started: {tool_name} with input: {str(input_str)[:100]}...")  # Debug
        self.current_tool_call = {
            "tool_name": tool_name,
            "input": str(input_str),
            "output": None,
            "error": None,
        }

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        if self.current_tool_call:
            self.current_tool_call["output"] = str(output)
            self.tool_calls.append(self.current_tool_call.copy())
            print(f"Tool completed: {self.current_tool_call['tool_name']}")  # Debug
            self.current_tool_call = None

    def on_tool_error(self, error: Exception, **kwargs: Any) -> None:
        if self.current_tool_call:
            self.current_tool_call["error"] = str(error)
            self.tool_calls.append(self.current_tool_call.copy())
            print(f"Tool error: {self.current_tool_call['tool_name']} - {error}")  # Debug
            self.current_tool_call = None


def initialize_session_state() -> None:
    """Initialize session state variables."""
    if "messages" not in sss:
        sss.messages = [AIMessage(content="Hello! I'm your ReAct agent. How can I help you today?")]
    if "tool_calls" not in sss:
        sss.tool_calls = []
    if "last_trace_url" not in sss:
        sss.last_trace_url = None
    if "agent" not in sss:
        sss.agent = None
    if "agent_config" not in sss:
        sss.agent_config = None
    if "current_demo" not in sss:
        sss.current_demo = None
    if "just_processed" not in sss:
        sss.just_processed = False


def clear_chat_history() -> None:
    """Reset the chat history and related state."""
    if "messages" in sss:
        sss.messages = [AIMessage(content="Hello! I'm your ReAct agent. How can I help you today?")]
    if "tool_calls" in sss:
        sss.tool_calls = []
    if "last_trace_url" in sss:
        sss.last_trace_url = None
    # Don't clear agent/config - let them persist to avoid recreation


def display_header_and_demo_selector(sample_demos: list[LangChainAgentConfig]) -> str | None:
    """Displays the header and demo selector, returning the selected pill."""
    st.title("🤖 ReAct Agent Chat")

    if not sample_demos:
        st.warning("No demo configurations found. Please check your config file.")
        return None

    # Demo selector in sidebar
    with st.sidebar:
        llm_selector_widget(st.sidebar)
        if st.button(":material/edit: Edit Config", help="Edit agent configuration"):
            edit_config_dialog(CONFIG_FILE)

        st.divider()

        # Find the current selection index to avoid constant recreation
        current_demo_index = 0
        if sss.current_demo:
            try:
                current_demo_index = [demo.name for demo in sample_demos].index(sss.current_demo)
            except ValueError:
                current_demo_index = 0

        selected_pill = st.selectbox(
            "Select Demo Configuration:",
            options=[demo.name for demo in sample_demos],
            index=current_demo_index,
            key="demo_selector",
        )

        # Only clear history if the demo actually changed
        if sss.current_demo and sss.current_demo != selected_pill:
            clear_chat_history()
            # Reset agent to force recreation with new demo
            sss.agent = None
            sss.agent_config = None

        # Show demo info
        demo = next((d for d in sample_demos if d.name == selected_pill), None)
        if demo:
            if demo.tools:
                tools_list = ", ".join(f"'{t.name}'" for t in demo.tools)
                st.markdown(f"**Tools**: {tools_list}")
            if demo.mcp_servers:
                mcp_list = ", ".join(f"'{mcp}'" for mcp in demo.mcp_servers)
                st.markdown(f"**MCP**: {mcp_list}")
            if demo.examples:
                with st.container(border=True):
                    st.markdown(
                        "**Examples:**",
                        help="💡 **Copy any example below and paste it into the chat input to get started!",
                    )
                    for i, example in enumerate(demo.examples, 1):
                        st.code(example, language="text", height=None, wrap_lines=True)

        if st.button("🗑️ Clear Chat History"):
            clear_chat_history()
            st.rerun()

    return selected_pill


def display_tool_calls_sidebar(tool_calls: List[Dict[str, Any]]) -> None:
    """Display tool calls in the left column with expandable details."""
    if not tool_calls:
        st.info("No tool calls yet. Send a message to see tool interactions!")
        return

    st.subheader("🔧 Tool Calls")
    for i, call in enumerate(tool_calls):
        tool_name = call.get("tool_name", "Unknown Tool")
        input_str = call.get("input", "")
        output = call.get("output")
        error = call.get("error")

        # Create an expander for each tool call
        status_emoji = "❌" if error else "✅"
        short_input = textwrap.shorten(str(input_str), 50, placeholder="...")

        with st.expander(f"{status_emoji} {tool_name} - {short_input}", expanded=False):
            st.markdown(f"**Tool:** `{tool_name}`")

            st.markdown("**Input:**")
            st.code(input_str, language="text")

            if error:
                st.markdown("**Error:**")
                st.error(error)
            elif output:
                st.markdown("**Output:**")
                # Truncate very long outputs
                display_output = output
                MAX_OUTPUT = 2000
                if len(str(output)) > MAX_OUTPUT:
                    display_output = str(output)[:MAX_OUTPUT] + "\n\n... (truncated)"
                st.code(display_output, language="text")
            else:
                st.info("Tool is still running...")


@st.cache_resource()
def get_cached_checkpointer():
    """Get a cached checkpointer to avoid recreating it."""
    return MemorySaver()


def get_or_create_agent(demo: LangChainAgentConfig) -> Tuple[Any, RunnableConfig, BaseCheckpointSaver]:
    """Get or create agent for the current demo configuration.

    Returns:
        Tuple of (agent, config, checkpointer)
    """
    # Check if we need to create a new agent
    if sss.agent is None or sss.current_demo != demo.name or sss.agent_config is None:
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        checkpointer = get_cached_checkpointer()

        # This will be set up later in the async function
        sss.agent_config = config
        sss.current_demo = demo.name

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
        if sss.last_trace_url:
            st.success(f"Opening trace: {sss.last_trace_url}")
            # Note: webbrowser.open() doesn't work in Streamlit, so we show a link
            st.link_button("🔗 Open Trace", sss.last_trace_url)
        else:
            st.warning("No trace URL available yet. Send a message first!")
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


async def setup_agent_if_needed(demo: LangChainAgentConfig) -> Any:
    """Set up the agent if it doesn't exist or configuration changed."""
    agent, config, checkpointer = get_or_create_agent(demo)

    if agent is None:
        with st.spinner("Setting up agent..."):
            llm = get_llm()

            # Get MCP servers from selected demo
            mcp_servers_params = get_mcp_servers_dict(demo.mcp_servers) if demo.mcp_servers else {}
            all_tools = demo.tools.copy()

            if mcp_servers_params:
                try:
                    client = MultiServerMCPClient(mcp_servers_params)
                    mcp_tools = await client.get_tools()
                    all_tools.extend(mcp_tools)
                except Exception as e:
                    st.error(f"Failed to connect to MCP servers: {e}")

            # Create agent with demo's system prompt or default
            system_prompt = demo.system_prompt or SYSTEM_PROMPT
            agent = create_react_agent(model=llm, tools=all_tools, prompt=system_prompt, checkpointer=checkpointer)

            # Cache the agent
            sss.agent = agent

    return sss.agent


async def process_user_input(
    demo: LangChainAgentConfig, user_input: str, status_container, chat_container=None
) -> None:
    """Process user input and generate agent response."""
    # Add user message to chat
    sss.messages.append(HumanMessage(content=user_input))

    # Display user message immediately if chat container is provided
    if chat_container:
        with chat_container:
            st.chat_message("human").write(user_input)

    # Set up agent
    agent = await setup_agent_if_needed(demo)

    # Create tool callback handler
    tool_callback = StreamlitToolCallbackHandler()

    # Get current config
    _, config, _ = get_or_create_agent(demo)

    try:
        with status_container.status("🤖 Agent is thinking...", expanded=True) as status:
            status.write("Processing your request...")

            # Prepare inputs - use the format that works in the CLI version
            inputs = {"messages": [HumanMessage(content=user_input)]}

            # Set up callbacks
            callbacks = [tool_callback]

            response_content = ""
            final_response = None

            # Stream the response
            with tracing_v2_enabled() as cb:
                astream = agent.astream(inputs, config | {"callbacks": callbacks})
                async for step in astream:
                    status.write(f"Processing step: {type(step).__name__}")

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
                                        status.write(f"Got AI response: {len(response_content)} chars")

                                # Also check for HumanMessages (tool calls)
                                elif isinstance(latest_message, HumanMessage):
                                    status.write(f"Tool interaction: {latest_message.content[:100]}...")

                # Get trace URL
                sss.last_trace_url = cb.get_run_url()

            status.update(label="✅ Complete!", state="complete", expanded=False)

        # Add the response to messages and display immediately
        if final_response and final_response.content:
            sss.messages.append(final_response)
            # Display AI response immediately if chat container is provided
            if chat_container:
                with chat_container:
                    st.chat_message("ai").write(final_response.content)
            status_container.success(f"Response added: {len(final_response.content)} characters")
        elif response_content:
            ai_message = AIMessage(content=response_content)
            sss.messages.append(ai_message)
            # Display AI response immediately if chat container is provided
            if chat_container:
                with chat_container:
                    st.chat_message("ai").write(response_content)
            status_container.success(f"Response added: {len(response_content)} characters")
        else:
            error_msg = "I apologize, but I couldn't generate a proper response."
            sss.messages.append(AIMessage(content=error_msg))
            # Display error message immediately if chat container is provided
            if chat_container:
                with chat_container:
                    st.chat_message("ai").write(error_msg)
            status_container.warning("No response content found")

        # Update tool calls in session state
        if tool_callback.tool_calls:
            sss.tool_calls.extend(tool_callback.tool_calls)
            status_container.info(f"Added {len(tool_callback.tool_calls)} tool calls")

        # Mark that we just processed input to prevent re-execution
        sss.just_processed = True
        status_container.success(
            f"✅ Processing complete! Messages: {len(sss.messages)}, Tool calls: {len(sss.tool_calls)}"
        )

    except Exception as e:
        status_container.error(f"An error occurred: {str(e)}")
        sss.messages.append(AIMessage(content=f"I encountered an error: {str(e)}"))
        # Also set flag for error case to prevent re-execution
        sss.just_processed = True
        import traceback

        st.error(f"Full traceback: {traceback.format_exc()}")


async def main() -> None:
    """Main async function to run the ReAct agent demo."""
    # Initialize session state
    initialize_session_state()

    # Load demo configurations
    sample_demos = load_all_langchain_agent_configs(CONFIG_FILE, "react_agent_demos")

    if not sample_demos:
        st.error(f"No demo configurations found in {CONFIG_FILE}")
        st.stop()

    # Display header and demo selector (in sidebar)
    selected_demo_name = display_header_and_demo_selector(sample_demos)

    # Get selected demo
    demo = next((d for d in sample_demos if d.name == selected_demo_name), None)
    if demo is None:
        st.error("Selected demo configuration not found")
        st.stop()

    # Reset the just_processed flag at the start of each run
    # This ensures that after one cycle of processing, we can handle new input
    if sss.just_processed:
        sss.just_processed = False

    # Create two-column layout
    col_tools, col_chat = st.columns([1, 2], gap="medium")

    # Left column: Tool calls
    with col_tools:
        st.header("🔧 Activity")
        display_tool_calls_sidebar(sss.tool_calls)

        # Show trace link if available (persistent after interactions)
        if sss.last_trace_url:
            st.divider()
            st.link_button("🔗 View Trace", sss.last_trace_url)
            st.caption("Latest interaction trace")

    # Right column: Chat interface
    with col_chat:
        st.header("💬 Conversation")

        # Debug info
        if len(sss.messages) > 1:  # Don't show for just the welcome message
            st.caption(f"Debug: {len(sss.messages)} messages, {len(sss.tool_calls)} tool calls")

        # Display chat messages
        chat_container = st.container(height=600)
        with chat_container:
            for msg in sss.messages:
                if isinstance(msg, HumanMessage):
                    st.chat_message("human").write(msg.content)
                elif isinstance(msg, AIMessage):
                    st.chat_message("ai").write(msg.content)

        # Chat input at the bottom
        user_input = st.chat_input("Type your message here... (or use /help for commands)", key="chat_input")

        # Handle user input - but only if we haven't just processed something
        if user_input and not sss.just_processed:
            user_input = user_input.strip()

            # Handle commands
            if handle_command(user_input):
                if user_input == "/clear":
                    # The rerun is handled in handle_command
                    pass
                # Command handled, don't process as regular input
                return

            # Process regular user input
            if user_input:
                col_tools.info(f"🚀 Processing input: {user_input[:100]}...")
                await process_user_input(demo, user_input, col_tools, chat_container)
                # Processing complete - response is already displayed


# Run the async main function only when executing in Streamlit context
try:
    # This will only work when running in a Streamlit context
    _ = st.session_state  # This will raise an exception if not in Streamlit context
    asyncio.run(main())
except (AttributeError, RuntimeError, Exception):
    # We're being imported, not running in Streamlit - skip execution
    pass
