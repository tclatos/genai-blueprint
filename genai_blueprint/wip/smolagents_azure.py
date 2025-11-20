from genai_tk.core.llm_factory import LlmFactory
from smolagents import (
    CodeAgent,
    WebSearchTool,
)

llm_factory = LlmFactory(llm="azure", llm_params={"temperature": 0.7})
llm = llm_factory.get_smolagent_model()
print(f"Using model: {llm_factory.get_id()}")
agent = CodeAgent(tools=[WebSearchTool()], model=llm)
agent.run("How many seconds would it take for a lion at full speed to run through Pont des Arts?")
