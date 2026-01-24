"""CodeAct Agent - A Streamlit-based interface for interactive AI-powered code execution.

This module provides a Streamlit web application that allows users to interact with an AI agent
capable of executing Python code in a controlled environment. The agent can perform various tasks
including data analysis, visualization, and web interactions using predefined tools and libraries.

Key Features:
- Interactive chat interface for code execution
- Support for multiple AI models
- Integration with various data sources and APIs
- Safe execution environment with restricted imports
- Real-time output display including plots and maps

Thread pool executors in SmolAgents create their own separate session state instance. so we need Module-Level Shared Storage
= ( _shared_agent_outputs)

┌─────────────────────────────────────────────────────────┐
│                   Streamlit Main Thread                 │
│  ┌───────────────────────────────────────────────────┐  │
│  │  handle_submission()                              │  │
│  │  • Creates agent with my_final_answer tool        │  │
│  │  • Starts execution                               │  │
│  └───────────────────────┬───────────────────────────┘  │
│                          │                              │
│                          ▼                              │
│  ┌───────────────────────────────────────────────────┐  │
│  │  SmolAgents CodeAgent                             │  │
│  │  └─► Spawns ThreadPoolExecutor                    │  │
│  └───────────────────────┬───────────────────────────┘  │
└──────────────────────────┼──────────────────────────────┘
                           │
         ┌─────────────────┴──────────────────┐
         │    Thread Pool Executor Thread     │
         │  ┌──────────────────────────────┐  │
         │  │  Agent executes Python code  │  │
         │  │  • Calls my_final_answer()   │  │
         │  │  • Stores in                 │  │
         │  │    _shared_agent_outputs ◄───┼──┼─ Module-level
         │  └──────────────────────────────┘  │    shared list
         └────────────────────────────────────┘
                           │
         ┌─────────────────┴──────────────────┐
         │      Back to Main Thread           │
         │  ┌──────────────────────────────┐  │
         │  │  handle_submission()         │  │
         │  │  • Reads _shared_agent_      │  │
         │  │    outputs                   │  │
         │  │  • Displays in right column  │  │
         │  └──────────────────────────────┘  │
         └────────────────────────────────────┘
"""

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from genai_tk.core.llm_factory import LlmFactory
from genai_tk.core.mcp_client import dict_to_stdio_server_list, get_mcp_servers_dict
from genai_tk.core.prompts import dedent_ws

# Import shared configuration functionality
from genai_tk.tools.smolagents.config_loader import (
    SmolagentsAgentConfig,
    load_all_demos_from_config,
)
from genai_tk.utils.load_data import TABULAR_FILE_FORMATS_READERS, load_tabular_data_once
from loguru import logger
from smolagents import (
    CodeAgent,
    LiteLLMModel,
    MCPClient,
    tool,
)
from smolagents.memory import FinalAnswerStep
from streamlit import session_state as sss
from streamlit.delta_generator import DeltaGenerator

from genai_blueprint.utils.streamlit.auto_scroll import scroll_to_here
from genai_blueprint.utils.streamlit.recorder import StreamlitRecorder
from genai_blueprint.webapp.ui_components.config_editor import edit_config_dialog
from genai_blueprint.webapp.ui_components.llm_selector import llm_selector_widget
from genai_blueprint.webapp.ui_components.smolagents_streamlit import stream_to_streamlit

MODEL_ID = None  # Use the one by configuration
# MODEL_ID = "gpt_41mini_openrouter"
# MODEL_ID = "kimi_k2_openrouter"
# MODEL_ID = "gpt_o3mini_openrouter"
# MODEL_ID = "qwen_qwq32_openrouter"

DATA_PATH = Path.cwd() / "use_case_data/other"
CONF_YAML_FILE = "config/agents/smolagents.yaml"

##########################
#  Initialize session state
##########################

# Initialize all session state variables before any usage to prevent AttributeError
if "agent_output" not in st.session_state:
    st.session_state["agent_output"] = []  # Stores all agent responses

if "result_display" not in sss:
    sss.result_display = None  # Display container for results

if "agent_running" not in sss:
    sss.agent_running = False  # Track if agent is currently executing

