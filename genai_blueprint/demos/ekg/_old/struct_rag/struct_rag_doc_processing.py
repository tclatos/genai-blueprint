"""Utilities for extracting structured information from markdown documents and storing it
in a vector database.

The module defines a configuration model for the extraction pipeline, a processor that
handles batch analysis, caching, and conversion of Pydantic models into searchable
document chunks, and helper functions for loading schema definitions.
"""

import asyncio
from typing import Any, Type

import nest_asyncio
from beartype.door import is_bearable
from genai_tk.core.embeddings_store import EmbeddingsStore
from genai_tk.core.llm_factory import get_llm
from genai_tk.core.prompts import def_prompt
from genai_tk.utils.config_mngr import global_config
from genai_tk.utils.pydantic.dyn_model_factory import PydanticModelFactory
from genai_tk.utils.pydantic.kv_store import PydanticStore, save_object_to_kvstore
from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig
from loguru import logger  # noqa: F401
from markpickle import dumps
from pydantic import BaseModel, ConfigDict, PrivateAttr
from upath import UPath

from genai_blueprint.demos.ekg.cli_commands.commands import KV_STORE_ID

# Markdown separators for text splitting
# fmt:off
MARKDOWN_SEPARATOR = [
    "\n\n", "\n#", "\n##", "\n###", "\n####", "\n#####", "\n######",
    "\n---", "\n***", "\n|", "\n- ", "\1. ""\n2. ", "\n3. ", "\n```", "\n", " ", ""
]
# fmt:on


def get_schema(schema_name: str) -> dict | None:
    """Retrieve a schema definition from the configuration.

    The function loads the ``document_extractor.yaml`` configuration file and returns the
    dictionary that matches the provided ``schema_name``. If no matching schema is found,
    ``None`` is returned.
    """
    list_demos = (
        global_config().merge_with("config/schemas/document_extractor.yaml").get_list("Document_extractor_demo")
    )
    schema_dict = next((item for item in list_demos if item.get("schema_name") == schema_name), None)
    return schema_dict


class StructuredRagConfig(BaseModel):
    """Configuration for a structured RAG document processing pipeline."""

    model_definition: dict
    embeddings_store: EmbeddingsStore
    llm_id: str | None
    kvstore_id: str | None = None

    _top_class: Type[BaseModel] = PrivateAttr()
    _key_field: str = PrivateAttr()
    _llm: Any = PrivateAttr()

    def model_post_init(self, __context: Any) -> None:
        """Validate the model definition and create required components."""
        required_keys = ["schema", "key", "top_class"]
        for k in required_keys:
            if self.model_definition.get(k) is None:
                raise ValueError("Model should have key '{k}'")
        converter = PydanticModelFactory()
        self._top_class = converter.create_class_from_dict(
            self.model_definition["schema"], self.model_definition["top_class"]
        )
        self._key_field = self.model_definition["key"]
        self._llm = get_llm(llm_id=self.llm_id, streaming=False, temperature=0.0)

    def get_top_class(self) -> type[BaseModel]:
        """Return the main Pydantic model class for document extraction."""
        return self._top_class

    def get_top_class_fields(self) -> dict:
        """Return a mapping of field names to their descriptions."""
        return {
            field_name: getattr(field_info, "description", "")
            for field_name, field_info in self._top_class.model_fields.items()
            if field_name != "source"
        }

    def get_top_class_description(self) -> str:
        """Return the description of the top‑level model."""
        return self.model_definition.get("schema", {}).get(self._top_class.__name__, {}).get("description", "")

    def get_key_description(self) -> str:
        """Return the description of the primary key field."""
        key_path = self._key_field.split(".")
        current_schema = self.model_definition.get("schema", {})

        top_class_name = self.model_definition.get("top_class", "")
        if not top_class_name or top_class_name not in current_schema:
            return ""

        description = ""
        temp_schema = current_schema

        if "fields" in current_schema[top_class_name]:
            temp_schema = current_schema[top_class_name]["fields"]

        for i, key_part in enumerate(key_path):
            if key_part in temp_schema:
                field_def = temp_schema[key_part]

                if i == len(key_path) - 1:
                    description = field_def.get("description", "")
                    break

                if "type" in field_def:
                    field_type = field_def["type"]
                    if field_type.startswith("list[") and field_type.endswith("]"):
                        field_type = field_type[5:-1]

                    if field_type in current_schema:
                        if "fields" in current_schema[field_type]:
                            temp_schema = current_schema[field_type]["fields"]
                        else:
                            break
                    else:
                        break
                else:
                    break
            else:
                break

        return description

    @staticmethod
    def get_vector_store_factory() -> EmbeddingsStore:
        """Create a vector store factory configured with the postgres backend."""
        # Note: This uses the postgres configuration which should be configured
        # in the baseline.yaml with proper embeddings and PgVector settings
        embeddings_store = EmbeddingsStore.create_from_config("postgres")
        return embeddings_store


