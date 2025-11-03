"""Factory for creating LangChain tools to query structured RAG documents.

This module provides a Pydantic-based factory that builds a LangChain
`BaseTool` capable of performing semantic vector searches over structured
documents.  The tool is generated from a `StructuredRagConfig` which
encapsulates the schema, vector store, LLM, and key-value store
configuration.
"""

from typing import List, Optional, TypeVar

from genai_tk.core.prompts import dedent_ws
from langchain_core.documents import Document
from langchain_core.tools import BaseTool
from langchain_core.tools.base import ArgsSchema
from loguru import logger
from pydantic import BaseModel, Field

from genai_blueprint.demos.ekg.struct_rag.struct_rag_doc_processing import StructuredRagConfig, get_schema

T = TypeVar("T", bound=BaseModel)


class StructuredRagToolFactory(BaseModel):
    """Factory for creating LangChain tools to query structured documents.

    Attributes:
        rag_conf: Configuration object describing the schema, vector store,
            LLM, and key-value store to be used.
    """

    rag_conf: StructuredRagConfig

    def create_vector_search_lc_tool(self) -> BaseTool:
        """Create a vector-search tool for semantic queries.

        The generated tool accepts a free-form query, a list of relevant
        sections, and an optional list of entity identifiers.  It performs
        a similarity search against the configured vector store and returns
        a formatted markdown string containing the most relevant fields.

        Returns:
            A LangChain `BaseTool` that executes the described vector
            search workflow.
        """
        _entity_id_name: str = self.rag_conf._key_field.split(".")[-1]
        _top_class_description: dict = self.rag_conf.get_top_class_fields()
        _entity_key_name: str = self.rag_conf._key_field.split(".")[-1]

        class _VectorSearchInput(BaseModel):
            """Input schema for the vector-search tool."""

            query: str = Field(
                ...,
                description=dedent_ws(
                    """
                    The query to the semantic search vector store. 
                    Provide several variants of the request to improve the semantic matching 
                    (ex: broaden, examples,...)
                    """
                ),
            )
            selected_sections: List[str] = Field(
                ...,
                description=dedent_ws(
                    f"""
                    List of sections relevant for the query.
                    Allowed section names SHOULD BE in that list:
                    {"\n- ".join([f"'{k}' ({v})" for k, v in self.rag_conf.get_top_class_fields().items()])}
                    Select only the most relevant sections (maximum 2).
                    """
                ),
            )
            entity_keys: list[str] = Field(
                ...,
                description=dedent_ws(
                    f"""
                    List of '{_entity_id_name}' mentioned in the discussion and whose
                    user is talking about (for example the one returned by a search query
                    and whose user wants more details).

                    Set an empty list if no '{_entity_id_name}' has been mentioned,
                    or if the user request is not related to previously returned
                    {_entity_id_name}.
                    """
                ),
            )

        def get_name() -> str:
            return f"{self.rag_conf.get_top_class().__name__}_retriever"

        def get_description() -> str:
            return dedent_ws(
                f"""
                Retrieve information related to documents described as
                '{self.rag_conf.get_top_class_description()}'.

                Each document is related to a unique id '{_entity_id_name}',
                which is typically a {self.rag_conf.get_key_description()}.

                Args:
                    query: Expanded query, broad enough to improve the semantic matching.
                    selected_sections: A list of up to 2 section names that best match the query,
                        taken from: {"; ".join([f"'{k}' ({v})" for k, v in self.rag_conf.get_top_class_fields().items()])}
                    entity_keys: List of '{_entity_id_name}' mentioned in the context/discussion
                        (empty list if none).
                """
            )

        class _VectorSearchTool(BaseTool):
            """Semantic search tool for structured documents."""

            name: str = get_name()
            description: str = get_description()
            args_schema: Optional[ArgsSchema] = _VectorSearchInput

            def semantic_search(
                self, query: str, selected_sections: list[str], entity_keys: list[str]
            ) -> list[Document]:
                """Execute vector search."""
                allowed = set(_top_class_description.keys())
                invalid = [f for f in selected_sections if f not in allowed]
                if invalid:
                    logger.warning(f"Removing invalid section: {invalid}")
                    selected_sections = [f for f in selected_sections if f in allowed]

                section_filter = {"field_name": {"$in": selected_sections}} if selected_sections else {}
                entity_filter = {"entity_id": {"$in": entity_keys}} if entity_keys else {}

                if not section_filter:
                    logger.warning("empty section filter (incorrect selected_sections)")
                    filter_dict = entity_filter
                else:
                    filter_dict = {"$and": [section_filter, entity_filter]} if entity_filter else section_filter

                vector_store = StructuredRagConfig.get_vector_store_factory().get()
                docs = vector_store.similarity_search(query, k=20, filter=filter_dict)
                return docs

            def _run(self, query: str, selected_sections: List[str], entity_keys: list[str] = []) -> str:
                # Tool executor : call the vector store and format the answer

                docs = self.semantic_search(query, selected_sections, entity_keys)
                if not docs:
                    return "No information found"
                entity_id = docs[0].metadata.get("entity_id", "unknown")
                fields_dict = {}
                for doc in docs:
                    field_name = doc.metadata.get("field_name", "")
                    fields_dict.setdefault(field_name, []).append(doc)

                result_parts = [f"# {_entity_key_name}: {entity_id}"]
                field_order = list(_top_class_description.keys())
                sorted_fields = sorted(
                    fields_dict.keys(),
                    key=lambda x: field_order.index(x) if x in field_order else len(field_order),
                )

                for field_name in sorted_fields:
                    result_parts.append(f"## {field_name}")
                    for doc in fields_dict[field_name]:
                        content = doc.page_content.replace("#", "###")
                        result_parts.append(f"\n{content}")

                return "\n".join(result_parts)

        return _VectorSearchTool()

    def query_vectorstore(self, query: str, k: int = 4, filter: dict = {}) -> List[Document]:
        """Directly query the underlying vector store (useful for testing).

        Args:
            query: The search query.
            k: Number of results to return.
            filter: Optional filter dictionary applied to the search.

        Returns:
            A list of `Document` objects matching the query.
        """
        vector_store = self.rag_conf.embeddings_store.get()
        return vector_store.similarity_search(query, k=k, filter=filter)


def create_structured_rag_tool(schema_name: str, llm_id: str | None = None, kvstore_id: str = "file") -> BaseTool:
    """Create a vector-search tool from a schema configuration.

    The function loads the schema definition, builds a `StructuredRagConfig`,
    and returns a ready-to-use LangChain tool.

    Args:
        schema_name: Name of the schema to load.
        llm_id: Optional identifier of the LLM to use.
        kvstore_id: Identifier of the key-value store (default: "file").

    Returns:
        A LangChain tool that can perform semantic searches over the
        structured RAG documents.

    Raises:
        ValueError: If the requested schema cannot be found.
    """
    embeddings_store = StructuredRagConfig.get_vector_store_factory()
    schema = get_schema(schema_name)
    if schema is None:
        raise ValueError(f"Unknown schema for structured rag: {schema_name}")
    rag_conf = StructuredRagConfig(
        model_definition=schema,
        embeddings_store=embeddings_store,
        llm_id=llm_id,
        kvstore_id=kvstore_id,
    )
    rag = StructuredRagToolFactory(rag_conf=rag_conf)
    return rag.create_vector_search_lc_tool()
