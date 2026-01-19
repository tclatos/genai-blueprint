# Source : https://raw.githubusercontent.com/huggingface/smolagents/refs/heads/main/src/smolagents/gradio_ui.py

#!/usr/bin/env python
# coding=utf-8
# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Streamlit UI components for smolagents integration.
Provides functions to display agent steps and stream agent outputs in Streamlit apps.
"""

# Update prompt:
# smolagents_streamlit.py is a port of gradio_ui.py to streamlit.  However, the smolagents package has evolved.
# Modify smolagents_streamlit.py to make it works with new version

import re
from typing import Dict, List, Optional

import streamlit as st
from devtools import debug  # ignore
from PIL import Image
from smolagents.agent_types import AgentAudio, AgentImage, AgentText
from smolagents.agents import MultiStepAgent, PlanningStep
from smolagents.memory import ActionStep, FinalAnswerStep, MemoryStep
from smolagents.models import ChatMessageStreamDelta

from genai_blueprint.utils.streamlit.auto_scroll import scroll_to_here


def get_step_footnote_content(step_log: ActionStep | PlanningStep, step_name: str) -> str:
    """Get a footnote string for a step log with duration and token information"""
    step_footnote = f"**{step_name}**"
    if step_log.token_usage is not None:
        step_footnote += (
            f" | Input tokens: {step_log.token_usage.input_tokens:,} | "
            f"Output tokens: {step_log.token_usage.output_tokens:,}"
        )
    step_footnote += f" | Duration: {round(float(step_log.timing.duration), 2)}s" if step_log.timing.duration else ""
    return step_footnote


def _clean_model_output(model_output: str) -> str:
    """
    Clean up model output by removing trailing tags and extra backticks.

    Args:
        model_output: Raw model output.

    Returns:
        Cleaned model output.
    """

    if not model_output:
        return ""
    model_output = model_output.strip()
    # Remove any trailing <end_code> and extra backticks, handling multiple possible formats
    model_output = re.sub(r"```\s*<end_code>", "```", model_output)  # handles ```<end_code>
    model_output = re.sub(r"<end_code>\s*```", "```", model_output)  # handles <end_code>```
    model_output = re.sub(r"```\s*\n\s*<end_code>", "```", model_output)  # handles ```\n<end_code>
    model_output = re.sub(r"<end_code>", "", model_output)  # remove any remaining <end_code> tags

    # Added to adress formatting code issue
    model_output = re.sub(r"<code>", "```python", model_output)
    model_output = re.sub(r"</code>", "```", model_output)
    return model_output.strip()


def _format_code_content(content: str) -> str:
    """
    Format code content as Python code block if it's not already formatted.

    Args:
        content: Code content to format.

    Returns:
        Code content formatted as a Python code block.
    """
    content = content.strip()
    # Remove existing code blocks and end_code tags
    content = re.sub(r"```.*?\n", "", content)
    content = re.sub(r"\s*<end_code>\s*", "", content)
    content = content.strip()
    # Add Python code block formatting if not already present
    if not content.startswith("```python"):
        content = f"```python\n{content}\n```"
    # Ensure proper code block closure
    if content.count("```") % 2 != 0:
        content += "\n```"
    return content


def _display_step_content(step_log: MemoryStep, display_details: bool = True) -> None:
    """Display content from agent steps in Streamlit

    Args:
        step_log: The memory step to display
        display_details: Whether to show detailed information like code and footnotes
    """
    if isinstance(step_log, ActionStep):
        # Skip model outputs if we're streaming them separately
        if getattr(step_log, "stream_outputs", False) and step_log.model_output:
            return
        step_number = f"Step {step_log.step_number}" if step_log.step_number is not None else "Step"
        st.markdown(f"**{step_number}**")

        if getattr(step_log, "model_output", ""):
            debug(step_log.model_output)
            model_output = _clean_model_output(step_log.model_output)
            st.markdown(model_output)

        if getattr(step_log, "tool_calls", []):
            first_tool_call = step_log.tool_calls[0]
            args = first_tool_call.arguments
            content = str(args.get("answer", str(args))) if isinstance(args, dict) else str(args).strip()

            if first_tool_call.name == "python_interpreter":
                content = _format_code_content(content)
                if display_details:
                    with st.expander(f"🛠️ Used tool {first_tool_call.name}"):
                        st.code(content)

        if getattr(step_log, "observations", "") and step_log.observations.strip():
            log_content = step_log.observations.strip()
            log_content = re.sub(r"^Execution logs:\s*", "", log_content)
            if display_details and log_content:
                with st.expander("📝 Execution Logs", expanded=False):
                    st.code(
                        _clean_model_output(log_content),
                        language="bash",
                        line_numbers=len(log_content.split("\n")) > 1,
                    )

        if getattr(step_log, "error", None):
            st.error(str(step_log.error))

        if getattr(step_log, "observations_images", []):
            for image in step_log.observations_images:
                st.image(AgentImage(image).to_raw())

        if display_details:
            st.caption(get_step_footnote_content(step_log, step_number))
        st.divider()

    elif isinstance(step_log, PlanningStep):
        st.markdown("**Planning step**")
        st.markdown(step_log.plan)
        if display_details:
            st.caption(get_step_footnote_content(step_log, "Planning step"))
        st.divider()

    elif isinstance(step_log, FinalAnswerStep):
        final_answer = step_log.output
        if isinstance(final_answer, AgentText):
            st.markdown(f"**Final answer:**\n{final_answer.to_string()}\n")
        elif isinstance(final_answer, AgentImage):
            st.image(final_answer.to_raw())
        elif isinstance(final_answer, AgentAudio):
            st.audio(final_answer.to_raw())
        else:
            st.markdown(f"**Final answer:** {str(final_answer)}")


def stream_to_streamlit(
    agent: MultiStepAgent,
    task: str,
    task_images: Optional[List[Image.Image]] = None,
    reset_agent_memory: bool = False,
    additional_args: Optional[Dict] = None,
    display_details: bool = True,
    final_answer_handler: Optional[callable] = None,
) -> None:
    """Runs an agent with the given task and streams the messages to Streamlit components.

    Args:
        agent: The MultiStepAgent instance to run
        task: The task prompt for the agent
        task_images: Optional list of PIL images to include with the task
        reset_agent_memory: Whether to reset the agent's memory before running
        additional_args: Additional arguments to pass to the agent's run method
        display_details: Whether to show detailed information like code and footnotes
        final_answer_handler: Optional custom handler for FinalAnswerStep, receives the step as argument
    """
    intermediate_text = ""

    for event in agent.run(
        task, images=task_images, stream=True, reset=reset_agent_memory, additional_args=additional_args
    ):
        if isinstance(event, (ActionStep, PlanningStep, FinalAnswerStep)):
            intermediate_text = ""
            # Use custom handler for FinalAnswerStep if provided
            if isinstance(event, FinalAnswerStep) and final_answer_handler is not None:
                final_answer_handler(event)
            else:
                _display_step_content(event, display_details)
            scroll_to_here()
        elif isinstance(event, ChatMessageStreamDelta):
            if event.content:
                intermediate_text += event.content
                st.markdown(intermediate_text)
                scroll_to_here()