if "last_error" not in sss:
    sss.last_error = None  # Store last error for display

llm_selector_widget(st.sidebar)


##########################
#  SmolAgent parameters
##########################


# List of authorized Python packages that can be imported in the code execution environment
COMMON_AUTHORIZED_IMPORTS = [
    "pathlib",
    "numpy.*",
    "json",
    "streamlit",
    "base64",
    "tempfile",
]

PRINT_INFORMATION = "my_final_answer"

IMAGE_INSTRUCTION = dedent_ws(
    f""" 
    -  When creating a plot or generating an image:
      -- save it as png in a tempory directory (use tempfile)
      -- call '{PRINT_INFORMATION}' with the pathlib.Path  
"""
)

FOLIUM_INSTRUCTION = dedent_ws(
    f""" 
    - If requested by the user, use Folium to display a map. For example: 
        -- to display map at a given location, call  folium.Map([latitude, longitude])
        -- Do your best to select the zoom factor so whole location enter globaly in the map 
        -- save it as png in a tempory directory (use tempfile)
        -- Call the function '{PRINT_INFORMATION}' with the map object 
        """
)

PRE_PROMPT = dedent_ws(
    f"""
    Answer following request. 

    Instructions:
    - You can use ONLY the following packages:  {{authorized_imports}}.
    - DO NOT USE other packages (such as os, shutils, etc).
    - Use provided functions to gather information. Don't generate fake one if not explicly asked.
    - Don't generate "if __name__ == "__main__"
    - Don't use st.sidebar 
    - Call the function '{PRINT_INFORMATION}' with same content that 'final_answer', before calling it.

    - {IMAGE_INSTRUCTION}

    \nRequest :
    """
)

#  - Call the function '{PRINT_STEP}' to display intermediate informtation. It accepts markdown and str.
#  - Print also the outcome on stdio, or the title if it's a diagram.


# load_demos_from_config is now imported as load_all_demos_from_config from shared module


# Load demos from config
try:
    sample_demos = load_all_demos_from_config()
except Exception as ex:
    st.error(f"Cannot load demo: {ex}")
    st.stop()

##########################
#  UI
##########################


FILE_SElECT_CHOICE = ":open_file_folder: :orange[Select your file]"

# recorder of agents generated output, to be re-displayed when the page is rerun.
strecorder = StreamlitRecorder()

# Thread-safe shared storage for outputs from agent threads
# SmolAgents executes code in thread pool executors, which have separate session state instances.
# This module-level list acts as a bridge between the executor thread and main Streamlit thread.
# Python's GIL ensures thread-safe list operations without requiring explicit locks.
_shared_agent_outputs: list[Any] = []


def clear_display() -> None:
    """Clear the current display and reset agent output when changing demos"""
    global _shared_agent_outputs
    _shared_agent_outputs = []  # Clear shared storage
    if "agent_output" in st.session_state:
        st.session_state["agent_output"] = []  # Reset stored outputs
    sss.result_display = None  # Reset display container
    sss.last_error = None  # Clear any previous errors
    strecorder.clear()  # Clear the action recorder


@tool
def my_final_answer(answer: Any) -> Any:
    """Display the final result of the AI agent's execution.

    This tool stores outputs in a thread-safe shared storage that can be accessed
    by the main Streamlit thread for display. It handles various output types including
    text, DataFrames, images (as Path objects), and other data.

    Thread Safety:
        Uses module-level `_shared_agent_outputs` list to bridge thread pool executors
        and the main Streamlit thread, avoiding session state isolation issues.

    Args:
        answer: The result to display - can be str, DataFrame, Path, or other types

    Returns:
        String representation of the answer
    """
    global _shared_agent_outputs

    logger.info(f"my_final_answer called with {type(answer).__name__}: {answer}")

    try:
        # Convert string paths to Path objects for consistent image handling
        if isinstance(answer, str) and ("/" in answer or "\\" in answer):
            try:
                test_path = Path(answer)
                if test_path.suffix in [".png", ".jpg", ".jpeg", ".gif", ".svg"]:
                    answer = test_path
                    logger.debug(f"Converted string to Path for image: {answer}")
            except Exception as e:
                logger.debug(f"Could not convert to path: {e}")

        # Store in thread-safe shared storage
        _shared_agent_outputs.append(answer)
        logger.info(f"Stored output in shared storage (total: {len(_shared_agent_outputs)} items)")

        return str(answer)

    except Exception as e:
        error_msg = f"Error in my_final_answer: {e}"
        logger.error(error_msg)
        import traceback

        logger.error(traceback.format_exc())
        return error_msg


