"""
Deep Research Agent Example

This module demonstrates how to use the deepagents integration to create
a powerful research agent that can conduct comprehensive research on any topic.
"""

import asyncio
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from genai_tk.core.deep_agents import DeepAgentConfig, deep_agent_factory, run_deep_agent
from genai_tk.tools.langchain.web_search_tool import basic_web_search
from langchain.tools import tool
from loguru import logger
from tavily import TavilyClient

load_dotenv()


class ResearchAgentExample:
    """Example implementation of a deep research agent"""

    def __init__(self, tavily_api_key: Optional[str] = None):
        """
        Initialize the research agent example.

        Args:
            tavily_api_key: Tavily API key for web search
        """
        self.tavily_api_key = tavily_api_key or os.environ.get("TAVILY_API_KEY")
        if not self.tavily_api_key:
            logger.warning("No Tavily API key provided. Web search will not be available.")

        self.agent = None
        self.tavily_client = None

    def _create_search_tool(self):
        """Create the web search tool"""
        if not self.tavily_api_key:
            return basic_web_search

        # Create real Tavily search tool
        self.tavily_client = TavilyClient(api_key=self.tavily_api_key)

        @tool
        def internet_search(query: str, max_results: int = 5, include_raw_content: bool = False) -> Dict[str, Any]:
            """
            Run a web search using Tavily.

            Args:
                query: Search query
                max_results: Maximum number of results
                include_raw_content: Whether to include raw content

            Returns:
                Search results
            """
            try:
                results = self.tavily_client.search(
                    query, max_results=max_results, include_raw_content=include_raw_content
                )
                return results
            except Exception as e:
                logger.error("Search error: {}", e)
                return {"error": str(e), "results": []}

        return internet_search

    def _create_additional_tools(self):
        """Create additional research tools"""

        @tool
        def summarize_text(text: str, max_length: int = 500) -> str:
            """
            Summarize a piece of text.

            Args:
                text: Text to summarize
                max_length: Maximum length of summary

            Returns:
                Summarized text
            """
            # Simple truncation for demo - in production, use LLM
            if len(text) <= max_length:
                return text
            return text[:max_length] + "..."

        @tool
        def extract_key_points(text: str) -> list:
            """
            Extract key points from text.

            Args:
                text: Text to analyze

            Returns:
                List of key points
            """
            # Simple implementation - in production, use NLP
            lines = text.split("\n")
            key_points = [line.strip() for line in lines if line.strip() and len(line.strip()) > 20]
            return key_points[:10]  # Return top 10 points

        @tool
        def create_citation(title: str, author: str = "Unknown", url: str = "", year: str = "2024") -> str:
            """
            Create a formatted citation.

            Args:
                title: Title of the source
                author: Author name
                url: Source URL
                year: Publication year

            Returns:
                Formatted citation
            """
            citation = f"{author} ({year}). {title}."
            if url:
                citation += f" Retrieved from {url}"
            return citation

        return [summarize_text, extract_key_points, create_citation]

    def create_agent(self, custom_instructions: Optional[str] = None):
        """
        Create the research agent.

        Args:
            custom_instructions: Optional custom instructions for the agent

        Returns:
            The created agent
        """
        search_tool = self._create_search_tool()
        additional_tools = self._create_additional_tools()

        instructions = (
            custom_instructions
            or """You are an expert researcher specializing in comprehensive, accurate research.

## Your Research Process:

1. **Understanding**: First, clearly understand what needs to be researched
2. **Planning**: Create a detailed research plan using the planning tool
3. **Searching**: Use the search tool to find relevant information
4. **Analysis**: Analyze and synthesize the information found
5. **Note-taking**: Create organized notes in the file system
6. **Citation**: Properly cite all sources using the citation tool
7. **Reporting**: Write a comprehensive, well-structured report

## Guidelines:

- Be thorough and explore multiple perspectives
- Verify information from multiple sources when possible
- Clearly distinguish between facts and opinions
- Use the file system to organize your research materials
- Create intermediate notes and drafts
- Always cite your sources properly
- Structure your final report with clear sections

## Output Format:

Your final report should include:
1. Executive Summary
2. Introduction
3. Main Findings (organized by theme)
4. Analysis and Insights
5. Conclusion
6. References
"""
        )

        # Create agent using the factory
        self.agent = deep_agent_factory.create_research_agent(
            search_tool=search_tool, name="Expert Research Agent", additional_tools=additional_tools, async_mode=True
        )

        # Update the instructions if custom ones provided
        if custom_instructions:
            config = DeepAgentConfig(
                name="Expert Research Agent", instructions=instructions, enable_file_system=True, enable_planning=True
            )
            self.agent = deep_agent_factory.create_agent(
                config=config, tools=[search_tool] + additional_tools, async_mode=True
            )

        logger.info("Research agent created successfully")
        return self.agent

    async def research_topic(
        self, topic: str, depth: str = "moderate", focus_areas: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Research a specific topic.

        Args:
            topic: The topic to research
            depth: Research depth (quick, moderate, comprehensive)
            focus_areas: Optional specific areas to focus on

        Returns:
            Research results
        """
        if not self.agent:
            self.create_agent()

        # Prepare the research query
        query = f"Research the topic: {topic}\n\n"

        if depth == "quick":
            query += "Provide a quick overview with key points.\n"
        elif depth == "comprehensive":
            query += "Conduct comprehensive, in-depth research with multiple sources.\n"
        else:
            query += "Conduct moderate-depth research with good coverage.\n"

        if focus_areas:
            query += "\nFocus particularly on these areas:\n"
            for area in focus_areas:
                query += f"- {area}\n"

        # Run the research
        messages = [{"role": "user", "content": query}]

        logger.info("Starting research on topic: {}", topic)
        result = await run_deep_agent(agent=self.agent, messages=messages, stream=False)

        logger.info("Research completed")
        return result

    async def research_with_context(
        self, topic: str, context_files: Dict[str, str], additional_questions: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Research a topic with additional context files.

        Args:
            topic: The topic to research
            context_files: Dictionary of file names to content
            additional_questions: Optional specific questions to answer

        Returns:
            Research results
        """
        if not self.agent:
            self.create_agent()

        query = f"Research the topic: {topic}\n\n"
        query += "You have been provided with some context files. Review them first.\n\n"

        if additional_questions:
            query += "Please specifically address these questions:\n"
            for q in additional_questions:
                query += f"- {q}\n"

        messages = [{"role": "user", "content": query}]

        logger.info("Starting contextual research on topic: {}", topic)
        result = await run_deep_agent(agent=self.agent, messages=messages, files=context_files, stream=False)

        logger.info("Contextual research completed")
        return result


async def main():
    """Main function demonstrating the research agent"""

    # Create the research agent example
    researcher = ResearchAgentExample()

    # Example 1: Quick research
    print("\n" + "=" * 50)
    print("Example 1: Quick Research on LangGraph")
    print("=" * 50)

    result = await researcher.research_topic(topic="LangGraph framework for building AI agents", depth="quick")

    if "messages" in result:
        print(result["messages"][-1].content)
    else:
        print(result)

    # Example 2: Focused research
    print("\n" + "=" * 50)
    print("Example 2: Focused Research on Deep Learning")
    print("=" * 50)

    result = await researcher.research_topic(
        topic="Transformer architecture in deep learning",
        depth="moderate",
        focus_areas=["Self-attention mechanism", "Positional encoding", "Applications in NLP"],
    )

    if "messages" in result:
        print(result["messages"][-1].content)

    # Example 3: Research with context
    print("\n" + "=" * 50)
    print("Example 3: Research with Context")
    print("=" * 50)

    context_files = {
        "project_requirements.txt": """Project: AI-Powered Research Assistant
        
Requirements:
- Must handle multiple research sources
- Should provide citations
- Need to organize information hierarchically
- Must support both quick and deep research modes
""",
        "technical_specs.txt": """Technical Specifications:
        
- Python 3.12+
- LangChain/LangGraph integration
- Support for multiple LLM providers
- Async operation support
""",
    }

    result = await researcher.research_with_context(
        topic="Best practices for building AI research assistants",
        context_files=context_files,
        additional_questions=[
            "What are the key architectural patterns?",
            "How to handle source reliability?",
            "What are common pitfalls to avoid?",
        ],
    )

    if "messages" in result:
        print(result["messages"][-1].content)

    # Show any files created during research
    if "files" in result:
        print("\n" + "=" * 50)
        print("Files Created During Research:")
        print("=" * 50)
        for filename, content in result["files"].items():
            print(f"\n📄 {filename}:")
            print(content[:500] + "..." if len(content) > 500 else content)


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())
