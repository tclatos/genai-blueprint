import streamlit as st
from genai_tk.core.llm_factory import LlmFactory
from smolagents import (
    CodeAgent,
    LiteLLMModel,
    VisitWebpageTool,
    WebSearchTool,
)

from genai_blueprint.webapp.ui_components.smolagents_streamlit import stream_to_streamlit

# MODEL_ID = "gpt_4o_azure"
MODEL_ID = None


# SmolagentsInstrumentor().instrument(tracer_provider=get_telemetry_trace_provider())

SAMPLE_PROMPTS = [
    "How many seconds would it take for a leopard at full speed to run through Pont des Arts?",
    "If the US keeps its 2024 growth rate, how many years will it take for the GDP to double?",
    "Which Dutch player scored an open-play goal in the 2022 Netherlands vs Argentina game in the men’s FIFA World Cup?",
]


model_name = LlmFactory(llm=MODEL_ID).get_litellm_model_name()
llm = LiteLLMModel(model_id=model_name)
print(model_name)


with st.expander(label="Prompt examples", expanded=True):
    st.write(SAMPLE_PROMPTS)


# Input for new messages
if prompt := st.chat_input("What would you like to ask SmolAgents?"):
    agent = CodeAgent(tools=[WebSearchTool(), VisitWebpageTool()], model=llm)
    with st.container(height=600):
        stream_to_streamlit(agent, prompt)
