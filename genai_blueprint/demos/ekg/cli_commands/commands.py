"""CLI commands for EKG (Enterprise Knowledge Graph) document processing and analysis.

This module provides command-line interface commands for:
- Extracting structured data from Markdown documents using LLMs
- Generating synthetic/fake project data based on existing templates
- Running interactive agents for querying the knowledge graph

The commands integrate with the PydanticRAG system to provide document analysis,
vector storage, and semantic search capabilities.

Key Features:
    - Batch processing of Markdown files with parallel LLM extraction
    - Generation of realistic synthetic project data for testing
    - Interactive ReAct agents for querying processed project information
    - Integration with MCP (Model Context Protocol) servers for extended capabilities
    - Configurable caching strategies and LLM selection

Usage Examples:
    ```bash
    # Extract structured data from Markdown files
    uv run cli structured extract "*.md" --output-dir ./data

    # Generate fake project data from existing JSON templates
    uv run cli structured gen-fake "templates/*.json" --output-dir ./fake --count 5

    # Extract with BAML
    uv run cli structured extract-baml "*.md" --class ReviewedOpportunity --force

    # Start interactive agent for querying the knowledge graph
    uv run cli kg agent --llm gpt-4o-mini --mcp filesystem

    # Process recursively with custom settings
    uv run cli structured extract ./reviews/ --recursive --batch-size 10 --force

    # Debug mode for troubleshooting
    uv run cli kg agent --debug --verbose --cache sqlite
    ```

Data Flow:
    1. Markdown files → rainbow_extract → JSON structured data
    2. JSON templates → rainbow_generate_fake → Synthetic JSON data
    3. Processed data → ekg_agent_shell → Interactive querying via ReAct agent
"""

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from loguru import logger
from typer import Option
from upath import UPath

LLM_ID = None
KV_STORE_ID = "file"


