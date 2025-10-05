"""
Streamlit page for Deep Agent demo.

Provides an interactive interface to run Deep Agents with different configurations.
Uses the same configuration system as the CLI for consistency.

"""

import asyncio
import uuid
from pathlib import Path
from typing import cast

import streamlit as st
from dotenv import load_dotenv
from genai_tk.core.deep_agents import DeepAgentConfig, deep_agent_factory, run_deep_agent
from genai_tk.core.llm_factory import get_llm
from genai_tk.tools.smolagents.config_loader import process_tools_from_config
from genai_tk.tools.smolagents.deep_config_loader import (
    load_all_deep_agent_demos_from_config,
)
from langchain.callbacks import tracing_v2_enabled
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from smolagents import Tool as SmolAgentTool
from streamlit import session_state as sss
from streamlit.delta_generator import DeltaGenerator

from genai_blueprint.utils.streamlit.thread_issue_fix import get_streamlit_cb
from genai_blueprint.webapp.ui_components.config_editor import edit_config_dialog
from genai_blueprint.webapp.ui_components.llm_selector import llm_selector_widget
from genai_blueprint.webapp.ui_components.streamlit_chat import StreamlitStatusCallbackHandler, display_messages

load_dotenv()

CONFIG_FILE = "config/agents/deepagents.yaml"
assert Path(CONFIG_FILE).exists(), f"Cannot load {CONFIG_FILE}"

# Only run UI code when this script is executed in Streamlit context (not during import)
try:
    # This will only work when running in a Streamlit context
    _ = st.session_state  # This will raise an exception if not in Streamlit context

    st.title("Deep Agent")

    # Sidebar: LLM selector and config editor
    llm_selector_widget(st.sidebar)
    if st.sidebar.button(":material/edit: Edit Config", help="Edit Deep Agent configuration"):
        edit_config_dialog(CONFIG_FILE)
except (AttributeError, RuntimeError, Exception):
    # We're being imported, not running in Streamlit - skip UI code
    pass


# Load demos when actually running the UI, not during import
SAMPLES_DEMOS = None


def clear_display() -> None:
    """Reset the chat display and agent state."""
    if "messages" in sss:
        sss.messages = []
    if "current_agent" in sss:
        del sss.current_agent
    if "agent_files" in sss:
        del sss.agent_files


def display_header_and_demo_selector(sample_demos: list) -> str | None:
    """Displays the header and demo selector, returning the selected pill."""
    c01, c02 = st.columns([6, 1], border=False, gap="medium", vertical_alignment="top")
    selected_pill = None

    if not sample_demos:
        with c01.container(border=True):
            st.warning("No demo configurations found. Please check your config file.")
        return None

    with c01.container(border=True):
        selector_col, edit_col = st.columns([8, 1], vertical_alignment="bottom")
        with selector_col:
            selected_pill = st.pills(
                ":material/psychology: **Deep Agent Demos:**",
                options=[demo.name for demo in sample_demos],
                default=sample_demos[0].name,
                on_change=clear_display,
            )
    return selected_pill


def display_demo_info_and_sample_selector(demo, select_block):
    """Display demo information and sample selector."""
    col_display_left, col_display_right = select_block.columns([6, 3], vertical_alignment="bottom")
    with col_display_right:
        if demo.tools and (tools_list := f"{len(demo.tools)} tool(s)"):
            st.markdown(f"**Tools**: *{tools_list}*")
        if (
            hasattr(demo, "mcp_servers")
            and demo.mcp_servers
            and (mcp_list := ", ".join(f"'{mcp}'" for mcp in demo.mcp_servers))
        ):
            st.markdown(f"**MCP**: *{mcp_list}*")
        if demo.enable_file_system:
            st.markdown("**File System**: *Enabled*")
        if demo.enable_planning:
            st.markdown("**Planning**: *Enabled*")

    with col_display_left:
        sample_search = col_display_left.selectbox(
            label="Sample",
            placeholder="Select an example (optional)",
            options=demo.examples if hasattr(demo, "examples") and demo.examples else [],
            index=None,
            label_visibility="collapsed",
        )
    return sample_search


@st.cache_resource()
def get_agent_config() -> tuple[RunnableConfig, BaseCheckpointSaver]:
    """Create and cache agent configuration.

    Returns:
        Tuple of (RunnableConfig, checkpoint saver) with unique thread ID
    """
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    checkpointer = MemorySaver()
    return cast(RunnableConfig, config), checkpointer


def display_input_form(select_block, sample_search: str | None) -> tuple[str, bool]:
    """Displays the input form and returns user input."""
    with select_block.form("deep_agent_form", border=False):
        cf1, cf2 = st.columns([15, 1], vertical_alignment="bottom")
        prompt = cf1.text_area(
            "Your question",
            height=68,
            placeholder="Enter your question here...",
            value=sample_search or "",
            label_visibility="collapsed",
        )
        submitted = cf2.form_submit_button(label="", icon=":material/send:")
    return prompt, submitted


