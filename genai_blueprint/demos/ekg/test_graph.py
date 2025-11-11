#!/usr/bin/env python3
"""Test script for the Knowledge Graph creation from Pydantic models.

This script demonstrates the complete workflow of creating a knowledge graph
from structured Pydantic data using Kuzu as the graph database.

Features the simplified GraphSchema API that:
- Automatically deduces field paths from Pydantic model structure
- Auto-computes excluded fields based on relationships
- Provides built-in validation and coherence checking
- Eliminates duplicate configurations for the same class
- Handles ForwardRef types automatically
"""

# Add the src directory to Python path for imports

import kuzu
from genai_tk.utils.pydantic.kv_store import PydanticStore
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from genai_blueprint.demos.ekg.baml_client.types import (
    CompetitiveLandscape,
    Customer,
    FinancialMetrics,
    Opportunity,
    Partner,
    Person,
    ReviewedOpportunity,
    RiskAnalysis,
    TechnicalApproach,
)
from genai_blueprint.demos.ekg.graph_core import create_graph, restart_database
from genai_blueprint.demos.ekg.graph_schema import GraphNodeConfig, GraphRelationConfig, create_schema
from genai_blueprint.demos.ekg.kuzu_graph_html import generate_html_visualization

console = Console()

# Configuration constants
KV_STORE_ID = "file"
OPPORTUNITY_KEY = "cnes-venus-tma"


def create_configuration():
    """Create graph configuration using the simplified GraphSchema API.

    This approach provides:
    - 70% less configuration code than legacy approach
    - Auto-deduced field paths from Pydantic model structure
    - Auto-computed excluded fields based on relationships
    - No duplicate configurations for same class in different relationships
    - Automatic coherence validation

    Returns:
        GraphSchema with all auto-deduced configurations
    """
    # Define nodes - just specify the class and name_from field
    nodes = [
        # Root node
        GraphNodeConfig(baml_class=ReviewedOpportunity, name_from="start_date"),
        # Regular nodes - field paths auto-deduced
        GraphNodeConfig(baml_class=Opportunity, name_from="name"),
        GraphNodeConfig(baml_class=Customer, name_from="name"),
        GraphNodeConfig(
            baml_class=Person, name_from="name", deduplication_key="name"
        ),  # Handles both contacts and team
        GraphNodeConfig(baml_class=Partner, name_from="name"),
        GraphNodeConfig(baml_class=RiskAnalysis, name_from="risk_description"),
        GraphNodeConfig(
            baml_class=TechnicalApproach,
            name_from=lambda data, base: data.get("technical_stack") or data.get("architecture") or f"{base}_default",
        ),
        GraphNodeConfig(
            baml_class=CompetitiveLandscape,
            name_from=lambda data, base: data.get("competitive_position") or f"{base}_competitive_position",
        ),
        # Embedded node - financials will be embedded in Opportunity table
        GraphNodeConfig(baml_class=FinancialMetrics, name_from="tcv", embed_in_parent=True, embed_prefix="financial_"),
    ]

    # Define relationships - just specify from/to classes and relationship name
    # Field paths are automatically deduced from the model structure
    relations = [
        GraphRelationConfig(from_node=ReviewedOpportunity, to_node=Opportunity, name="REVIEWS"),
        GraphRelationConfig(from_node=Opportunity, to_node=Customer, name="HAS_CUSTOMER"),
        GraphRelationConfig(from_node=Customer, to_node=Person, name="HAS_CONTACT"),
        GraphRelationConfig(from_node=ReviewedOpportunity, to_node=Person, name="HAS_TEAM_MEMBER"),
        GraphRelationConfig(from_node=ReviewedOpportunity, to_node=Partner, name="HAS_PARTNER"),
        GraphRelationConfig(from_node=ReviewedOpportunity, to_node=RiskAnalysis, name="HAS_RISK"),
        GraphRelationConfig(from_node=ReviewedOpportunity, to_node=TechnicalApproach, name="HAS_TECH_STACK"),
        GraphRelationConfig(from_node=ReviewedOpportunity, to_node=CompetitiveLandscape, name="HAS_COMPETITION"),
        # Note: No relationship to FinancialMetrics because it's embedded in Opportunity
    ]

    # Create and validate the schema - this will auto-deduce all field paths
    # and validate consistency with the Pydantic model structure
    schema = create_schema(root_model_class=ReviewedOpportunity, nodes=nodes, relations=relations)

    return schema


