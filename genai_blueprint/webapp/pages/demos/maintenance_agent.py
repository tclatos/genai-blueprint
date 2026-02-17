"""Demo of an LLM Augmented Autonomous Agent for Maintenance.

This module implements a Streamlit-based web application that demonstrates an LLM-augmented
autonomous agent for maintenance operations. The agent can:
- Access maintenance procedures and documentation
- Query planning databases
- Check tool availability and locations
- Provide task-specific information and requirements

The application provides sample prompts and allows users to ask their own questions
about maintenance operations, with the agent retrieving and synthesizing information
from multiple data sources.
"""

import asyncio
import uuid
from datetime import datetime
from typing import cast

import pandas as pd
import streamlit as st
from genai_tk.core.llm_factory import get_llm
from genai_tk.core.prompts import dedent_ws, dict_input_message
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger  # noqa: F401

from genai_blueprint.demos.maintenance_agent.dummy_data import dummy_database
from genai_blueprint.demos.maintenance_agent.tools import (
    DATA_PATH,
    PROCEDURES,
    create_maintenance_tools,
)
from genai_blueprint.utils.streamlit.clear_result import with_clear_container
from genai_blueprint.utils.streamlit.thread_issue_fix import get_streamlit_cb
from genai_blueprint.webapp.ui_components.streamlit_chat import StreamlitStatusCallbackHandler, display_messages

# fmt:off
SAMPLE_PROMPTS = {
  #  "Display a diagram" : "Display a diagram",

    "Task prerequisite and required tools":
        "What are the required tools and prerequisite for task 'Diaphragm Inspection' of procedure 'Power Plant Steam Turbine'?",
    "Required tools availability and localization":  """
            Print the required tools for task 'Diaphragm Inspection' in procedure 'Power Plant Steam Turbine',
            check if they are available and print their localization""",
    "Tasks assigned to an employee":
            "print the tasks assigned to employee 'John Smith' next 2 days",
    "Print assigned tasks to an employee, spares needed, required tools, their availability and localization": """
        Follow these steps:
        -  print the tasks assigned to employee John Smith next 5 days.
        -  print the tools required for these tasks
        -  print the spare parts required for these tasks.
        -  for each of these spare parts, print their availability and localization.
        Print different sections for each step.""",
    "Values from the sensor 'signal_1' last 2 weeks":
        "Values from the sensor 'signal_1' last week ",
}
# fmt:on

LLM_ID = None


################################
#  UI
################################

st.title("Maintenance Operation Assistant")
st.markdown(
    """
    ## Autonomous Agent Demo for Maintenance Operation.


    The goal is to support  plant turbine maintenance operations.
    Currently, we gather information from:
    - Maintenance procedures  (text document)
    - Planning System   (SQL database)
    - ERP and PLM (API)
""",
    unsafe_allow_html=True,
)

b_column = st.columns(4)
if b_column[0].button("See Planning DB"):
    default_sql = """SELECT * FROM "tasks" ;"""
    with st.expander("Tasks Planning Database", expanded=True):
        sql = st.text_input(label="query", value=default_sql, key="sql_input")
        df = pd.read_sql(sql, dummy_database())
        st.write(df)
        print(sql)

if b_column[1].button("See Sensors Values DB"):
    sql = """SELECT *  FROM "sensor_data" ;"""
    df = pd.read_sql(sql, dummy_database())
    with st.expander("Sensor Values Database", expanded=True):
        st.write(sql)
        st.write(df)

if b_column[2].button("See Procedure", key="procedure"):
    with st.expander("Maintenance Procedure", expanded=True):
        with open(DATA_PATH / PROCEDURES[0]) as file:
            st.write(file.read())


def extract_right_part(string: str, separator: str) -> str:
    """Extract the right part of a string after a separator."""
    return string.split(separator)[1].strip() if separator in string else string.strip()


if b_column[3].button("See tools"):
    with st.expander("Available tools", expanded=True):
        tools = create_maintenance_tools()
        tool_list = [(tool.name, extract_right_part(tool.description, "-> str")) for tool in tools]
        df = pd.DataFrame(tool_list, columns=["name", "description"])
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            column_config={
                "name": st.column_config.Column(width="small"),
                "description": st.column_config.Column(width="large"),
            },  # does  not seems to work :(
        )

sample_prompt_key = st.selectbox("Sample prompts", SAMPLE_PROMPTS.keys(), index=None, placeholder="choose an example")
sample_prompt = ""
if sample_prompt_key:
    sample_prompt = dedent_ws(SAMPLE_PROMPTS.get(sample_prompt_key, "").strip())
with st.form(key="form"):
    user_input = st.text_area(label="Or, ask your own question / prompt", value=sample_prompt, height=150)
    submit_clicked = st.form_submit_button("Submit Question")

# Initialize messages in session state if not present
if "messages" not in st.session_state:
    st.session_state.messages = []


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


# System prompt for the maintenance agent
SYSTEM_PROMPT = dedent_ws(
    """
    You are a helpful assistant to help a maintenance engineer.
    To do so, you have different tools to access maintenance planning, spares etc.
    Make sure to use only the provided tools to answer the user request.
    If you don't find relevant tool, answer "I don't know"
    """
)


async def main() -> None:
    """Main async function to run the Maintenance Agent demo.

    Handles:
    - UI setup and demo selection
    - Tool initialization
    - Agent execution
    - Streaming output display
    """
    display_messages(st)

    if not with_clear_container(submit_clicked):
        return

    # Add current date context to the query

    # Add message to chat history
    st.session_state.messages.append(HumanMessage(content=user_input))
    st.chat_message("user").write(user_input)

    # Create status to show agent progress
    status = st.status("Agent starting...", expanded=True)
    status_callback = StreamlitStatusCallbackHandler(status)

    # Get agent configuration
    config, checkpointer = get_agent_config()
    agent = create_agent(
        model=get_llm(),
        tools=create_maintenance_tools(),
        system_prompt=f"{SYSTEM_PROMPT}\nCurrent date:{datetime.now().strftime('%Y-%m-%d')}",
        checkpointer=checkpointer,
    )
    st_callback = get_streamlit_cb(st.container())

    # Prepare input and config
    inputs = dict_input_message(user=user_input)
    config["configurable"].update({"st_container": status})

    try:
        # Run agent
        astream = agent.astream(
            inputs,
            config | {"callbacks": [st_callback, status_callback]},
        )

        async for step in astream:
            for node, update in step.items():
                if node == "agent":
                    response = update["messages"][-1]
                    assert isinstance(response, AIMessage)
                    st.chat_message("ai", avatar="🛠️").write(response.content)

            url = st_callback.get_run_url()
            st.session_state.messages.append(response)
            if url:
                st.link_button("Trace", url)

        status.update(label="Done", state="complete", expanded=False)
    except Exception as ex:
        logger.exception(ex)
        st.error(f"An error occurred: {ex}")


# Run the async main function
asyncio.run(main())
