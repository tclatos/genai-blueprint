#!/usr/bin/env python3
"""Interactive EKG (Enhanced Knowledge Graph) CLI.

A comprehensive Typer-based CLI for managing a single Kuzu knowledge graph
created from BAML-structured data. Provides commands for adding opportunity data,
querying with Cypher, and exporting visualizations.

Features:
    - Add opportunity data to shared knowledge base
    - Execute interactive Cypher queries
    - Display database schema and statistics
    - Export HTML visualizations with clickable links
    - Rich console output with colors and tables

Commands:
    cli kg add --key OPPORTUNITY_KEY     Add opportunity data to KB
    cli kg delete                        Delete entire KB
    cli kg query                         Interactive Cypher query shell
    cli kg info                          Display DB info and schema
    cli kg export-html                   Export HTML visualization

Usage Examples:
    ```bash
    # Add opportunity data to knowledge base
    uv run cli kg add --key cnes-venus-tma

    # Query the knowledge base interactively
    uv run cli kg query

    # Display database information and mapping
    uv run cli kg info

    # Export HTML visualization
    uv run cli kg export-html
    ```
"""

import shutil
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
from genai_tk.main.cli import CliTopCommand
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from genai_blueprint.demos.ekg.graph_backend import GraphBackend, create_backend_from_config
from genai_blueprint.demos.ekg.text2cypher import query_kg

# Initialize Rich console
console = Console()

# Configuration constants
KV_STORE_ID = "file"


def _get_db_connection() -> GraphBackend | None:
    """Get database connection to the shared EKG database.

    Returns:
        GraphBackend instance or None if database doesn't exist
    """
    try:
        backend = create_backend_from_config("default")
        return backend
    except Exception as e:
        console.print(f"[red]Error connecting to database: {e}[/red]")
        return None


## subcommands