def register_commands(cli_app: typer.Typer) -> None:
    # Create structured sub-app for extraction and generation commands
    structured_app = typer.Typer(no_args_is_help=True, help="Structured extraction and data generation commands.")

    @structured_app.command("extract")
    def structured_extract(
        file_or_dir: Annotated[
            Path,
            typer.Argument(
                help="Markdown files or directories to process",
                exists=True,
                file_okay=True,
                dir_okay=True,
            ),
        ],
        schema: str = typer.Argument(help="name of he schcme dict to use to extract information"),
        llm: Annotated[Optional[str], Option("--llm", "-m", help="LLM identifier (ID or tag from config)")] = None,
        recursive: bool = typer.Option(False, help="Search for files recursively"),
        batch_size: int = typer.Option(5, help="Number of files to process in each batch"),
        force: bool = typer.Option(False, "--force", help="Overwrite existing KV entries"),
    ) -> None:
        """Extract structured project data from Markdown files and save as JSON in a key-value store.

        Example:
           uv run cli structured extract "*.md" "projects/*.md" --output-dir=./json_output --llm-id gpt-4o
           uv run cli structured extract "**/*.md" --recursive --output-dir=./data
        """

        from genai_blueprint.demos.ekg.struct_rag_doc_processing import (
            StructuredRagConfig,
            StructuredRagDocProcessor,
            get_schema,
        )
        from genai_tk.core.llm_factory import LlmFactory
        from genai_tk.utils.pydantic.kv_store import PydanticStore
        from loguru import logger

        # Resolve LLM identifier if provided
        llm_id = None
        if llm:
            resolved_id, error_msg = LlmFactory.resolve_llm_identifier_safe(llm)
            if error_msg:
                print(error_msg)
                return
            llm_id = resolved_id

        schema_dict = get_schema(schema)

        if schema_dict is None:
            logger.error(f"Invalid schema_name: {schema}")
            return
        top_class: str | None = schema_dict.get("top_class")
        if top_class is None:
            logger.error(f"Incorrect schema: {schema}")
            return

        logger.info(f"Starting project extraction with: {file_or_dir} and schema {schema} (class: {top_class})")

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

        embeddings_store = StructuredRagConfig.get_vector_store_factory()
        struct_rag_conf = StructuredRagConfig(
            model_definition=schema_dict,
            embeddings_store=embeddings_store,
            llm_id=None,
            kvstore_id=KV_STORE_ID,
        )
        rag_processor = StructuredRagDocProcessor(rag_conf=struct_rag_conf)
        # Filter out files that already have JSON in KV unless forced
        if not force:
            unprocessed_files = []
            for md_file in md_files:
                key = md_file.stem
                cached_doc = PydanticStore(kvstore_id=KV_STORE_ID, model=struct_rag_conf.get_top_class()).load_object(
                    key
                )
                if not cached_doc:
                    unprocessed_files.append(md_file)
                else:
                    logger.info(f"Skipping {md_file.name} - JSON already exists (use --force to overwrite)")
            md_files = unprocessed_files

        if not md_files:
            logger.info("All files have already been processed. Use --force to reprocess.")
            return
        asyncio.run(rag_processor.process_files(md_files, batch_size))

        logger.success(f"Project extraction complete. {len(md_files)} files processed. Results saved to KV Store")

    @structured_app.command("gen-fake")
    def rainbow_generate_fake(
        file_or_dir: Annotated[
            Path,
            typer.Argument(
                help="JSON files or directories containing project reviews to use as templates",
                exists=True,
                file_okay=True,
                dir_okay=True,
            ),
        ],
        output_dir: Annotated[
            Path,
            typer.Argument(
                help="Output directory for generated fake JSON files",
                file_okay=False,
                dir_okay=True,
            ),
        ],
        count: Annotated[int, Option("--count", "-n", help="Number of fake projects to generate per input file")] = 1,
        llm: Annotated[Optional[str], Option("--llm", "-m", help="LLM identifier (ID or tag from config)")] = None,
        recursive: bool = typer.Option(False, help="Search for files recursively"),
    ) -> None:
        """Generate fake but realistic project review JSON files based on existing ones.

        This command reads existing project review JSON files and uses an LLM to generate
        new similar but fake project data that maintains the structure and realistic patterns
        of the originals.

        Example:
           uv run cli structured gen-fake "projects/*.json" --output-dir=./fake_data --count=5
           uv run cli structured gen-fake sample_project.json --output-dir=./generated --count=3
           uv run cli structured gen-fake "data/**/*.json" --recursive --output-dir=./generated
        """
        from genai_tk.core.llm_factory import LlmFactory

        from genai_blueprint.demos.ekg.generate_fake_rainbows import generate_fake_rainbows_from_samples

        # Resolve LLM identifier if provided
        llm_id = None
        if llm:
            resolved_id, error_msg = LlmFactory.resolve_llm_identifier_safe(llm)
            if error_msg:
                print(error_msg)
                return
            llm_id = resolved_id

        # Collect all JSON files
        all_files = []

        if file_or_dir.is_file() and file_or_dir.suffix.lower() in [".json"]:
            # Single JSON file
            all_files.append(file_or_dir)
        elif file_or_dir.is_dir():
            # Directory - find JSON files inside
            if recursive:
                json_files = list(file_or_dir.rglob("*.json"))
            else:
                json_files = list(file_or_dir.glob("*.json"))
            all_files.extend(json_files)
        else:
            logger.error(f"Invalid path: {file_or_dir} - must be a JSON file or directory")
            return

        if not all_files:
            logger.warning("No JSON files found matching the provided patterns.")
            return

        logger.info(f"Found {len(all_files)} JSON files to process")

        output_path = UPath(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        total_generated = 0
        for json_file in all_files:
            logger.info(f"Processing template: {json_file}")
            generate_fake_rainbows_from_samples(
                examples=[json_file], number_of_generated_fakes=count, output_dir=output_path, llm_id=llm_id
            )
            total_generated += count

        logger.success(
            f"Successfully generated {total_generated} fake project reviews from {len(all_files)} templates in {output_dir}"
        )

    # @structured_app.command("extract-baml")
    # def structured_extract_baml(
    #     file_or_dir: Annotated[
    #         Path,
    #         typer.Argument(
    #             help="Markdown files or directories to process",
    #             exists=True,
    #             file_okay=True,
    #             dir_okay=True,
    #         ),
    #     ],
    #     recursive: bool = typer.Option(False, help="Search for files recursively"),
    #     batch_size: int = typer.Option(5, help="Number of files to process in each batch"),
    #     force: bool = typer.Option(False, "--force", help="Overwrite existing KV entries"),
    #     class_name: Annotated[
    #         str, typer.Option("--class", help="Name of the Pydantic model class to instantiate")
    #     ] = "ReviewedOpportunity",
    # ) -> None:
    #     """Extract structured project data from Markdown files using BAML.

    #     Example:
    #        uv run cli structured extract-baml "*.md" --force --class ReviewedOpportunity
    #     """
    #     from genai_blueprint.demos.ekg.cli_commands.commands_baml import BamlStructuredProcessor
    #     from loguru import logger
    #     from pydantic import BaseModel

    #     import genai_blueprint.demos.ekg.baml_client.types as baml_types

    #     logger.info(f"Starting BAML-based project extraction with: {file_or_dir}")

    #     # Resolve model class from the BAML types module
    #     try:
    #         model_cls = getattr(baml_types, class_name)
    #     except AttributeError as e:
    #         logger.error(f"Unknown class '{class_name}' in baml_client.types: {e}")
    #         return

    #     if not isinstance(model_cls, type) or not issubclass(model_cls, BaseModel):
    #         logger.error(f"Provided class '{class_name}' is not a Pydantic BaseModel")
    #         return

    #     # Collect all Markdown files
    #     all_files = []
    #     KV_STORE_ID = "file"

    #     if file_or_dir.is_file() and file_or_dir.suffix.lower() in [".md", ".markdown"]:
    #         all_files.append(file_or_dir)
    #     elif file_or_dir.is_dir():
    #         if recursive:
    #             md_files = list(file_or_dir.rglob("*.[mM][dD]"))
    #         else:
    #             md_files = list(file_or_dir.glob("*.[mM][dD]"))
    #         all_files.extend(md_files)
    #     else:
    #         logger.error(f"Invalid path: {file_or_dir} - must be a Markdown file or directory")
    #         return

    #     if not all_files:
    #         logger.warning("No Markdown files found matching the provided patterns.")
    #         return

    #     logger.info(f"Found {len(all_files)} Markdown files to process")

    #     if force:
    #         logger.info("Force option enabled - will reprocess all files and overwrite existing KV entries")

    #     # Create BAML processor
    #     processor = BamlStructuredProcessor(model_cls=model_cls, kvstore_id=KV_STORE_ID, force=force)

    #     # Filter out files that already have JSON in KV unless forced
    #     if not force:
    #         from genai_tk.utils.pydantic.kv_store import PydanticStore

    #         unprocessed_files = []
    #         for md_file in all_files:
    #             key = md_file.stem
    #             cached_doc = PydanticStore(kvstore_id=KV_STORE_ID, model=model_cls).load_object(key)
    #             if not cached_doc:
    #                 unprocessed_files.append(md_file)
    #             else:
    #                 logger.info(f"Skipping {md_file.name} - JSON already exists (use --force to overwrite)")
    #         all_files = unprocessed_files

    #     if not all_files:
    #         logger.info("All files have already been processed. Use --force to reprocess.")
    #         return

    #     asyncio.run(processor.process_files(all_files, batch_size))
    #     logger.success(f"BAML-based project extraction complete. {len(all_files)} files processed.")

    # # This agent command will be moved to kg group in commands_ekg.py
    # # @ekg_app.command("agent")
    # def ekg_agent_shell_moved(
    #     input: Annotated[str | None, typer.Option(help="Input query or '-' to read from stdin")] = None,
    #     cache: Annotated[str, typer.Option(help="Cache strategy: 'sqlite', 'memory' or 'no_cache'")] = "memory",
    #     mcp: Annotated[
    #         list[str], typer.Option(help="MCP server names to connect to (e.g. playwright, filesystem, ..)")
    #     ] = [],
    #     lc_verbose: Annotated[bool, Option("--verbose", "-v", help="Enable LangChain verbose mode")] = False,
    #     lc_debug: Annotated[bool, Option("--debug", "-d", help="Enable LangChain debug mode")] = False,
    #     llm: Annotated[Optional[str], Option("--llm", "-m", help="LLM identifier (ID or tag from config)")] = None,
    #     chat: Annotated[bool, Option("--chat", help="Start an interactive shell to send prompts")] = False,
    # ) -> None:
    #     """Run a ReAct agent to query the Enterprise Knowledge Graph (EKG).

    #     Can either start an interactive shell or execute a single query directly.
    #     The agent can query processed project data using semantic search across the
    #     vector store and has access to project information extracted from Markdown files.

    #     The agent integrates with MCP (Model Context Protocol) servers for extended
    #     capabilities like file system access, web browsing, or other external tools.

    #     Examples:
    #         ```bash
    #         # Basic interactive shell
    #         uv run cli ekg agent

    #         # Execute a single query
    #         uv run cli ekg agent --input "Find all projects using Python"

    #         # Read query from stdin
    #         echo "Which projects had budgets over $1M?" | uv run cli ekg agent

    #         # With custom LLM and cache
    #         uv run cli ekg agent --llm gpt-4o-mini --cache sqlite

    #         # With MCP servers for extended capabilities
    #         uv run cli ekg agent --mcp filesystem --mcp playwright --input "List files and analyze project data"

    #         # Force interactive shell even with input
    #         uv run cli ekg agent --shell --input "This will be ignored"

    #         # Debug mode for troubleshooting
    #         uv run cli ekg agent --debug --verbose
    #         ```

    #     Usage modes:
    #         - No --input parameter: Start interactive shell (default behavior)
    #         - With --input: Execute single query and exit
    #         - With --chat: Force interactive shell mode (ignores --input)
    #         - Reading from stdin: Pipe input directly to the agent

    #     Interactive Usage:
    #         Once started, you can ask questions like:
    #         - "Find all projects using Python"
    #         - "Which projects had budgets over $1M?"
    #         - "List team members who worked on healthcare projects"
    #         - "Compare project delivery times across different technologies"
    #     """

    #     from genai_blueprint.demos.ekg.struct_rag_tool_factory import create_structured_rag_tool
    #     from genai_tk.core.llm_factory import LlmFactory
    #     from genai_tk.utils.cli.langchain_setup import setup_langchain
    #     from genai_tk.utils.cli.langgraph_agent_shell import run_langgraph_agent_shell

    #     # Resolve LLM identifier if provided
    #     llm_id = None
    #     if llm:
    #         resolved_id, error_msg = LlmFactory.resolve_llm_identifier_safe(llm)
    #         if error_msg:
    #             print(error_msg)
    #             return
    #         llm_id = resolved_id

    #     if not setup_langchain(llm_id, lc_debug, lc_verbose, cache):
    #         return

    #     rainbow_schema = "Rainbow File"
    #     rainbow_tool = create_structured_rag_tool(rainbow_schema, llm_id=LLM_ID, kvstore_id=KV_STORE_ID)

    #     if chat:
    #         # Force interactive shell mode (ignores input parameter)
    #         asyncio.run(run_langgraph_agent_shell(llm_id, tools=[rainbow_tool], mcp_server_names=mcp))
    #     else:
    #         # Handle input parameter or stdin
    #         if not input and not sys.stdin.isatty():
    #             input = sys.stdin.read()

    #         if input and len(input.strip()) >= 5:
    #             # Execute single query and exit
    #             asyncio.run(call_ekg_agent(input.strip(), llm_id=llm_id, tools=[rainbow_tool], mcp_server_names=mcp))
    #         else:
    #             # No input provided or input too short, start interactive shell (default behavior)
    #             if input and len(input.strip()) < 5:
    #                 print("Warning: Input too short (minimum 5 characters), starting interactive shell instead")
    #             asyncio.run(run_langgraph_agent_shell(llm_id, tools=[rainbow_tool], mcp_server_names=mcp))

    # # Mount sub-apps on root app
    # cli_app.add_typer(structured_app, name="structured")
    # # generate_app merged into structured_app
    # # ekg_app removed - agent command moved to kg group