def load_test_data() -> ReviewedOpportunity:
    """Load test opportunity data from the key-value store.

    Returns:
        The loaded ReviewedOpportunity instance
    """
    console.print(Panel("[bold cyan]Loading Test Data[/bold cyan]"))

    store = PydanticStore(kvstore_id=KV_STORE_ID, model=ReviewedOpportunity)
    opportunity = store.load_object(OPPORTUNITY_KEY)

    if not opportunity:
        console.print(f"[red]Error: Could not load opportunity '{OPPORTUNITY_KEY}' from store[/red]")
        exit(1)

    console.print(f"[green]✓[/green] Loaded opportunity: [bold]{opportunity.opportunity.name}[/bold]")
    console.print(f"[green]✓[/green] Status: {opportunity.opportunity.status}")
    console.print(f"[green]✓[/green] Customer: {opportunity.opportunity.customer.name}")
    console.print(f"[green]✓[/green] Team size: {len(opportunity.team)}")
    console.print(f"[green]✓[/green] Partners: {len(opportunity.partners)}")
    console.print(f"[green]✓[/green] Risks: {len(opportunity.risks)}")

    return opportunity


def display_schema_configuration(schema):
    """Display the complete schema configuration with auto-deduced information.

    Args:
        schema: GraphSchema object with all configuration details
    """
    console.print(Panel("[bold cyan]Graph Schema Configuration[/bold cyan]"))

    # Call the built-in schema summary display
    schema.print_schema_summary()

    # Display validation results
    warnings = schema.get_warnings()
    if warnings:
        console.print("\n[bold red]Schema Validation Warnings:[/bold red]")
        for warning in warnings:
            console.print(f"⚠️  {warning}")
    else:
        console.print("\n[bold green]✓ Schema validation passed - no warnings![/bold green]")

    # Display configuration statistics
    console.print("\n[bold]Configuration Summary:[/bold]")
    console.print(f"• Root model: {schema.root_model_class.__name__}")
    console.print(f"• Node types configured: {len(schema.nodes)}")
    console.print(f"• Relationships configured: {len(schema.relations)}")
    console.print(f"• Auto-deduced field paths: {sum(len(n.field_paths) for n in schema.nodes)}")
    console.print(f"• Auto-computed excluded fields: {sum(len(n.excluded_fields) for n in schema.nodes)}")

    # Display auto-deduced details
    console.print("\n[bold]Auto-deduced Information:[/bold]")
    for node in schema.nodes:
        if node.field_paths:
            paths_info = ", ".join(
                [f"{path}{'(list)' if node.is_list_at_paths.get(path, False) else ''}" for path in node.field_paths]
            )
        else:
            paths_info = "ROOT"

        console.print(f"• {node.baml_class.__name__}: {paths_info}")
        if node.excluded_fields:
            console.print(f"  └─ Excluded fields: {', '.join(sorted(node.excluded_fields))}")


def create_statistics_table(conn: kuzu.Connection, config=None) -> None:
    """Display comprehensive statistics about the created graph.

    Args:
        conn: The Kuzu database connection
        config: Either GraphSchema, tuple of (nodes, relations), or None
    """
    console.print(Panel("[bold cyan]Graph Statistics[/bold cyan]"))

    # Handle different config formats
    if config is None:
        console.print("[yellow]No configuration provided for statistics[/yellow]")
        return

    # Extract nodes and relations from config
    if hasattr(config, "nodes") and hasattr(config, "relations"):
        # GraphSchema format
        nodes = config.nodes
        relations = config.relations
    elif isinstance(config, tuple) and len(config) == 2:
        # Legacy (nodes, relations) tuple format
        nodes, relations = config
    else:
        console.print(f"[red]Unsupported config format: {type(config)}[/red]")
        return

    # Node statistics
    node_table = Table(title="Node Counts")
    node_table.add_column("Node Type", style="cyan", no_wrap=True)
    node_table.add_column("Count", justify="right", style="magenta")

    # Get unique node types to avoid duplicates
    unique_node_types = set()
    for node_info in nodes:
        node_type = node_info.baml_class.__name__
        if node_type not in unique_node_types:
            unique_node_types.add(node_type)
            try:
                result = conn.execute(f"MATCH (n:{node_type}) RETURN count(n) as count")
                count = result.get_as_df().iloc[0]["count"]
                node_table.add_row(node_type, str(count))
            except Exception as e:
                node_table.add_row(node_type, f"[red]Error: {e}[/red]")

    console.print(node_table)

    # Relationship statistics
    rel_table = Table(title="Relationship Counts")
    rel_table.add_column("Relationship Type", style="cyan", no_wrap=True)
    rel_table.add_column("Count", justify="right", style="magenta")

    for relation in relations:
        rel_name = relation.name
        try:
            result = conn.execute(f"MATCH ()-[r:{rel_name}]->() RETURN count(r) as count")
            count = result.get_as_df().iloc[0]["count"]
            rel_table.add_row(rel_name, str(count))
        except Exception as e:
            rel_table.add_row(rel_name, f"[red]Error: {e}[/red]")

    console.print(rel_table)