def update_display() -> None:
    """Update the Streamlit display with all accumulated agent outputs.

    This function iterates through the stored agent outputs and displays
    them in the appropriate format in the Streamlit interface.
    """
    if "agent_output" in st.session_state and len(st.session_state["agent_output"]) > 0:
        st.write("answer:")
        for msg in st.session_state["agent_output"]:
            display_final_msg(msg)


def display_final_msg(msg: Any) -> None:
    """Display a single message in the appropriate format.

    This function handles the rendering of different message types including
    Markdown, DataFrames, images, and Folium maps in the Streamlit interface.

    Args:
        msg: The message to display, can be various types
    """
    try:
        # Check if we're in a Streamlit context
        try:
            # Use result_display if available and is a container
            if (
                hasattr(sss, "result_display")
                and sss.result_display is not None
                and hasattr(sss.result_display, "__enter__")
            ):
                display_container = sss.result_display
            else:
                display_container = st.container()
        except (AttributeError, RuntimeError):
            # Called from thread without Streamlit context
            logger.debug("display_final_msg called from thread without Streamlit context")
            return  # Can't display in thread, will be handled by FinalAnswerStep

        with display_container:
            if isinstance(msg, str):
                st.markdown(msg)
            # elif isinstance(msg, folium.Map):
            #     st_folium(msg)
            elif isinstance(msg, pd.DataFrame):
                st.dataframe(msg, use_container_width=True)
            elif isinstance(msg, Path):
                if msg.exists():
                    st.image(str(msg))
                else:
                    st.warning(f"Image file not found: {msg}")
            else:
                st.write(msg)
    except (AttributeError, RuntimeError) as ex:
        # Thread context error - silently ignore as it will be handled by main thread
        logger.debug(f"display_final_msg thread context error (expected): {ex}")
    except Exception as ex:
        error_msg = f"Error displaying message: {ex}"
        logger.exception(error_msg)
        try:
            st.error(error_msg)
            sss.last_error = error_msg
        except (AttributeError, RuntimeError):
            pass  # Can't display error in thread context


# LLM will be initialized in handle_submission to avoid early initialization errors


##########################
#  UI functions
##########################


def display_header_and_demo_selector(sample_demos: list[SmolagentsAgentConfig]) -> str | None:
    """Displays the header and demo selector, returning the selected pill."""
    c01, c02 = st.columns([6, 4], border=False, gap="medium", vertical_alignment="top")
    c02.title(" CodeAct Agent :material/Mindfulness:")
    selected_pill = None

    if st.sidebar.button(":material/edit: Edit Config", help="Edit anonymization configuration"):
        edit_config_dialog(CONF_YAML_FILE)

    with c01.container(border=True):
        selector_col, edit_col = st.columns([8, 1], vertical_alignment="bottom")
        with selector_col:
            selected_pill = st.pills(
                ":material/open_with: **Demos:**",
                options=[demo.name for demo in sample_demos] + [FILE_SElECT_CHOICE],
                default=sample_demos[0].name,
                on_change=clear_display,
            )
    return selected_pill


