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

# Initialize session state variables for managing agent output and display
if "agent_output" not in sss:
    sss.agent_output = []  # Stores all agent responses

if "result_display" not in sss:
    sss.result_display = st  # Default display container

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


def clear_display() -> None:
    """Clear the current display and reset agent output when changing demos"""
    sss.agent_output = []  # Reset stored outputs
    strecorder.clear()  # Clear the action recorder
    # st.rerun()  # Optional: Uncomment to force UI refresh


@tool
def my_final_answer(answer: Any) -> Any:
    """Display the final result of the AI agent's execution.

    This tool handles the presentation of different types of results including
    Markdown text, DataFrames, images, and Folium maps in the Streamlit interface.

    Args:
        answer: The final result to display, can be various types

    Returns:
        String representation of the answer
    """
    """
    Provides a final answer to the given problem.

        Args:
        answer : The final answer to the problem.  Can be Markdown or an object of type pd.DataFrame, Path or folium.Map
    """
    # additional_args = getattr(my_final_answer, "_additional_args", {})
    # widget = additional_args.get("widget") # Does not woek here
    if len(sss.agent_output) == 0 or sss.agent_output[-1] != answer:
        sss.agent_output.append(answer)
        display_final_msg(answer)
    return str(answer)


def update_display() -> None:
    """Update the Streamlit display with all accumulated agent outputs.

    This function iterates through the stored agent outputs and displays
    them in the appropriate format in the Streamlit interface.
    """
    if len(sss.agent_output) > 0:
        st.write("answer:")
    for msg in sss.agent_output:
        display_final_msg(msg)


def display_final_msg(msg: Any) -> None:
    """Display a single message in the appropriate format.

    This function handles the rendering of different message types including
    Markdown, DataFrames, images, and Folium maps in the Streamlit interface.

    Args:
        msg: The message to display, can be various types
    """
    try:
        with sss.result_display:
            if isinstance(msg, str):
                st.markdown(msg)
            # elif isinstance(msg, folium.Map):
            #     st_folium(msg)
            elif isinstance(msg, pd.DataFrame):
                st.dataframe(msg)
            elif isinstance(msg, Path):
                st.image(msg)
            else:
                st.write(msg)
    except Exception as ex:
        logger.exception(ex)
        raise ex


model_name = LlmFactory(llm_id=MODEL_ID).get_litellm_model_name()
llm = LiteLLMModel(model_id=model_name)


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
    HEIGHT = 800
    exec_block = placeholder.container()
    col_display_left, col_display_right = exec_block.columns(2)
    log_widget = col_display_left.container(height=HEIGHT)
    result_display = col_display_right.container(height=HEIGHT)
    sss.result_display = result_display

    mcp_client = None
    with col_display_right:
        update_display()
    try:
        mcp_tools = []
        if demo.mcp_servers:
            mcp_servers = dict_to_stdio_server_list(get_mcp_servers_dict(demo.mcp_servers))
            if mcp_servers:
                mcp_client = MCPClient(mcp_servers)  # type: ignore
                mcp_tools = mcp_client.get_tools()

        strecorder.replay(log_widget)
        with log_widget:
            if prompt:
                tools = demo.tools + mcp_tools + [my_final_answer]
                authorized_imports_list = list(dict.fromkeys(COMMON_AUTHORIZED_IMPORTS + demo.authorized_imports))
                agent = CodeAgent(
                    tools=tools,
                    model=llm,
                    additional_authorized_imports=authorized_imports_list,
                    max_steps=max_steps,  # for debug
                )
                with st.spinner(text="Thinking..."):
                    result_display.write(f"query: {prompt}")
                    formatted_prompt = PRE_PROMPT.format(authorized_imports=", ".join(authorized_imports_list)) + prompt
                    with strecorder:
                        stream_to_streamlit(
                            agent,
                            formatted_prompt,
                            # additional_args={"widget": col_display_right},  # does not work in fact
                            display_details=False,
                        )
                    scroll_to_here()
    finally:
        if mcp_client:
            mcp_client.disconnect()


def main() -> None:
    """Main function to set up and run the Streamlit application."""

    selected_pill = display_header_and_demo_selector(sample_demos) if sample_demos else None

    placeholder = st.empty()
    select_block = placeholder.container()
    if selected_pill:
        demo, sample_search, _, _ = handle_selection(selected_pill, select_block)
        prompt, max_steps, submitted = display_input_form(select_block, sample_search)

        if submitted:
            handle_submission(placeholder, demo, prompt, max_steps)


main()
