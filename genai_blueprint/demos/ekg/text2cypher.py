import pandas as pd
from genai_tk.core.llm_factory import get_llm
from genai_tk.core.prompts import def_prompt
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable, RunnableLambda
from loguru import logger

from genai_blueprint.demos.ekg.graph_backend import create_backend_from_config
from genai_blueprint.demos.ekg.schema_doc_generator import generate_schema_markdown

SYSTEM_PROMPT = """  
    Translate the given question into a valid Cypher query that respects the given graph schema.
    <SYNTAX>
    - Relationship directions are VERY important to the success of a query. Here's an example: If
    the relationship `HAS_CREATOR` is marked as `from` A `to` B, it means that B created A.
    - Use short, concise alphanumeric strings as names of variable bindings (e.g., `a1`, `r1`, etc.)    
    - When comparing string properties, ALWAYS do the following:
      - Lowercase the property values before comparison
      - Use the WHERE clause
      - Use the CONTAINS operator to check for presence of one substring in the other
    - DO NOT use APOC as the database does not support it.
    - For datetime queries, use the TIMESTAMP type, which combines the date and time.
    </SYNTAX>

    <RETURN_RESULTS>
    - If the result is an integer, return it as an integer (not a string).
    - When returning results, return property values rather than the entire node or relationship.
    - Do not attempt to coerce data types to number formats (e.g., integer, float) in your results.
    - NO Cypher keywords should be returned by your query.
    </RETURN_RESULTS> """

USER_PROMPT = """
    <QUESTION>
    {question}
    </QUESTION>

    <SCHEMA>
    {schema}
    </SCHEMA>

    <OUTPUT>: 
    Valid Cypher query with no newlines: 
"""


def text2cypher_chain(question: str, subgraph: str, llm_id: str | None = None) -> Runnable:
    """Generate system and user prompts for text to Cypher conversion.

    Args:
        question: The user's question in natural language.
        subgraph: The graph schema type
    """
    prompt = {
        "question": RunnableLambda(lambda x: question),
        "schema": RunnableLambda(lambda x: generate_schema_markdown(subgraph)),
    } | def_prompt(system=SYSTEM_PROMPT, user=USER_PROMPT)
    return prompt | get_llm(llm_id=llm_id) | StrOutputParser()


def query_kg(query: str, subgraph: str, llm_id: str | None = None) -> pd.DataFrame:
    """Generate a Cypher query from a natural language query and execute it against the knowledge graph.

    Args:
        query: The user's question in natural language.
        subgraph: The graph schema type
    """
    backend = create_backend_from_config("default")
    if not backend:
        raise Exception("EKG database not found")
    cypher_query = text2cypher_chain(query, subgraph, llm_id=llm_id).invoke({})
    logger.info(f"Generated Cypher query: {cypher_query}")
    result = backend.execute(cypher_query)
    df = result.get_as_df()
    return df


if __name__ == "__main__":
    # Quick test
    query = "List the names of all competitors for opportunities created after January 1, 2012."
    df = query_kg(query, subgraph="ReviewedOpportunity", llm_id=None)
    print(df)
