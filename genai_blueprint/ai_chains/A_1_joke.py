"""The usual "tell me a joke" LLM call."""

from dotenv import load_dotenv
from genai_blueprint.chain_registry import (
    Example,
    RunnableItem,
    register_runnable,
)
from genai_tk.core.factories.llm_factory import get_llm_unified
from genai_tk.core.prompts import def_prompt
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda, RunnablePassthrough

load_dotenv(verbose=True)


def get_llm_from_config(topic: str, config: RunnableConfig) -> str:
    """Get LLM from runtime configuration and invoke it."""
    # Extract configuration from the runtime config
    configurable = config.get("configurable", {})
    llm_id = configurable.get("llm")
    llm_args = configurable.get("llm_args", {})

    # Extract reasoning parameter if provided
    reasoning = llm_args.get("reasoning", None)
    temperature = llm_args.get("temperature", 0.0)

    # Get configured LLM
    llm = get_llm_unified(llm=llm_id, reasoning=reasoning, temperature=temperature)

    # Create the prompt and invoke the LLM
    simple_prompt = """Tell me a joke on {topic}"""
    prompt = def_prompt(user=simple_prompt)

    # Format the prompt with the topic
    formatted_prompt = prompt.format(topic=topic)

    # Invoke LLM and return result
    result = llm.invoke(formatted_prompt)
    return result.content if hasattr(result, "content") else str(result)


def get_chain(config: dict) -> Runnable:
    """Create the joke chain with runtime configuration support."""
    # Create a runnable lambda that can access runtime config
    llm_runnable = RunnableLambda(get_llm_from_config)

    chain = {"topic": RunnablePassthrough()} | llm_runnable
    return chain


# Register the chain
register_runnable(
    RunnableItem(
        tag="Agent",
        name="Joke",
        runnable=get_chain,
        examples=[Example(query=["Beaver"])],
    )
)
