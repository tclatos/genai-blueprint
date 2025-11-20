"""Streamlit page for Graph RAG demo with Kuzu.

Provides an interactive interface to build and query knowledge graphs from text.
Supports configurable node types, relationship types, and demo presets.
"""

from typing import List

import kuzu
import streamlit as st
from devtools import debug
from genai_tk.core.llm_factory import get_llm
from genai_tk.utils.config_mngr import global_config
from langchain_core.documents import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_kuzu.chains.graph_qa.kuzu import KuzuQAChain
from langchain_kuzu.graphs.kuzu_graph import KuzuGraph
from loguru import logger
from pydantic import BaseModel, ConfigDict
from st_cytoscape import cytoscape
from streamlit import session_state as sss

from genai_blueprint.webapp.ui_components.cypher_graph_display import get_cytoscape_json, get_cytoscape_style


# Define demo class
class GraphRagDemo(BaseModel):
    """Configuration for a Graph RAG demo preset.

    Attributes:
        name: Unique demo name
        text: Sample text to analyze
        allowed_nodes: List of node types to extract
        allowed_relationships: List of relationship types to extract
        example_queries: Example queries for the demo
    """

    name: str
    text: str
    allowed_nodes: List[str]
    allowed_relationships: List[tuple[str, str, str]]
    example_queries: List[str] = []
    model_config = ConfigDict(arbitrary_types_allowed=True)


def load_demos_from_config() -> List[GraphRagDemo]:
    """Load demo configurations from global config.

    Returns:
        List of GraphRagDemo instances loaded from config
    """
    try:
        demos_config = global_config().merge_with("config/demos/graph_rag.yaml").get_list("graph_rag_demos")
        result = []
        # Create Demo objects from the configuration
        for demo_config in demos_config:
            name = demo_config.get("name", "")
            text = demo_config.get("text", "")
            allowed_nodes = demo_config.get("allowed_nodes", [])
            relationships_raw = demo_config.get("allowed_relationships", [])

            # Convert relationships to proper 3-item tuples
            allowed_relationships = []
            for rel in relationships_raw:
                if isinstance(rel, list) and len(rel) == 3:
                    allowed_relationships.append(tuple(rel))
                else:
                    logger.warning(f"Skipping invalid relationship format: {rel}")

            example_queries = demo_config.get("example_queries", [])

            demo = GraphRagDemo(
                name=name,
                text=text,
                allowed_nodes=allowed_nodes,
                allowed_relationships=allowed_relationships,
                example_queries=example_queries,
            )
            result.append(demo)
        return result
    except Exception as e:
        logger.exception(f"Error loading demos from config: {e}")
        return []


# Load demos from config
sample_demos = load_demos_from_config()

print(sample_demos)


llm = get_llm(llm=None)
st.title("Graph RAG with Kuzu")

# Initialize session state for graph data
if "graph" not in sss:
    sss.graph = None


def clear_display() -> None:
    """Reset the graph display and state."""
    if "graph" in sss:
        sss.graph = None


# Demo selection
c01, c02 = st.columns([6, 4], border=False, gap="medium", vertical_alignment="top")
with c01.container(border=True):
    selected_pill = st.pills(
        "🎬 **Demos:**",
        options=[demo.name for demo in sample_demos],
        default=sample_demos[0].name,
        on_change=clear_display,
    )

# Get selected demo
demo = next((d for d in sample_demos if d.name == selected_pill), None)
if demo is None:
    st.stop()

# Form for text input and processing
with st.form("graph_input_form"):
    col1, col2 = st.columns([2, 1])
    text = col1.text_area(
        "Enter text to analyze:",
        value=demo.text,
        height=100,
    )
    with col2.expander("Nodes:"):
        st.write(demo.allowed_nodes)
    with col2.expander("Allowed Relationships:"):
        for rel in demo.allowed_relationships:
            src, relation, dst = rel
            st.code(f"{src} -[{relation}]-> {dst}")
    use_cache = st.checkbox("Cache built graph", value=True)
    submitted = st.form_submit_button("Process Text")

DB = "/tmp/test_db"
if submitted:
    # Define schema

    debug(demo.allowed_relationships)

    llm_transformer = LLMGraphTransformer(
        llm=llm,
        allowed_nodes=demo.allowed_nodes,
        allowed_relationships=demo.allowed_relationships,
    )

    # Convert the given text into graph documents
    documents = [Document(page_content=text)]
    graph_documents = llm_transformer.convert_to_graph_documents(documents)
    db = kuzu.Database(DB)
    graph = KuzuGraph(db, allow_dangerous_requests=True)

    # Add the graph document to the graph
    graph.add_graph_documents(
        graph_documents,  # type: ignore
        include_source=True,
    )
    sss.graph = graph

# Display the graph if we have data
if graph := sss.graph:
    with st.expander("Graph Visualization", expanded=True):
        cytoscape(
            elements=get_cytoscape_json(graph),  # type: ignore
            stylesheet=get_cytoscape_style(),
            layout={"name": "cose", "animate": True},
            height="600px",
            key="graph_visualization",
        )

with st.form("graph_query_form"):
    st.subheader("Query the Knowledge Graph")

    # Display example queries if available
    if demo.example_queries:
        sample_query = st.selectbox(
            "Example queries:",
            options=demo.example_queries,
            index=0 if demo.example_queries else None,
        )
    else:
        sample_query = None

    input = st.text_area(
        "Enter query:",
        value=sample_query or "Who is CEO of Apple?",
        height=100,
    )
    submitted = st.form_submit_button("Ask KG!")
    if input and submitted:
        db = kuzu.Database(DB)
        graph = KuzuGraph(db, allow_dangerous_requests=True)

        chain = KuzuQAChain.from_llm(
            llm=llm,
            graph=graph,
            verbose=True,
            allow_dangerous_requests=True,
        )

        result = chain.invoke({"query": input})
        st.write(f"**Result:** {result['result']}")
