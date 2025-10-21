"""BAML-based version of structured extraction CLI commands.

This module provides an alternative implementation of the structured_extract function
that uses BAML instead of langchain for structured output extraction. It leverages
the BAML-generated client to extract structured data from markdown files into any
Pydantic BaseModel provided at runtime.

Key Features:
    - Uses BAML's ExtractRainbow function for structured data extraction
    - Maintains the same CLI interface as the original version
    - Compatible with existing KV store and batch processing infrastructure
    - Supports any Pydantic BaseModel (validated at runtime)

Usage Examples:
    ```bash
    # Extract structured data from Markdown files using BAML
    uv run cli structured extract-baml "*.md" --class ReviewedOpportunity --force

    # Process recursively with custom settings
    uv run cli structured extract-baml ./reviews/ --recursive --batch-size 10 --force --class ReviewedOpportunity
    ```

Data Flow:
    1. Markdown files → BAML ExtractRainbow → model instances
    2. Model instances → KV Store → JSON structured data
    3. Processed data → Available for EKG agent querying
"""

import asyncio
from pathlib import Path
from typing import Annotated, Generic, Type, TypeVar

import typer
from loguru import logger
from pydantic import BaseModel
from upath import UPath

import genai_blueprint.demos.ekg.baml_client.types as baml_types
from genai_blueprint.demos.ekg.baml_client.async_client import b as baml_async_client

LLM_ID = None
KV_STORE_ID = "file"


T = TypeVar("T", bound=BaseModel)


class BamlStructuredProcessor(Generic[T]):
    """Processor that uses BAML for extracting structured data from documents."""

    def __init__(self, model_cls: Type[T], kvstore_id: str | None = None, force: bool = False) -> None:
        self.model_cls = model_cls
        self.kvstore_id = kvstore_id or KV_STORE_ID
        self.force = force

    async def abatch_analyze_documents(self, document_ids: list[str], markdown_contents: list[str]) -> list[T]:
        """Process multiple documents asynchronously with caching using BAML."""
        from genai_tk.utils.pydantic.kv_store import PydanticStore, save_object_to_kvstore

        analyzed_docs: list[T] = []
        remaining_ids: list[str] = []
        remaining_contents: list[str] = []

        # Check cache first (unless force is enabled)
        if self.kvstore_id and not self.force:
            for doc_id, content in zip(document_ids, markdown_contents, strict=True):
                cached_doc = PydanticStore(kvstore_id=self.kvstore_id, model=self.model_cls).load_object(doc_id)

                if cached_doc:
                    analyzed_docs.append(cached_doc)
                    logger.info(f"Loaded cached document: {doc_id}")
                else:
                    remaining_ids.append(doc_id)
                    remaining_contents.append(content)
        else:
            remaining_ids = document_ids
            remaining_contents = markdown_contents

        if not remaining_ids:
            return analyzed_docs

        # Process uncached documents using BAML concurrent calls pattern
        logger.info(f"Processing {len(remaining_ids)} documents with BAML async client...")

        # Create concurrent tasks for all remaining documents
        tasks = [baml_async_client.ExtractRainbow(rainbow_file=content) for content in remaining_contents]

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and save to KV store
        for doc_id, result in zip(remaining_ids, results, strict=True):
            if isinstance(result, Exception):
                logger.error(f"Failed to process document {doc_id}: {result}")
                continue

            try:
                # Add document_id as a custom attribute
                result_dict = result.model_dump()
                result_dict["document_id"] = doc_id
                result_with_id = self.model_cls(**result_dict)

                analyzed_docs.append(result_with_id)
                logger.success(f"Processed document: {doc_id}")

                # Save to KV store
                if self.kvstore_id:
                    save_object_to_kvstore(doc_id, result_with_id, kv_store_id=self.kvstore_id)
                    logger.debug(f"Saved to KV store: {doc_id}")

            except Exception as e:
                logger.error(f"Failed to save document {doc_id}: {e}")

        return analyzed_docs

    def analyze_document(self, document_id: str, markdown: str) -> T:
        """Analyze a single document synchronously using BAML."""
        try:
            results = asyncio.run(self.abatch_analyze_documents([document_id], [markdown]))
        except RuntimeError:
            # If we're in an async context, try nest_asyncio
            try:
                import nest_asyncio

                nest_asyncio.apply()
                loop = asyncio.get_running_loop()
                results = loop.run_until_complete(self.abatch_analyze_documents([document_id], [markdown]))
            except Exception as e:
                raise ValueError(f"Failed to process document {document_id}: {e}") from e

        if results:
            return results[0]
        else:
            raise ValueError(f"Failed to process document: {document_id}")

    async def process_files(self, md_files: list[UPath], batch_size: int = 5) -> None:
        """Process markdown files in batches using BAML."""
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

        logger.info(f"Processing {len(valid_files)} files using BAML. Output in '{self.kvstore_id}' KV Store")

        # Process all documents (BAML handles batching internally)
        _ = await self.abatch_analyze_documents(document_ids, markdown_contents)


