"""Taken from :    https://learn.deeplearning.ai/courses/ai-agents-in-langgraph/lesson/7/essay-writer
Full source code with UI is here : https://s172-31-15-23p21826.lab-aws-production.deeplearning.ai/edit/helper.py.

Also of interest: https://github.com/langchain-ai/langgraph/blob/main/examples/multi_agent/multi-agent-collaboration.ipynb
"""

import os
import sys
from operator import itemgetter
from typing import Literal, TypedDict

from genai_tk.core.chain_registry import Example, RunnableItem, register_runnable
from genai_tk.core.llm_factory import get_llm
from genai_tk.core.prompts import def_prompt
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import (
    RunnableConfig,
    RunnablePassthrough,
)
from langgraph.graph import END, StateGraph
from loguru import logger
from pydantic import BaseModel
from tavily import TavilyClient


class AgentState(TypedDict, total=False):
    task: str
    plan: str
    draft: str
    critique: str
    content: list[str]
    revision_number: int
    max_revisions: int


class Queries(BaseModel):
    queries: list[str]


LLM_ID = "gpt_4omini_edenai"
# LLM_ID = "gpt_4_azure"
LLM_ID = "gpt_4o_azure"

llm = get_llm(llm_id=LLM_ID, temperature=0.0)

tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


def plan_node(state: AgentState) -> AgentState:
    PLAN_PROMPT = """
        You are an expert writer tasked with writing a high level outline of an essay.
        Write such an outline for the user provided topic. Give an outline of the essay along with any relevant notes
        or instructions for the sections."""

    chain = def_prompt(system=PLAN_PROMPT, user=state["task"]) | llm | StrOutputParser()
    plan = chain.invoke({})
    print(plan)
    return {"plan": plan}


def research_plan_node(state: AgentState):
    RESEARCH_PLAN_PROMPT = """
        You are a researcher charged with providing information that can
        be used when writing the following essay. Generate a list of search queries that will gather
        any relevant information. Only generate 3 queries max."""

    chain = def_prompt(system=RESEARCH_PLAN_PROMPT, user=state["task"]) | llm.with_structured_output(Queries)
    queries = chain.invoke({})
    content = state["content"] or []
    for q in queries.queries:
        response = tavily.search(query=q, max_results=2)
        assert response
        for r in response["results"]:
            content.append(r["content"])
    print(content)
    return {"content": content}


def generation_node(state: AgentState) -> AgentState:
    WRITER_PROMPT = """
        You are an essay assistant tasked with writing excellent 5-paragraph essays.
        Generate the best essay possible for the user's request and the initial outline.
        If the user provides critique, respond with a revised version of your previous attempts.
        Utilize all the information below as needed:
        ------
        {content}"""

    content = "\n\n".join(state["content"] or [])
    chain = (
        def_prompt(
            system=WRITER_PROMPT,
            user=f"{state['task']}\n\nHere is my plan:\n\n{state['plan']}",
        )
        | llm
        | StrOutputParser()
    )

    best_essay = chain.invoke({"content": content})
    print(best_essay)
    return {
        "draft": best_essay,
        "revision_number": state.get("revision_number", 1) + 1,
    }


def reflection_node(state: AgentState) -> AgentState:
    REFLECTION_PROMPT = """
        You are a teacher grading an essay submission.
        Generate critique and recommendations for the user's submission.
        Provide detailed recommendations, including requests for length, depth, style, etc."""

    chain = def_prompt(system=REFLECTION_PROMPT, user=state["draft"]) | llm | StrOutputParser()
    return {"critique": chain.invoke({})}


def research_critique_node(state: AgentState) -> AgentState:
    RESEARCH_CRITIQUE_PROMPT = """
        You are a researcher charged with providing information that can
        be used when making any requested revisions (as outlined below).
        Generate a list of search queries that will gather any relevant information. Only generate 3 queries max."""

    chain = def_prompt(system=RESEARCH_CRITIQUE_PROMPT, user=state["task"]) | llm.with_structured_output(Queries)
    queries = chain.invoke({})

    content = state["content"] or []
    for q in queries.queries:
        response = tavily.search(query=q, max_results=2)
        for r in response["results"]:
            content.append(r["content"])
    return {"content": content}


def should_continue(state: AgentState) -> Literal["reflect", "__end__"]:
    if state["revision_number"] > state["max_revisions"]:
        return END
    else:
        return "reflect"


def create_graph():
    builder = StateGraph(AgentState)
    builder.add_node("planner", plan_node)
    builder.add_node("generate", generation_node)
    builder.add_node("reflect", reflection_node)
    builder.add_node("research_plan", research_plan_node)
    builder.add_node("research_critique", research_critique_node)

    builder.set_entry_point("planner")
    builder.add_conditional_edges("generate", should_continue, {END: END, "reflect": "reflect"})

    builder.add_edge("planner", "research_plan")
    builder.add_edge("research_plan", "generate")
    builder.add_edge("reflect", "research_critique")
    builder.add_edge("research_critique", "generate")

    # memory = SqliteSaver.from_conn_string(":memory:")
    memory = None
    graph = builder.compile(checkpointer=memory, interrupt_after=None)
    return graph


def query_graph(config: dict):
    # chain = RunnablePassthrough.assign()

    chain = (
        RunnablePassthrough.assign(max_revisions=lambda x: 2, revision_number=lambda x: 1)
        | create_graph()
        | itemgetter("draft")
    )
    return chain


register_runnable(
    RunnableItem(
        tag="essay-writer-agent",
        name="essay-writer-agent",
        runnable=("task", query_graph),
        examples=[
            Example(
                query=[
                    "what is the difference between Quantization and Finetuning?",
                    "what is the difference between langchain and langsmith",
                ]
            )
        ],
        diagram="genai_blueprint/webapp/static/essay_writer_agent_screenshot.png",
    )
)


def test() -> None:
    graph = create_graph()
    thread = RunnableConfig({"configurable": {"thread_id": "1"}})
    for s in graph.stream(
        {
            "task": "what is the difference between Quantization and Finetuning?",
            "max_revisions": 2,
            "revision_number": 1,
        },
        thread,
    ):
        print(s)


if __name__ == "__main__":
    from langchain_core.globals set_debug, set_verbose

    set_debug(True)
    set_verbose(True)
    logger.remove()
    logger.add(
        sys.stderr,
        format="<blue>{level}</blue> | <green>{message}</green>",
        colorize=True,
    )
    test()
    # test_graph()