class StructuredRagDocProcessor(BaseModel):
    """Processor that extracts structured data from documents and stores it in a vector DB."""

    rag_conf: StructuredRagConfig

    model_config = ConfigDict(arbitrary_types_allowed=True)

    async def abatch_analyze_documents(self, document_ids: list[str], markdown_contents: list[str]) -> list[BaseModel]:
        """Process multiple documents asynchronously with caching."""
        analyzed_docs: list[BaseModel] = []
        remaining_ids: list[str] = []
        remaining_contents: list[str] = []

        # Check cache first
        if self.rag_conf.kvstore_id:
            for doc_id, content in zip(document_ids, markdown_contents, strict=True):
                cached_doc = PydanticStore(
                    kvstore_id=self.rag_conf.kvstore_id, model=self.rag_conf.get_top_class()
                ).load_object(doc_id)

                if cached_doc:
                    analyzed_docs.append(cached_doc)
                else:
                    remaining_ids.append(doc_id)
                    remaining_contents.append(content)
        else:
            remaining_ids = document_ids
            remaining_contents = markdown_contents

        if not remaining_ids:
            return analyzed_docs

        # Process uncached documents
        system = f"""
            Extract structured information from the document below into {self.rag_conf._top_class.__name__} schema. 
            Answer with a JSON document. Avoid explanations or extra text."""
        user = "Document to analyze:\n---\n{input}\n---"
        chain = def_prompt(system=system, user=user) | self.rag_conf._llm.with_structured_output(
            self.rag_conf._top_class
        )

        try:
            batch_results = await chain.abatch(
                [{"input": content} for content in remaining_contents],
                config=RunnableConfig(max_concurrency=5),
            )

            for doc_id, result in zip(remaining_ids, batch_results, strict=False):
                result.__setattr__("document_id", doc_id)
                analyzed_docs.append(result)
                if self.rag_conf.kvstore_id:
                    save_object_to_kvstore(doc_id, result, kv_store_id="file")

        except Exception as batch_error:
            logger.error(f"Batch analysis failed: {batch_error}")
        return analyzed_docs

    def analyze_document(self, document_id: str, markdown: str) -> BaseModel:
        """Analyze a single document synchronously."""
        try:
            if asyncio.get_event_loop().is_running():
                nest_asyncio.apply()
                loop = asyncio.get_event_loop()
                results = loop.run_until_complete(self.abatch_analyze_documents([document_id], [markdown]))
            else:
                results = asyncio.run(self.abatch_analyze_documents([document_id], [markdown]))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(self.abatch_analyze_documents([document_id], [markdown]))

        return results[0]

    def kv_to_vector_store(self) -> None:
        """Load all documents from KV store into the vector database."""
        self.rag_conf.embeddings_store.get()
        self.rag_conf.embeddings_store.delete_collection()
        psf = PydanticStore(kvstore_id=KV_STORE_ID, model=self.rag_conf.get_top_class())
        for keys in psf.get_kv_store().yield_keys():
            clean_key = keys.removesuffix(".json")
            obj = psf.load_object(clean_key)
            if obj:
                self.store(obj)
            else:
                logger.warning(f"cannot load object from kv: {clean_key}")

    def store(self, model_instance: BaseModel) -> None:
        """Store a model instance in the vector database."""
        chunks = self.chunck(model_instance)
        self.store_chunks(chunks)

    def store_chunks(self, chunks: list[Document]) -> None:
        """Store document chunks in the vector database."""
        vector_store = self.rag_conf.embeddings_store.get()
        vector_store.add_documents(chunks)

    def chunck(self, model_instance: BaseModel) -> list[Document]:
        """Convert model fields into searchable document chunks."""
        documents = []
        model_data = model_instance.model_dump()
        document_id = getattr(model_instance, "document_id", None)

        for field_name, field_value in model_data.items():
            if field_value is None:
                continue
            field_info = type(model_instance).model_fields.get(field_name)
            if field_info is None:
                continue

            serialized_content = f"{dumps(field_value)}"
            if is_bearable(field_value, list[dict]):
                chunks = [f"{dumps(field_value[i : i + 5])}" for i in range(0, len(field_value), 5)]  # type: ignore
            else:
                chunks = [serialized_content]

            for chunk in chunks:
                field_doc = Document(
                    page_content=chunk,
                    metadata={
                        "field_name": field_name,
                        "model_class": model_instance.__class__.__name__,
                        "description": getattr(field_info, "description", "") or "",
                        "document_id": document_id,
                        "entity_id": self.get_key(model_instance),
                    },
                )
                documents.append(field_doc)
        return documents

    def get_key(self, obj: BaseModel) -> str:
        """Extract the primary key from a model instance."""
        key_path = self.rag_conf._key_field.split(".")
        current_value = obj
        for key_part in key_path:
            if isinstance(current_value, dict):
                current_value = current_value.get(key_part)
            else:
                current_value = getattr(current_value, key_part, None)
            if current_value is None and key_part == key_path[0]:
                current_value = obj
        if current_value is None:
            raise ValueError(f"incorrect key {self.rag_conf._key_field}")
        return str(current_value)

    async def process_files(self, md_files: list[UPath], batch_size: int = 5) -> None:
        """Process markdown files in batches."""
        document_ids = []
        markdown_contents = []
        valid_files = []

        for file_path in md_files:
            try:
                content = file_path.read_text(encoding="utf-8")
                document_ids.append(file_path.stem)
                markdown_contents.append(content)
                valid_files.append(file_path)
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")

        if not document_ids:
            logger.warning("No valid files to process")
            return

        logger.info(
            f"Processing {len(valid_files)} files in batches of {batch_size}. Output in '{self.rag_conf.kvstore_id}' KV Store"
        )

        _ = await self.abatch_analyze_documents(document_ids, markdown_contents)