class EkgCommands(CliTopCommand):
    """Commands for interacting with a Knowledge Graph."""

    def get_description(self) -> tuple[str, str]:
        return "kg", "Knowledge Graph commands."

    def register_sub_commands(self, cli_app: typer.Typer) -> None:
        from genai_blueprint.demos.ekg.rainbow_subgraph import get_subgraph

        @cli_app.command("add-doc")
        def add_doc(
            keys: Annotated[
                list[str],
                typer.Option(
                    "--key", "-k", help="Data key(s) to add to the EKG database (can be specified multiple times)"
                ),
            ],
            subgraph: Annotated[
                str, typer.Option("--subgraph", "-g", help="Subgraph type to use")
            ] = "ReviewedOpportunity",
        ) -> None:
            """Add one or more documents to the shared EKG database.

            Loads data from the key-value store and adds it to the
            shared EKG database, creating the database if it doesn't exist.
            Supports incremental additions - nodes with the same _name will be merged,
            preserving creation timestamps and updating modification timestamps.

            Examples:
                # Add single document
                cli kg add --key fake_cnes_1

                # Add multiple documents in one command
                cli kg add --key fake_cnes_1 --key cnes-venus-tma

                # Add documents sequentially (without deleting DB in between)
                cli kg add --key fake_cnes_1
                cli kg add --key cnes-venus-tma
            """
            from genai_blueprint.demos.ekg.graph_core import create_graph

            # Get subgraph implementation
            try:
                subgraph_impl = get_subgraph(subgraph)
            except ValueError as e:
                console.print(f"[red]❌ {e}[/red]")
                raise typer.Exit(1) from e

            # Validate that we have at least one key
            if not keys:
                console.print("[red]❌ At least one --key must be provided[/red]")
                raise typer.Exit(1)

            console.print(Panel(f"[bold cyan]Adding {len(keys)} Document(s) to EKG[/bold cyan]"))

            # Get database path
            db_path = get_ekg_db_path()

            # Check if database exists
            db_exists = db_path.exists()
            if not db_exists:
                console.print(f"📂 Creating EKG database directory: {db_path.parent}")
                db_path.parent.mkdir(parents=True, exist_ok=True)
                console.print("[green]✓[/green] New EKG database will be created")
            else:
                console.print("[green]✓[/green] Adding to existing EKG database (incremental merge)")

            # Create graph configuration once
            console.print("⚙️  Creating graph schema...")
            schema = subgraph_impl.build_schema()
            console.print(
                f"[green]✓[/green] Schema: {len(schema.nodes)} node types, {len(schema.relations)} relationships"
            )

            # Initialize or connect to database once
            console.print("🔧 Connecting to EKG database...")
            backend = create_backend_from_config("default")

            # Track aggregate statistics across all documents
            total_docs_processed = 0
            total_docs_failed = 0
            aggregate_stats = {"nodes_created": 0, "nodes_matched": 0, "relationships_created": 0}

            # Process each key sequentially
            for idx, key in enumerate(keys, 1):
                console.print(f"\n[bold cyan]═══ Processing document {idx}/{len(keys)}: {key} ═══[/bold cyan]")

                try:
                    # Load data
                    console.print("📁 Loading data...")
                    data = subgraph_impl.load_data(key)
                    if not data:
                        console.print(f"[red]❌ No {subgraph} data found for key: {key}[/red]")
                        total_docs_failed += 1
                        continue

                    entity_name = subgraph_impl.get_entity_name_from_data(data)
                    console.print(f"[green]✓[/green] Loaded: [bold]{entity_name}[/bold]")

                    # Add data to the knowledge graph
                    console.print("🚀 Merging into graph...")
                    nodes_dict, relationships = create_graph(backend, data, schema)

                    # Accumulate statistics
                    # Note: create_graph now uses merge_nodes_batch internally which tracks created vs matched
                    # For now, we'll estimate from the nodes_dict and relationships returned
                    doc_nodes = sum(len(node_list) for node_list in nodes_dict.values())
                    doc_rels = len(relationships)

                    aggregate_stats["relationships_created"] += doc_rels
                    # Note: We'd need to refactor create_graph to return merge stats for accurate counts
                    # For now, count all nodes as "created" (the merge happens internally)
                    aggregate_stats["nodes_created"] += doc_nodes

                    total_docs_processed += 1
                    console.print(
                        f"[green]✓[/green] Document {idx} processed: {doc_nodes} nodes, {doc_rels} relationships"
                    )

                except Exception as e:
                    console.print(f"[red]❌ Error processing {key}: {e}[/red]")
                    total_docs_failed += 1
                    continue

            # Display final summary
            console.print(f"\n{'═' * 60}")
            if total_docs_processed > 0:
                console.print(
                    Panel(
                        f"[bold green]✅ Successfully processed {total_docs_processed}/{len(keys)} documents![/bold green]"
                    )
                )
            else:
                console.print(Panel("[bold red]❌ Failed to process any documents[/bold red]"))
                raise typer.Exit(1)

            summary_table = Table(title="Final Summary")
            summary_table.add_column("Metric", style="cyan", no_wrap=True)
            summary_table.add_column("Value", justify="right", style="magenta")

            summary_table.add_row("Documents Processed", f"{total_docs_processed}/{len(keys)}")
            if total_docs_failed > 0:
                summary_table.add_row("Documents Failed", str(total_docs_failed))
            summary_table.add_row("Total Nodes Processed", str(aggregate_stats["nodes_created"]))
            summary_table.add_row("Total Relationships Created", str(aggregate_stats["relationships_created"]))
            summary_table.add_row("Database Path", str(db_path))

            console.print(summary_table)

            console.print("\n[green]💡 Next steps:[/green]")
            console.print("   • Query: [bold]cli kg query[/bold]")
            console.print("   • Info:  [bold]cli kg info[/bold]")
            console.print("   • Export: [bold]cli kg export-html[/bold]")

        @cli_app.command("delete")
        def delete_ekg(
            force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation prompts")] = False,
        ) -> None:
            """Delete the entire EKG database.

            Safely removes the shared database directory after confirmation.
            All opportunity data will be lost.
            """
            console.print(Panel("[bold red]Deleting Entire EKG Database[/bold red]"))

            db_path = get_ekg_db_path()

            if not db_path.exists():
                console.print("[yellow]⚠️  No EKG database found[/yellow]")
                console.print(f"[yellow]Expected path: {db_path}[/yellow]")
                raise typer.Exit(0)

            # Show database info before deletion
            console.print(f"📍 Database location: [bold]{db_path}[/bold]")

            try:
                # Try to get some basic stats
                backend = _get_db_connection()
                if backend:
                    try:
                        tables_result = backend.execute("CALL show_tables() RETURN *")
                        tables_df = tables_result.get_as_df()
                        node_count = len([row for _, row in tables_df.iterrows() if row.get("type") == "NODE"])
                        rel_count = len([row for _, row in tables_df.iterrows() if row.get("type") == "REL"])
                        console.print(f"📊 Contains {node_count} node tables and {rel_count} relationship tables")

                        # Try to get total record counts
                        total_nodes = 0
                        for _, row in tables_df.iterrows():
                            if row.get("type") == "NODE":
                                try:
                                    result = backend.execute(f"MATCH (n:{row['name']}) RETURN count(n) as count")
                                    count = result.get_as_df().iloc[0]["count"]
                                    total_nodes += count
                                except Exception:
                                    pass
                        console.print(f"📊 Total nodes in database: {total_nodes}")
                    except Exception:
                        console.print("📊 Database exists but couldn't read statistics")
            except Exception:
                pass

            # Confirmation
            if not force:
                if not Confirm.ask("[bold red]Are you sure you want to delete the ENTIRE EKG database?[/bold red]"):
                    console.print("[yellow]Operation cancelled[/yellow]")
                    raise typer.Exit(0)

                # Final confirmation for safety
                if not Confirm.ask(
                    "[bold red]This will delete ALL opportunity data. This action cannot be undone. Continue?[/bold red]"
                ):
                    console.print("[yellow]Operation cancelled[/yellow]")
                    raise typer.Exit(0)
            else:
                console.print("[yellow]⚠️  Force mode enabled - skipping confirmation prompts[/yellow]")

            # Delete the database
            console.print("🗑️  Deleting EKG database...")
            try:
                if db_path.is_file():
                    db_path.unlink()
                elif db_path.is_dir():
                    shutil.rmtree(db_path)
                console.print("[green]✅ EKG database deleted successfully[/green]")
                console.print(
                    "[green]You can now start fresh with [bold]cli kg add --key <opportunity_key>[/bold][/green]"
                )
            except Exception as e:
                console.print(f"[red]❌ Error deleting database: {e}[/red]")
                raise typer.Exit(1) from e

        @cli_app.command("query")
        def query_ekg(
            query: str = typer.Argument(help="query to execute"),
            config_name: Annotated[
                str,
                typer.Option(
                    "--config",
                    help="Name of the structured config to use from yaml config",
                ),
            ] = "default",
            llm: Annotated[
                str | None,
                typer.Option(help="Name or tag of the LLM to use by BAML"),
            ] = None,
            subgraph: Annotated[
                str, typer.Option("--subgraph", "-g", help="Subgraph type for sample queries")
            ] = "ReviewedOpportunity",
        ) -> None:
            """Execute queries in natural language (Text-2-Cypher) on the EKG database.

            ex:  List the names of all competitors for opportunities created after January 1, 2012."""
            from loguru import logger

            try:
                df = query_kg(query, subgraph=subgraph, llm_id=llm)
                console.print(df)

            except Exception as e:
                logger.error(f"Failed to execute BAML function '{function_name}': {e}")
                return

            return

        @cli_app.command("cypher")
        def cypher(
            query: str = typer.Argument(help="Cypher query to execute"),
            subgraph: Annotated[
                str, typer.Option("--subgraph", "-g", help="Subgraph type for sample queries")
            ] = "ReviewedOpportunity",
        ) -> None:
            """Execute Cypher queries on the EKG database."""
            console.print(Panel("[bold cyan]Querying EKG Database[/bold cyan]"))

            # Get database connection
            backend = _get_db_connection()
            if not backend:
                console.print("[red]❌ No EKG database found[/red]")
                console.print("[yellow]💡 Add data first: [bold]cli kg add --key <data_key>[/bold][/yellow]")
                raise typer.Exit(1)

            def execute_query(cypher_query: str) -> None:
                """Execute a single Cypher query and display results."""
                if not cypher_query.strip():
                    return

                try:
                    console.print(f"[dim]Executing: {cypher_query}[/dim]")
                    result = backend.execute(cypher_query)
                    df = result.get_as_df()

                    if df.empty:
                        console.print("[yellow]Query returned no results[/yellow]")
                        return

                    # Create a Rich table for results
                    table = Table(title=f"Query Results ({len(df)} rows)")

                    # Add columns
                    for col in df.columns:
                        table.add_column(str(col), style="cyan")

                    # Add rows (limit to first 20 for readability)
                    max_rows = 20
                    for i, (_, row) in enumerate(df.iterrows()):
                        if i >= max_rows:
                            table.add_row(*["..." for _ in df.columns])
                            break
                        table.add_row(*[str(val) for val in row])

                    console.print(table)

                    if len(df) > max_rows:
                        console.print(f"[dim]Showing first {max_rows} of {len(df)} results[/dim]")

                except Exception as e:
                    console.print(f"[red]❌ Query error: {e}[/red]")

            # Execute single query if provided
            if query:
                execute_query(query)
                return

        @cli_app.command("info")
        def show_info(
            subgraph: Annotated[
                str, typer.Option("--subgraph", "-g", help="Subgraph type to display info for")
            ] = "ReviewedOpportunity",
        ) -> None:
            """Display EKG database information, schema, and entity mapping.

            Shows comprehensive information about the EKG database including
            node/relationship counts, schema details, and semantic mapping.
            """
            # Get subgraph implementation
            try:
                subgraph_impl = get_subgraph(subgraph)
            except ValueError as e:
                console.print(f"[red]❌ {e}[/red]")
                raise typer.Exit(1) from e

            console.print(Panel(f"[bold cyan]{subgraph.title()} EKG Database Information[/bold cyan]"))

            # Get database connection
            backend = _get_db_connection()
            if not backend:
                console.print("[red]❌ No EKG database found[/red]")
                console.print("[yellow]💡 Add data first: [bold]cli kg add --key <data_key>[/bold][/yellow]")
                raise typer.Exit(1)

            console.print("[green]✅ Connected to EKG database[/green]\n")

            # Database location info
            db_path = get_ekg_db_path()
            info_table = Table(title="Database Information")
            info_table.add_column("Property", style="cyan", no_wrap=True)
            info_table.add_column("Value", style="green")

            info_table.add_row("Database Path", str(db_path))
            info_table.add_row("Database Type", "Kuzu Graph Database")
            info_table.add_row("Backend", "Kuzu (via GraphBackend abstraction)")
            info_table.add_row("Storage", "Persistent File Storage")
            info_table.add_row("Subgraph Type", subgraph_impl.name)

            console.print(info_table)
            console.print()

            # Get schema information
            try:
                tables_result = backend.execute("CALL show_tables() RETURN *")
                tables_df = tables_result.get_as_df()

                node_tables = []
                rel_tables = []

                for _, row in tables_df.iterrows():
                    if row.get("type") == "NODE":
                        node_tables.append(row["name"])
                    elif row.get("type") == "REL":
                        rel_tables.append(row["name"])

                # Schema overview
                schema_table = Table(title="Schema Overview")
                schema_table.add_column("Component", style="cyan", no_wrap=True)
                schema_table.add_column("Count", justify="right", style="magenta")

                schema_table.add_row("Node Tables", str(len(node_tables)))
                schema_table.add_row("Relationship Tables", str(len(rel_tables)))

                console.print(schema_table)
                console.print()

                # Node statistics
                if node_tables:
                    node_stats_table = Table(title="Node Counts")
                    node_stats_table.add_column("Node Type", style="cyan", no_wrap=True)
                    node_stats_table.add_column("Count", justify="right", style="magenta")

                    for node_type in sorted(node_tables):
                        try:
                            result = backend.execute(f"MATCH (n:{node_type}) RETURN count(n) as count")
                            count = result.get_as_df().iloc[0]["count"]
                            node_stats_table.add_row(node_type, str(count))
                        except Exception as e:
                            node_stats_table.add_row(node_type, f"[red]Error: {e}[/red]")

                    console.print(node_stats_table)
                    console.print()

                # Relationship statistics
                if rel_tables:
                    rel_stats_table = Table(title="Relationship Counts")
                    rel_stats_table.add_column("Relationship Type", style="cyan", no_wrap=True)
                    rel_stats_table.add_column("Count", justify="right", style="magenta")

                    for rel_type in sorted(rel_tables):
                        try:
                            result = backend.execute(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as count")
                            count = result.get_as_df().iloc[0]["count"]
                            rel_stats_table.add_row(rel_type, str(count))
                        except Exception as e:
                            rel_stats_table.add_row(rel_type, f"[red]Error: {e}[/red]")

                    console.print(rel_stats_table)
                    console.print()

            except Exception as e:
                console.print(f"[red]Error retrieving schema information: {e}[/red]")

            # Node Mapping
            console.print(Panel(f"[bold cyan]{subgraph.title()} Node Mapping[/bold cyan]"))

            mapping_table = Table(title="Node Type → Description")
            mapping_table.add_column("Graph Node Type", style="cyan", no_wrap=True)
            mapping_table.add_column("Description", style="yellow")

            # Get node labels from subgraph implementation
            node_labels = subgraph_impl.get_node_labels()

            for node_type, description in node_labels.items():
                mapping_table.add_row(node_type, description)

            console.print(mapping_table)
            console.print()

            # Relationship mapping
            rel_mapping_table = Table(title="Relationship Type → Semantic Meaning")
            rel_mapping_table.add_column("Relationship", style="cyan", no_wrap=True)
            rel_mapping_table.add_column("From → To", style="green")
            rel_mapping_table.add_column("Meaning", style="yellow")

            # Get relationship labels from subgraph implementation
            relationship_meanings = subgraph_impl.get_relationship_labels()

            for rel_type, (direction, meaning) in relationship_meanings.items():
                rel_mapping_table.add_row(rel_type, direction, meaning)

            console.print(rel_mapping_table)

            # Indexed fields information
            console.print("\n[bold cyan]Indexed Fields (Vector Store)[/bold cyan]")
            schema = subgraph_impl.build_schema()
            indexed_fields_table = Table(title="Vector Store Indexed Fields")
            indexed_fields_table.add_column("Node Type", style="cyan", no_wrap=True)
            indexed_fields_table.add_column("Indexed Fields", style="yellow")

            has_indexed = False
            for node in schema.nodes:
                if node.index_fields:
                    has_indexed = True
                    fields_str = ", ".join(node.index_fields)
                    indexed_fields_table.add_row(node.baml_class.__name__, fields_str)

            if has_indexed:
                console.print(indexed_fields_table)
            else:
                console.print("[dim]No fields are configured for vector indexing[/dim]")

            # Embedded fields information
            console.print("\n[bold cyan]Embedded Fields[/bold cyan]")
            embedded_table = Table(title="Fields Embedded in Parent Nodes")
            embedded_table.add_column("Parent Node", style="cyan", no_wrap=True)
            embedded_table.add_column("Embedded Field", style="green")
            embedded_table.add_column("Embedded Class", style="magenta")

            has_embedded = False
            for node in schema.nodes:
                if node.embedded:
                    has_embedded = True
                    for field_name, embedded_class in node.embedded:
                        embedded_table.add_row(node.baml_class.__name__, field_name, embedded_class.__name__)

            if has_embedded:
                console.print(embedded_table)
            else:
                console.print("[dim]No embedded fields configured[/dim]")

            # Quick query suggestions
            console.print("\n[green]💡 Try these queries:[/green]")
            console.print('   • [bold]cli kg query --query "MATCH (n) RETURN labels(n)[0], count(n)"[/bold]')
            console.print("   • [bold]cli kg query[/bold] (interactive shell)")

        @cli_app.command("export-html")
        def export_html(
            output_dir: Annotated[str, typer.Option("--output-dir", "-o", help="Output directory")] = "/tmp",
            open_browser: Annotated[bool, typer.Option("--open/--no-open", help="Open in browser")] = True,
        ) -> None:
            """Export EKG graph visualization as HTML and display clickable link.

            Creates an interactive D3.js visualization of the EKG database
            and saves it to the specified output directory.
            """
            from genai_blueprint.demos.ekg.kuzu_graph_html import generate_html_visualization

            console.print(Panel("[bold cyan]Exporting EKG HTML Visualization[/bold cyan]"))

            # Get database connection
            backend = _get_db_connection()
            if not backend:
                console.print("[red]❌ No EKG database found[/red]")
                console.print("[yellow]💡 Add data first: [bold]cli kg add --key <opportunity_key>[/bold][/yellow]")
                raise typer.Exit(1)

            console.print("[green]✅ Connected to EKG database[/green]")

            # Prepare output path
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            html_filename = "ekg_graph_visualization.html"
            html_file_path = output_path / html_filename

            console.print(f"📁 Output location: [bold]{html_file_path}[/bold]")

            # Generate HTML visualization
            console.print("🎨 Generating interactive visualization...")
            try:
                with console.status("[bold green]Creating HTML visualization..."):
                    generate_html_visualization(backend, str(html_file_path), title="EKG Database Visualization")

                console.print("[green]✅ HTML visualization created successfully[/green]")

                # Get file size
                file_size = html_file_path.stat().st_size
                file_size_mb = file_size / (1024 * 1024)

                # Display export summary
                export_table = Table(title="Export Summary")
                export_table.add_column("Property", style="cyan", no_wrap=True)
                export_table.add_column("Value", style="green")

                export_table.add_row("File Location", str(html_file_path))
                export_table.add_row("File Size", f"{file_size_mb:.2f} MB")
                export_table.add_row("Format", "Interactive HTML + D3.js")
                export_table.add_row("Features", "Zoomable, draggable, hover tooltips")

                console.print(export_table)

                # Create clickable link panel
                file_url = f"file://{html_file_path.absolute()}"
                console.print(
                    Panel(
                        f"[bold green]🌐 Clickable Link:[/bold green]\n\n"
                        f"[link={file_url}]{file_url}[/link]\n\n"
                        f"[dim]Click the link above or copy-paste into your browser[/dim]",
                        title="HTML Visualization Ready",
                        border_style="green",
                    )
                )

                # Optionally open in browser
                if open_browser:
                    try:
                        console.print("🌐 Opening in default browser...")
                        webbrowser.open(file_url)
                        console.print("[green]✅ Opened in browser[/green]")
                    except Exception as e:
                        console.print(f"[yellow]⚠️  Could not open browser automatically: {e}[/yellow]")
                        console.print("[yellow]Please open the file manually using the link above[/yellow]")

            except Exception as e:
                console.print(f"[red]❌ Error generating visualization: {e}[/red]")
                raise typer.Exit(1) from e

        @cli_app.command("schema")
        def show_schema(
            subgraph: Annotated[
                str, typer.Option("--subgraph", "-g", help="Subgraph type to display schema for")
            ] = "ReviewedOpportunity",
        ) -> None:
            """Display knowledge graph schema in Markdown format for LLM context.

            Generates a comprehensive Markdown description of the graph schema including
            node types, relationships, properties, and indexed fields. This output is
            designed to provide context to LLMs for generating correct Cypher queries.
            """
            from rich.markdown import Markdown

            from genai_blueprint.demos.ekg.schema_doc_generator import generate_schema_markdown

            console.print(Panel("[bold cyan]Knowledge Graph Schema[/bold cyan]"))

            try:
                markdown = generate_schema_markdown(subgraph)
                console.print(Markdown(markdown))
            except ValueError as e:
                console.print(f"[red]❌ {e}[/red]")
                raise typer.Exit(1) from e
