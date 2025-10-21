import textwrap
from typing import Any, Dict, List

import streamlit as st
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage
from loguru import logger
from streamlit.delta_generator import DeltaGenerator


class StreamlitStatusCallbackHandler(BaseCallbackHandler):
    """Callback handler for updating Streamlit status with LLM and tool calls."""

    def __init__(self, status_widget: DeltaGenerator) -> None:
        self.status_widget = status_widget
        self.current_steps = []

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        llm_name = serialized["kwargs"].get("model_name", "LLM")
        self.status_widget.write(f"Call {llm_name}...")

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        tool_name = serialized.get("name", "Tool")
        self.status_widget.write(f"Call tool: {tool_name} args: {textwrap.shorten(input_str, 20, placeholder='...}')}")


def display_messages(container: DeltaGenerator | Any) -> None:
    if "messages" not in st.session_state:
        st.session_state["messages"] = [AIMessage(content="How can I help you?")]

    # Loop through all messages in the query session state and render them as a chat on every st.refresh
    for msg in st.session_state.messages:
        # https://docs.streamlit.io/develop/api-reference/chat/st.chat_message
        # we store them as AIMessage and HumanMessage as its easier to send to LangGraph
        if isinstance(msg, AIMessage) and msg.content:
            container.chat_message("ai").write(msg.content)
            if hasattr(msg, "trace_url"):
                st.link_button("Trace", msg.trace_url)  # type: ignore
        elif isinstance(msg, HumanMessage) and msg.content:
            container.chat_message("human").write(msg.content)
        else:
            logger.warning(f"unknown message ! {msg}")