async def handle_agent_execution(placeholder: DeltaGenerator, demo, query: str) -> None:
    """Handle the agent execution with proper UI layout."""
    HEIGHT = 800
    exec_block = placeholder.container()
    chat_container = exec_block.container(height=HEIGHT)

    config, checkpointer = get_agent_config()
    llm = get_llm()

    try:
        with chat_container:
            display_messages(st)
            st.chat_message("human").write(query)

            # Create status to show agent progress
            status = st.status("Deep Agent starting...", expanded=True)
            status_callback = StreamlitStatusCallbackHandler(status)
            st_callback = get_streamlit_cb(st.container())

            # Set up the Deep Agent factory with the current LLM
            deep_agent_factory.set_default_model(llm)

            # Create agent configuration from demo
            agent_config = DeepAgentConfig(
                name=f"Interactive {demo.name} Agent",
                instructions=demo.instructions,
                enable_file_system=getattr(demo, "enable_file_system", True),
                enable_planning=getattr(demo, "enable_planning", True),
            )

            # Process tools from configuration
            agent_tools = []
            if demo.tools:
                try:
                    # Process tools using the smolagents processor
                    processed_tools = process_tools_from_config(demo.tools)

                    # Convert SmolAgent tools to LangChain tools
                    for tool_instance in processed_tools:
                        if isinstance(tool_instance, SmolAgentTool):
                            # Convert SmolAgent tool to LangChain tool
                            try:

                                def create_langchain_wrapper(smol_tool):
                                    @tool
                                    def langchain_tool_wrapper(query: str) -> str:
                                        """Tool converted from SmolAgent."""
                                        return str(smol_tool(query))

                                    # Set proper metadata
                                    langchain_tool_wrapper.name = getattr(smol_tool, "name", type(smol_tool).__name__)
                                    langchain_tool_wrapper.description = getattr(
                                        smol_tool, "description", f"Tool: {langchain_tool_wrapper.name}"
                                    )
                                    return langchain_tool_wrapper

                                langchain_tool = create_langchain_wrapper(tool_instance)
                                agent_tools.append(langchain_tool)
                            except Exception as convert_ex:
                                st.warning(f"Failed to convert SmolAgent tool {tool_instance}: {convert_ex}")
                        else:
                            # Already a LangChain tool or compatible
                            agent_tools.append(tool_instance)

                except Exception as ex:
                    st.warning(f"Failed to process some tools from config: {ex}")

            # Create the deep agent
            if "current_agent" not in sss or sss.get("current_demo_name") != demo.name:
                agent = deep_agent_factory.create_agent(config=agent_config, tools=agent_tools, async_mode=True)
                sss.current_agent = agent
                sss.current_demo_name = demo.name
                sss.agent_files = {}

            # Run the agent
            messages = [{"role": "user", "content": query}]

            response = "A problem occurred"

            with tracing_v2_enabled() as cb:
                try:
                    result = await run_deep_agent(
                        agent=sss.current_agent, messages=messages, files=sss.get("agent_files", {}), stream=False
                    )

                    # Update files if changed
                    if "files" in result:
                        sss.agent_files = result["files"]

                    # Extract response
                    if "messages" in result and result["messages"]:
                        response_content = result["messages"][-1].content
                        response = AIMessage(content=response_content)
                        st.chat_message("ai").write(response_content)
                    else:
                        response = AIMessage(content=str(result))
                        st.chat_message("ai").write(str(result))

                except Exception as e:
                    error_msg = f"Error running Deep Agent: {str(e)}"
                    response = AIMessage(content=error_msg)
                    st.chat_message("ai").error(error_msg)

                url = cb.get_run_url()

            status.update(label="Done", state="complete", expanded=False)

            # Update session state messages
            if "messages" not in sss:
                sss.messages = []
            sss.messages.append(HumanMessage(content=query))
            if response:
                sss.messages.append(response)

            st.link_button("Trace", url)

            # Show files if any were created/modified
            if sss.get("agent_files"):
                st.divider()
                with st.expander("📁 Virtual File System", expanded=False):
                    for filename, content in sss.agent_files.items():
                        st.text_area(filename, value=content, height=150, key=f"file_{filename}", disabled=True)

    except Exception as e:
        status.update(label="Error", state="error", expanded=False)
        st.error(f"An error occurred: {str(e)}")


async def main() -> None:
    """Main async function to run the Deep Agent demo."""
    # Load demos when actually running the UI
    global SAMPLES_DEMOS
    if SAMPLES_DEMOS is None:
        SAMPLES_DEMOS = load_all_deep_agent_demos_from_config()

    # Main UI setup
    selected_pill = display_header_and_demo_selector(SAMPLES_DEMOS)

    # Get selected demo
    demo = next((d for d in SAMPLES_DEMOS if d.name == selected_pill), None)
    if demo is None:
        st.stop()

    # Create main placeholder and select block container
    placeholder = st.empty()
    select_block = placeholder.container()

    # Display demo information and sample selector
    sample_search = display_demo_info_and_sample_selector(demo, select_block)

    # Get user input
    query, submitted = display_input_form(select_block, sample_search)

    if submitted and query:
        await handle_agent_execution(placeholder, demo, query)


# Run the async main function only when executing in Streamlit context
try:
    _ = st.session_state  # This will raise an exception if not in Streamlit context
    asyncio.run(main())
except (AttributeError, RuntimeError, Exception):
    # We're being imported, not running in Streamlit - skip execution
    pass