def run_sample_queries(conn: kuzu.Connection) -> None:
    """Run sample queries to demonstrate the graph functionality.

    Args:
        conn: The Kuzu database connection
    """
    console.print(Panel("[bold cyan]Sample Query Results[/bold cyan]"))

    # Opportunity details
    console.print("[bold]Opportunity Details:[/bold]")
    query = "MATCH (o:Opportunity) RETURN o.name as name, o.opportunity_id as id, o.status as status"
    console.print(f"[dim]Query: {query}[/dim]")
    result = conn.execute(query)
    df = result.get_as_df()
    if not df.empty:
        table = Table()
        table.add_column("Name", style="cyan")
        table.add_column("ID", style="magenta")
        table.add_column("Status", style="green")
        for _, row in df.iterrows():
            table.add_row(str(row["name"]), str(row["id"]), str(row["status"]))
        console.print(table)
    else:
        console.print("[yellow]No opportunities found[/yellow]")

    # Customer and contacts
    console.print("\n[bold]Customer and Contacts:[/bold]")
    query = """
        MATCH (o:Opportunity)-[:HAS_CUSTOMER]->(c:Customer)-[:HAS_CONTACT]->(p:Person)
        RETURN c.name as customer, p.name as contact, p.role as role
        """
    console.print(f"[dim]Query: {query.strip()}[/dim]")
    result = conn.execute(query)
    df = result.get_as_df()
    if not df.empty:
        table = Table()
        table.add_column("Customer", style="cyan")
        table.add_column("Contact", style="magenta")
        table.add_column("Role", style="green")
        for _, row in df.iterrows():
            table.add_row(str(row["customer"]), str(row["contact"]), str(row["role"]))
        console.print(table)
    else:
        console.print("[yellow]No customer contacts found[/yellow]")

    # Team members - Query directly from ReviewedOpportunity since that's where the relationship is
    console.print("\n[bold]Team Members (Top 5):[/bold]")
    query = """
        MATCH (ro:ReviewedOpportunity)-[:HAS_TEAM_MEMBER]->(p:Person)
        RETURN p.name as name, p.role as role, p.organization as org
        LIMIT 5
        """
    console.print(f"[dim]Query: {query.strip()}[/dim]")
    result = conn.execute(query)
    df = result.get_as_df()
    if not df.empty:
        table = Table()
        table.add_column("Name", style="cyan")
        table.add_column("Role", style="magenta")
        table.add_column("Organization", style="green")
        for _, row in df.iterrows():
            table.add_row(str(row["name"]), str(row["role"]), str(row["org"]))
        console.print(table)
    else:
        console.print("[yellow]No team members found[/yellow]")

    # Risks - Query directly from ReviewedOpportunity since that's where the relationship is
    console.print("\n[bold]Top 3 Risks:[/bold]")
    query = """
        MATCH (ro:ReviewedOpportunity)-[:HAS_RISK]->(r:RiskAnalysis)
        RETURN r.risk_description as description, r.impact_level as impact, r.status as status
        LIMIT 3
        """
    console.print(f"[dim]Query: {query.strip()}[/dim]")
    result = conn.execute(query)
    df = result.get_as_df()
    if not df.empty:
        table = Table()
        table.add_column("Description", style="cyan", max_width=50)
        table.add_column("Impact", style="magenta")
        table.add_column("Status", style="green")
        for _, row in df.iterrows():
            description = str(row["description"])
            if len(description) > 50:
                description = description[:47] + "..."
            table.add_row(description, str(row["impact"]), str(row["status"]))
        console.print(table)
    else:
        console.print("[yellow]No risks found[/yellow]")


