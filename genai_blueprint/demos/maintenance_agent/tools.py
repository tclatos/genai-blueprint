"""Tools for Maintenance Agent.

This module provides tools for maintenance operations including:
- Maintenance procedure retrieval
- Planning database queries
- Tool availability and location checks
- Sensor data access
- Maintenance history retrieval

These tools can be used with a ReAct agent to create a comprehensive
maintenance assistant.
"""

from functools import cache
from pathlib import Path
from textwrap import dedent

import streamlit as st
from genai_tk.core.embeddings_store import EmbeddingsStore
from genai_tk.core.llm_factory import get_llm
from genai_tk.core.prompts import dedent_ws, def_prompt
from genai_tk.tools.langchain.sql_tool_factory import SQLToolConfig, SQLToolFactory
from genai_tk.utils.config_mngr import global_config
from langchain.tools import BaseTool, tool
from langchain_classic.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_community.utilities import SQLDatabase
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.vectorstores.base import VectorStore
from loguru import logger

from genai_blueprint.demos.maintenance_agent.dummy_data import dummy_database

# Tools setup
PROCEDURES = [
    "procedure_turbine.txt",
    "procedure_generator.txt",
    "procedure_cooling_system.txt",
]

DATA_PATH = Path(global_config().get_str("documents.base")) / "maintenance"

VECTOR_STORE_ID = "InMemory"


@st.cache_resource(show_spinner=True)
def maintenance_procedure_vectors(text: str) -> VectorStore:
    """Create vector store from maintenance procedure documents.

    Args:
        text: Name of the text file containing maintenance procedures

    Returns:
        VectorStore: Configured vector store with indexed documents

    The procedure documents are:
    1. Loaded from the specified text file
    2. Split into chunks for efficient retrieval
    3. Embedded using configured embeddings
    4. Stored in the vector store
    """
    embeddings_store = EmbeddingsStore.create_from_config("in_memory")

    loader = TextLoader(str(DATA_PATH / text))
    documents = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
    texts = text_splitter.split_documents(documents)
    embeddings_store.add_documents(texts)
    return embeddings_store.get()


examples = [
    {
        "input": "Tasks assigned to employee 'employee_name' between '2023-10-22' and '2023-10-28'.",
        "query": """SELECT task FROM "tasks" WHERE employee = 'employee_name' AND start_date > '2023-10-22' and end_date  < '2023-10-28';""",
    },
    {
        "input": "List of procedures that employee 'employee_name' knows. ",
        "query": "SELECT  DISTINCT employee, procedure FROM tasks WHERE employee = 'employee_name';",
    },
]


@cache
def create_maintenance_tools() -> list[BaseTool]:
    """Create and configure the tools for the Maintenance Agent.

    Returns:
        list[BaseTool]: List of configured tools including:
            - Planning info retrieval: Query task assignments and schedules
            - Maintenance times: Access historical maintenance timings
            - Maintenance issues: Retrieve past maintenance problems
            - Procedure retrieval: Search maintenance procedures
            - ERP system queries: Check tool availability and locations
            - Sensor data: Access historical sensor readings

    Each tool is implemented as a LangChain tool with appropriate
    descriptions and functionality for maintenance operations.
    """
    logger.info("create tools")

    # Create planning info tool using the factory constructor
    config = SQLToolConfig(
        database_uri=dummy_database(),
        tool_name="get_planning_info",
        tool_description="Useful for when you need to answer questions about tasks assigned to employees.",
        examples=examples[:5],
    )
    factory = SQLToolFactory(get_llm())
    get_planning_info = factory.create_tool(config)

    @tool
    def get_maintenance_times(area: str) -> str:
        """Useful to searches the list of previous maintenance time for the given area."""
        result = """
        -29/05/2018  13:45
        -16/05/2019  10:00
        -22/07/2020  9:45
        """
        return dedent_ws(result)

    @tool
    def get_maintenance_issues(area: str, time: str) -> str:
        """Searches for the issues during the maintenance of a given area at a given time."""
        result = f"""
        Big big problem in area {area} at {time}
        """
        return dedent(result)

    @tool
    def maintenance_procedure_retriever(full_query: str) -> str:
        """Answer to any questions about maintenance procedures, such as tasks, prerequisite, spare parts, required tools etc."""
        system_prompt = (
            "Use the given context to answer the question. If you don't know the answer, say you don't know. "
            "Use three sentence maximum and keep the answer concise. \n"
            "Context: {context}"
        )
        prompt = def_prompt(system_prompt, "{input}")
        retriever = maintenance_procedure_vectors(PROCEDURES[0]).as_retriever()
        llm = get_llm()
        chain = {"context": retriever, "input": RunnablePassthrough()} | prompt | llm | StrOutputParser()
        return chain.invoke(full_query)

    @tool
    def get_info_from_erp(tools_name: list[str], time: str) -> str:
        """Useful to answer questions about tools, such as availability, localization, ..."""
        result = ""
        for too_name in tools_name:
            availability = too_name[0].lower() < "r"
            hash = str(too_name.__hash__())
            localization = f"R{hash[1:3]}L{hash[3:7]}"
            result += f"{too_name}:\n\t- availability: {availability} \n\t- localization:{localization}\n"
        return result

    @tool
    def get_sensor_values(sensor_name: list[str], start_time: str, end_time: str) -> str:
        """Useful to know the values of a given sensor during a time range."""
        print(sensor_name, start_time, end_time)
        ls = ",".join([f"'{n}'" for n in sensor_name])
        db = SQLDatabase.from_uri(dummy_database())
        sql = f"""SELECT date, sensor, value, unit FROM  sensor_data
                  WHERE  sensor IN ({ls}) and date >= '{start_time}' and date <= '{end_time}'"""
        print(sql)
        result = db.run(sql)
        return str(result)

    return [
        get_maintenance_times,
        get_maintenance_issues,
        get_planning_info,
        maintenance_procedure_retriever,
        get_info_from_erp,
        get_sensor_values,
    ]
