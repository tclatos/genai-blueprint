import math

from genai_tk.core.llm_factory import get_llm
from langchain.agents import create_agent
from langchain_core.tools import tool

llm = get_llm("gpt_4o_azure")


@tool
def add(a: int, b: int) -> int:
    """Adds a and b.

    Args:
        a: first int
        b: second int
    """
    return a + b


@tool
def exponentiate(x: float, y: float) -> float:
    """Calculate the power of a number. Return x**y (w to the power of y)."""
    print("exponentiate")
    return math.pow(x, y)


tools = [add, exponentiate]
agent = create_agent(model=llm, tools=tools, system_prompt=prompt)  # type: ignore

QUERY = "what is 12  + 100^3"

r = agent.invoke({"messages": [{"role": "user", "content": QUERY}]})
print(r)