def run_advanced_graph_queries(conn: kuzu.Connection) -> None:
    """Run advanced graph queries to showcase graph capabilities.

    Args:
        conn: The Kuzu database connection
    """
    console.print(Panel("[bold cyan]Advanced Graph Analysis[/bold cyan]"))

    # Path analysis - connections between customer contacts and team members
    console.print("[bold]Connectivity Analysis:[/bold]")
    query = """
        MATCH (ro:ReviewedOpportunity)-[:REVIEWS]->(o:Opportunity)-[:HAS_CUSTOMER]->(c:Customer),
              (ro)-[:HAS_TEAM_MEMBER]->(p:Person)
        RETURN c.name as customer, p.name as team_member, p.role as team_role
        LIMIT 5
        """
    console.print(f"[dim]Query: {query.strip()}[/dim]")
    result = conn.execute(query)
    df = result.get_as_df()
    if not df.empty:
        table = Table(title="Customer-Team Connections")
        table.add_column("Customer", style="cyan")
        table.add_column("Team Member", style="magenta")
        table.add_column("Team Role", style="green")
        for _, row in df.iterrows():
            table.add_row(str(row["customer"]), str(row["team_member"]), str(row["team_role"]))
        console.print(table)
    else:
        console.print("[yellow]No connections found[/yellow]")

    # Risk impact analysis
    console.print("\n[bold]Risk Impact Distribution:[/bold]")
    query = """
        MATCH (ro:ReviewedOpportunity)-[:HAS_RISK]->(r:RiskAnalysis)
        RETURN r.impact_level as impact, count(r) as risk_count
        ORDER BY risk_count DESC
        """
    console.print(f"[dim]Query: {query.strip()}[/dim]")
    result = conn.execute(query)
    df = result.get_as_df()
    if not df.empty:
        table = Table(title="Risk Impact Levels")
        table.add_column("Impact Level", style="cyan")
        table.add_column("Count", justify="right", style="magenta")
        for _, row in df.iterrows():
            table.add_row(str(row["impact"]), str(row["risk_count"]))
        console.print(table)
    else:
        console.print("[yellow]No risk data found[/yellow]")


def main() -> None:
    """Main test execution function."""
    console.print(Text("🚀 Knowledge Graph Test Suite", style="bold magenta"))
    console.print(Text("─" * 50, style="dim"))

    try:
        # Load test data
        opportunity = load_test_data()

        # Create graph configuration
        console.print(Panel("[bold cyan]Creating Graph Schema[/bold cyan]"))
        schema = create_configuration()

        console.print(
            f"[green]✓[/green] Created schema with {len(schema.nodes)} node types and {len(schema.relations)} relationship types"
        )

        # Display schema configuration
        display_schema_configuration(schema)

        # Initialize database
        db, conn = restart_database()

        # Create the knowledge graph
        console.print(Panel("[bold cyan]Creating Knowledge Graph[/bold cyan]"))
        nodes_dict, relationships = create_graph(conn, opportunity, schema)

        # Display statistics
        create_statistics_table(conn, schema)

        # Run sample queries
        console.print(Panel("[bold cyan]Sample Queries[/bold cyan]"))
        run_sample_queries(conn)

        # Run advanced queries
        console.print(Panel("[bold cyan]Advanced Analysis[/bold cyan]"))
        run_advanced_graph_queries(conn)

        # Generate visualization
        console.print(Panel("[bold cyan]Generating Visualization[/bold cyan]"))
        try:
            generate_html_visualization(conn, "ekg_visu.html", title="Enhanced Knowledge Graph")
            console.print("[green]✓[/green] Graph visualization saved to ekg_visu.html")
        except ImportError as e:
            console.print(f"[yellow]Warning: Could not generate visualization: {e}[/yellow]")
            console.print("[green]✓[/green] Database operations completed successfully")

        # Summary
        console.print(Panel("[bold green]Test Completed Successfully![/bold green]"))
        total_nodes = sum(len(node_list) for node_list in nodes_dict.values())
        console.print("[bold]Summary:[/bold]")
        console.print(f"• Total nodes created: {total_nodes}")
        console.print(f"• Total relationships created: {len(relationships)}")
        console.print(f"• Node types: {len([k for k, v in nodes_dict.items() if v])}")
        console.print(f"• Relationship types: {len(set(rel[4] for rel in relationships))}")
        console.print(f"• Auto-deduced field paths: {sum(len(n.field_paths) for n in schema.nodes)}")
        console.print(f"• Auto-computed excluded fields: {sum(len(n.excluded_fields) for n in schema.nodes)}")

    except Exception as e:
        console.print(Panel(f"[bold red]Test Failed[/bold red]\n\n{str(e)}", style="red"))
        raise


if __name__ == "__main__":
    main()
