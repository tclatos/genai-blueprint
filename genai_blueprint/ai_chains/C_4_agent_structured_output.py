# https://langchain-ai.github.io/langgraph/how-tos/react-agent-structured-output/#define-graph

from typing import Literal

from genai_tk.core.llm_factory import get_llm, llm_config
from genai_tk.extra.graphs.react_agent_structured_output import create_react_structured_output_graph
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class WeatherResponse(BaseModel):
    """Respond to the user with this."""

    temperature: float = Field(description="The temperature in fahrenheit")
    wind_direction: str = Field(description="The direction of the wind in abbreviated form")
    wind_speed: float = Field(description="The speed of the wind in km/h")


@tool
def get_weather(city: Literal["nyc", "sf"]) -> str:
    """Use this to get weather information."""
    if city == "nyc":
        return "It is cloudy in NYC, with 10 mph winds in the North-East direction and a temperature of 66 degrees"
    elif city == "sf":
        return "It is 75 degrees and sunny in SF, with 3 mph winds in the South-East direction"
    else:
        raise AssertionError("Unknown city")


# @chain
def get_weather_fn(query: str, config: RunnableConfig) -> WeatherResponse:
    llm_id = config["configurable"].get("llm_id")
    llm = get_llm(llm=llm_id)
    graph = create_react_structured_output_graph(llm, [get_weather], WeatherResponse)
    graph_input = {"messages": [("human", query)]}
    result = graph.invoke(graph_input)
    return result["final_response"]


MODEL = "claude_haiku45_openrouter"  # Work
MODEL = "nvidia_nemotron70_openrouter"  # Do NOT work
MODEL = "gpt_4o_azure"  # Work
MODEL = "google_gemini3flash_openrouter"  # Updated to Gemini 3 (Flash)
MODEL = "qwen2_vl72_openrouter"  # Do NOT work
MODEL = "gpt_4omini_edenai"  # ?
MODEL = "falcon3_3_ollama"  # Do NOT work
MODEL = "mistral_nemo_openrouter"  # Work
MODEL = "google_gemini3pro_openrouter"  # Updated to Gemini 3 (Pro)

get_weather_chain = RunnableLambda(get_weather_fn).with_config(llm_config(MODEL) | {"recursion_limit": 6})
answer = get_weather_chain.invoke("what's the weather in New York?")

print(answer)
debug(answer)