def register_baml_commands(cli_app: typer.Typer) -> None:
    """Register BAML-based commands with the CLI application."""

    # This command will be added to the main structured group in commands.py
    # @cli_app.command("structured-baml-extract")
    def structured_extract_baml(
        file_or_dir: Annotated[
            Path,
            typer.Argument(
                help="Markdown files or directories to process",
                exists=True,
                file_okay=True,
                dir_okay=True,
            ),
        ],
        recursive: bool = typer.Option(False, help="Search for files recursively"),
        batch_size: int = typer.Option(5, help="Number of files to process in each batch"),
        force: bool = typer.Option(False, "--force", help="Overwrite existing KV entries"),
        class_name: Annotated[
            str, typer.Option("--class", help="Name of the Pydantic model class to instantiate")
        ] = "ReviewedOpportunity",
    ) -> None:
        """Extract structured project data from Markdown files using BAML and save as JSON in a key-value store.

        This command uses BAML's ExtractRainbow function to extract data from markdown files
        and instantiate the provided Pydantic model class. It provides the same functionality
        as structured_extract but uses BAML for structured output.

        Example:
           uv run cli structured extract-baml "*.md" --force --class ReviewedOpportunity
           uv run cli structured extract-baml "**/*.md" --recursive --class ReviewedOpportunity
        """

        logger.info(f"Starting BAML-based project extraction with: {file_or_dir}")

        # Resolve model class from the BAML types module
        try:
            model_cls = getattr(baml_types, class_name)
        except AttributeError as e:
            logger.error(f"Unknown class '{class_name}' in baml_client.types: {e}")
            return

        if not isinstance(model_cls, type) or not issubclass(model_cls, BaseModel):
            logger.error(f"Provided class '{class_name}' is not a Pydantic BaseModel")
            return

        # Collect all Markdown files
        all_files = []

        if file_or_dir.is_file() and file_or_dir.suffix.lower() in [".md", ".markdown"]:
            # Single Markdown file
            all_files.append(file_or_dir)
        elif file_or_dir.is_dir():
            # Directory - find Markdown files inside
            if recursive:
                md_files = list(file_or_dir.rglob("*.[mM][dD]"))  # Case-insensitive match
            else:
                md_files = list(file_or_dir.glob("*.[mM][dD]"))
            all_files.extend(md_files)
        else:
            logger.error(f"Invalid path: {file_or_dir} - must be a Markdown file or directory")
            return

        md_files = all_files  # All files are already Markdown files at this point

        if not md_files:
            logger.warning("No Markdown files found matching the provided patterns.")
            return

        logger.info(f"Found {len(md_files)} Markdown files to process")

        if force:
            logger.info("Force option enabled - will reprocess all files and overwrite existing KV entries")

        # Create BAML processor
        processor = BamlStructuredProcessor(model_cls=model_cls, kvstore_id=KV_STORE_ID, force=force)

        # Filter out files that already have JSON in KV unless forced
        if not force:
            from genai_tk.utils.pydantic.kv_store import PydanticStore

            unprocessed_files = []
            for md_file in md_files:
                key = md_file.stem
                cached_doc = PydanticStore(kvstore_id=KV_STORE_ID, model=model_cls).load_object(key)
                if not cached_doc:
                    unprocessed_files.append(md_file)
                else:
                    logger.info(f"Skipping {md_file.name} - JSON already exists (use --force to overwrite)")
            md_files = unprocessed_files

        if not md_files:
            logger.info("All files have already been processed. Use --force to reprocess.")
            return

        asyncio.run(processor.process_files(md_files, batch_size))

        logger.success(
            f"BAML-based project extraction complete. {len(md_files)} files processed. Results saved to KV Store"
        )

    # BAML function will be called from commands.py structured group