def handle_selection(
    selected_pill: str, select_block: Any
) -> tuple[SmolagentsAgentConfig, str | None, pd.DataFrame | None, Any]:
    """Handles file upload or demo selection logic."""
    raw_data_file = None
    df = None
    sample_search = None
    if selected_pill == FILE_SElECT_CHOICE:
        raw_data_file = select_block.file_uploader(
            "Upload a Data file:",
            type=list(TABULAR_FILE_FORMATS_READERS.keys()),
        )
        demo = SmolagentsAgentConfig(name="custom", examples=[])
    else:
        demo = next((d for d in sample_demos if d.name == selected_pill), None)
        if demo is None:
            st.stop()
        col_display_left, col_display_right = select_block.columns([6, 3], vertical_alignment="bottom")
        with col_display_right:
            if tools_list := ", ".join(f"'{t.name}'" for t in demo.tools):
                st.markdown(f"**Tools**: *{tools_list}*")
            if mcp_list := ", ".join(f"'{mcp}'" for mcp in demo.mcp_servers):
                st.markdown(f"**MCP**: *{mcp_list}*")
        with col_display_left:
            sample_search = col_display_left.selectbox(
                label="Sample",
                placeholder="Select an example (optional)",
                options=demo.examples,
                index=None,
                label_visibility="collapsed",
            )
    if raw_data_file:
        with select_block.expander(label="Loaded Dataframe", expanded=True):
            args = {}
            df = load_tabular_data_once(raw_data_file, **args)
    return demo, sample_search, df, raw_data_file


def display_input_form(select_block: DeltaGenerator, sample_search: str | None) -> tuple[str, int, bool]:
    """Displays the input form and returns user input."""
    with select_block.form("my_form", border=False):
        cf1, cf2 = st.columns([15, 1], vertical_alignment="bottom")
        prompt = cf1.text_area(
            "Your task",
            height=68,
            placeholder="Enter or modify your query here...",
            value=sample_search or "",
            label_visibility="collapsed",
        )
        max_steps = cf2.number_input("Max steps", 1, 20, 10)
        submitted = cf2.form_submit_button(label="", icon=":material/send:")
    return prompt, max_steps, submitted


