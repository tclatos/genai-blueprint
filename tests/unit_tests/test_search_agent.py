"""
Test script to verify Deep Agent with real search works
"""

import asyncio
import os

from genai_tk.ai_core.deep_agents import DeepAgentFactory, run_deep_agent
from genai_tk.ai_core.search_tools import create_search_tool
from langchain_openai import ChatOpenAI


async def test_research_agent():
    """Test the research agent with real search"""

    # Create factory
    factory = DeepAgentFactory()

    # Check if we have OpenAI API key
    openai_key = os.environ.get("OPENAI_API_KEY")

    if openai_key:
        print("Using OpenAI GPT-4o-mini")
        model = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, api_key=openai_key)
        factory.set_default_model(model)
    else:
        print("Warning: No OpenAI API key found. Using mock model for testing.")
        # Create a simple mock model that doesn't require API keys
        from typing import Any, List, Optional

        from langchain_core.language_models.base import LanguageModelInput
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, ChatResult

        class MockChatModel(BaseChatModel):
            """Mock model for testing"""

            @property
            def _llm_type(self) -> str:
                return "mock"

            def _generate(
                self, messages: LanguageModelInput, stop: Optional[List[str]] = None, **kwargs: Any
            ) -> ChatResult:
                # Simple mock response
                response = AIMessage(content="I'll search for information about Atos.")
                return ChatResult(generations=[ChatGeneration(message=response)])

            async def _agenerate(
                self, messages: LanguageModelInput, stop: Optional[List[str]] = None, **kwargs: Any
            ) -> ChatResult:
                return self._generate(messages, stop, **kwargs)

        model = MockChatModel()
        factory.set_default_model(model)

    # Create search tool (will use Tavily since API key is available)
    search_tool = create_search_tool(verbose=True)

    # Test the search tool directly first
    print("\nTesting search tool directly...")
    search_result = search_tool.invoke({"query": "Atos news September 2025", "search_type": "news"})
    print(f"Search result preview: {search_result[:500]}...\n")

    # Create research agent
    print("Creating research agent...")
    agent = factory.create_research_agent(search_tool=search_tool, name="Test Research Agent", async_mode=True)

    # Run the agent
    print("Running agent with query...")
    messages = [{"role": "user", "content": "Find recent news about Atos in September 2025"}]

    try:
        result = await run_deep_agent(agent=agent, messages=messages, stream=False)

        print("\nAgent Response:")
        if "messages" in result and result["messages"]:
            print(result["messages"][-1].content)
        else:
            print("No response from agent")

    except Exception as e:
        print(f"Error running agent: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_research_agent())
