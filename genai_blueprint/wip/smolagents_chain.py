"""Wrappers to facilitate SmallAgents and LangChain integration."""

from genai_tk.core.llm_factory import LlmFactory
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda
from smolagents import CodeAgent, LiteLLMModel, MultiStepAgent, Tool


def get_model_from_factory(llm_factory: LlmFactory) -> LiteLLMModel:
    return LiteLLMModel(model_id=llm_factory.get_litellm_model_name(), **llm_factory.llm_params)


def smallagents_chain(agent: MultiStepAgent) -> RunnableLambda:
    # TODO : pass optional parameters ?
    return RunnableLambda(func=agent.run)


# Create RetrieverTool
class RetrieverTool(Tool):
    name = "retriever"
    description = "Uses semantic search to retrieve relevant documentation"
    inputs = {
        "query": {
            "type": "string",
            "description": "The query to perform. This should be semantically close to your target documents. Use the affirmative form rather than a question.",
        }
    }
    output_type = "string"

    def __init__(self, retriever: BaseRetriever, **kwargs) -> None:
        super().__init__(**kwargs)
        self.retriever = retriever

    def forward(self, query: str) -> str:  # type: ignore
        assert isinstance(query, str), "Your search query must be a string"
        docs = self.retriever.invoke(query)
        return "\nRetrieved documents:\n" + "".join(
            f"\n\n===== Document {i} =====\n{doc.page_content}" for i, doc in enumerate(docs)
        )


# Quick test
if __name__ == "__main__":
    from smolagents import WebSearchTool

    MODEL_ID = "gpt_4omini_openai"
    llm_factory = LlmFactory(llm=MODEL_ID, llm_params={"temperature": 0.7})

    agent = CodeAgent(tools=[WebSearchTool()], model=get_model_from_factory(llm_factory))

    r = smallagents_chain(agent).invoke(
        "How many seconds would it take for a leopard at full speed to run through Pont des Arts?"
    )
    print(r)