def handle_submission(placeholder: Any, demo: SmolagentsAgentConfig, prompt: str, max_steps: int) -> None:
    """Handles the agent execution on form submission."""
    # Prevent multiple simultaneous executions
    if sss.agent_running:
        st.warning("Agent is already running. Please wait for it to complete.")
        return

    sss.agent_running = True
    sss.last_error = None

    HEIGHT = 800
    exec_block = placeholder.container()
    col_display_left, col_display_right = exec_block.columns([1, 1], gap="medium")

    log_widget = col_display_left.container(height=HEIGHT, border=True)
    result_display = col_display_right.container(height=HEIGHT, border=True)
    sss.result_display = result_display

    mcp_client = None

    # Display existing results
    with result_display:
        update_display()

    try:
        mcp_tools = []
        if demo.mcp_servers:
            try:
                mcp_servers = dict_to_stdio_server_list(get_mcp_servers_dict(demo.mcp_servers))
                if mcp_servers:
                    mcp_client = MCPClient(mcp_servers)  # type: ignore
                    mcp_tools = mcp_client.get_tools()
                    logger.info(f"Loaded {len(mcp_tools)} MCP tools")
            except Exception as e:
                st.warning(f"Could not load MCP servers: {e}")
                logger.warning(f"MCP loading error: {e}")

        strecorder.replay(log_widget)

        with log_widget:
            if not prompt or not prompt.strip():
                st.warning("Please enter a task to execute.")
                return

            # Initialize LLM model with error handling
            try:
                model_name = LlmFactory(llm=MODEL_ID).get_litellm_model_name()
                llm = LiteLLMModel(model_id=model_name)
                logger.info(f"Initialized LLM: {model_name}")
            except Exception as e:
                error_msg = f"Failed to initialize LLM model: {e}"
                st.error(error_msg)
                logger.error(error_msg)
                sss.last_error = error_msg
                return

            # Build tool list and agent
            tools = demo.tools + mcp_tools + [my_final_answer]
            authorized_imports_list = list(dict.fromkeys(COMMON_AUTHORIZED_IMPORTS + demo.authorized_imports))

            logger.info(f"Creating agent with {len(tools)} tools and {len(authorized_imports_list)} authorized imports")

            try:
                agent = CodeAgent(
                    tools=tools,
                    model=llm,
                    additional_authorized_imports=authorized_imports_list,
                    max_steps=max_steps,
                )
                logger.info(
                    f"Created agent with {len(tools)} tools and {len(authorized_imports_list)} authorized imports"
                )
            except Exception as e:
                error_msg = f"Failed to create agent: {e}"
                st.error(error_msg)
                logger.error(error_msg)
                sss.last_error = error_msg
                return

            # Execute the agent
            with st.spinner(text="🤔 Agent is thinking..."):
                result_display.markdown(f"**Query:** {prompt}")
                result_display.divider()
                formatted_prompt = PRE_PROMPT.format(authorized_imports=", ".join(authorized_imports_list)) + prompt

                # Custom handler to display final answer in right column
                def handle_final_answer(step: FinalAnswerStep) -> None:
                    """Handle final answer step by displaying in the right column"""
                    from smolagents.agent_types import AgentAudio, AgentImage, AgentText

                    with result_display:
                        st.markdown("### 🎯 Final Answer")
                        final_answer = step.output
                        if isinstance(final_answer, AgentText):
                            st.markdown(final_answer.to_string())
                        elif isinstance(final_answer, AgentImage):
                            image_raw = final_answer.to_raw()
                            if image_raw is not None:
                                st.image(image_raw)
                        elif isinstance(final_answer, AgentAudio):
                            st.audio(final_answer.to_raw())
                        elif isinstance(final_answer, pd.DataFrame):
                            st.dataframe(final_answer, use_container_width=True)
                        elif isinstance(final_answer, Path):
                            if final_answer.exists():
                                st.image(str(final_answer))
                            else:
                                st.warning(f"Image file not found: {final_answer}")
                        else:
                            st.markdown(str(final_answer))

                try:
                    with strecorder:
                        stream_to_streamlit(
                            agent,
                            formatted_prompt,
                            display_details=True,
                            final_answer_handler=handle_final_answer,
                        )

                    # Display outputs collected by my_final_answer (from thread pool executor)
                    global _shared_agent_outputs
                    if len(_shared_agent_outputs) > 0:
                        logger.info(f"Displaying {len(_shared_agent_outputs)} outputs from agent")
                        with result_display:
                            st.markdown("### 🎯 Results from my_final_answer")
                            for output in _shared_agent_outputs:
                                if isinstance(output, str):
                                    st.markdown(output)
                                elif isinstance(output, pd.DataFrame):
                                    st.dataframe(output, use_container_width=True)
                                elif isinstance(output, Path):
                                    if output.exists():
                                        st.image(str(output))
                                    else:
                                        st.warning(f"Image file not found: {output}")
                                else:
                                    st.write(output)

                    st.success("✅ Agent execution completed")
                except KeyboardInterrupt:
                    st.warning("⚠️ Execution interrupted by user")
                    logger.warning("Agent execution interrupted")
                except Exception as e:
                    error_msg = f"Agent execution failed: {e}"
                    st.error(f"❌ {error_msg}")
                    logger.error(error_msg)
                    sss.last_error = error_msg

                    # Display detailed error information
                    import traceback

                    with st.expander("🐛 Full Error Traceback"):
                        st.code(traceback.format_exc(), language="python")

                scroll_to_here()

    except Exception as e:
        error_msg = f"Unexpected error in handle_submission: {e}"
        st.error(error_msg)
        logger.exception(error_msg)
        sss.last_error = error_msg

        import traceback

        with st.expander("🐛 Full Error Traceback"):
            st.code(traceback.format_exc(), language="python")

    finally:
        sss.agent_running = False
        if mcp_client:
            try:
                mcp_client.disconnect()
                logger.info("MCP client disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting MCP client: {e}")


def main() -> None:
    """Main function to set up and run the Streamlit application."""

    # Display any previous errors
    if sss.last_error:
        st.error(f"⚠️ Last error: {sss.last_error}")
        if st.button("Clear Error"):
            sss.last_error = None
            st.rerun()

    # Display running status
    if sss.agent_running:
        st.info("🏃 Agent is currently running...")

    selected_pill = display_header_and_demo_selector(sample_demos) if sample_demos else None

    placeholder = st.empty()
    select_block = placeholder.container()

    if selected_pill:
        demo, sample_search, _, _ = handle_selection(selected_pill, select_block)
        prompt, max_steps, submitted = display_input_form(select_block, sample_search)

        if submitted:
            handle_submission(placeholder, demo, prompt, max_steps)


main()
