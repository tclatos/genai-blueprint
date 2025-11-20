"""Adapted from https://blog.langchain.dev/tool-calling-with-langchain/."""

from operator import itemgetter

from genai_tk.core.chain_registry import (
    Example,
    RunnableItem,
    register_runnable,
)
from genai_tk.core.llm_factory import get_llm
from langchain.agents import AgentExecutor, create_tool_calling_agent, tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable


@tool
def multiply(x: float, y: float) -> float:
    """Multiply 'x' times 'y'."""
    return x * y


@tool
def exponentiate(x: float, y: float) -> float:
    """Raise 'x' to the 'y'."""
    return x**y


@tool
def add(x: float, y: float) -> float:
    """Add 'x' and 'y'."""
    return x + y


# tavily_tool = TavilySearchResults(max_results=5)

# tools = [multiply, exponentiate, add, tavily_tool]
tools = [multiply, exponentiate, add]


# Whenever we invoke `llm_with_tool`, all three of these tool definitions
# are passed to the model.


def create_runnable(config: dict) -> Runnable:
    llm = get_llm(llm=config["llm"])
    return llm.bind_tools(tools)


register_runnable(
    RunnableItem(
        tag="Tool",
        name="Calculator tool",
        runnable=create_runnable,
        examples=[Example(query=["what's 5 raised to the 3"])],
    )
)


def create_executor(config: dict) -> Runnable:
    llm_id = config["llm"]
    llm = get_llm(llm=llm_id)
    # info = get_llm_info(llm_id)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You are a helpful Search Assistant"),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )

    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    return agent_executor | itemgetter("output")


register_runnable(
    RunnableItem(
        tag="Agent",
        name="Calculator agent",
        runnable=("input", create_executor),
        examples=[Example(query=["what's 3 plus 5 raised to the 2.743. also what's 17.24 - 918.1241"])],
    )
)
