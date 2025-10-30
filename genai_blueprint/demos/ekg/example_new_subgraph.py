#!/usr/bin/env python3
"""Example demonstrating how easy it is to add a new subgraph type.

This shows the extensibility of the refactored EKG system.
"""

from typing import Any

from pydantic import BaseModel

from genai_blueprint.demos.ekg.rainbow_subgraph import SUBGRAPH_REGISTRY, Subgraph


# Example: Adding a new "Project" data model
class Project(BaseModel):
    """Example project data model."""

    name: str
    status: str
    manager: str
    budget: float


class ProjectSubgraph(Subgraph, BaseModel):
    """Example project subgraph implementation."""

    kv_store_id: str = "file"

    @property
    def name(self) -> str:
        """Name of the subgraph."""
        return "project"

    def load_data(self, key: str) -> Any | None:
        """Load project data from some data source."""
        # This would load from your actual data source
        # For demo purposes, return a mock project
        return Project(name=f"Project-{key}", status="Active", manager="Jane Doe", budget=100000.0)

    def build_schema(self) -> Any:
        """Build the graph schema configuration for project data."""
        from genai_blueprint.demos.ekg.graph_schema import GraphNodeConfig, create_simplified_schema

        # Define nodes with descriptions
        nodes = [
            GraphNodeConfig(
                baml_class=Project, name_from="name", description="Project information with status and budget"
            ),
            # Add more nodes as needed...
        ]

        # Define relationships with descriptions
        relations = [
            # Add relationships as needed...
        ]

        # Create and validate the schema
        schema = create_simplified_schema(root_model_class=Project, nodes=nodes, relations=relations)

        return schema

    def get_sample_queries(self) -> list[str]:
        """Get list of sample Cypher queries for project data."""
        return [
            "MATCH (p:Project) RETURN p.name, p.status, p.budget",
            "MATCH (p:Project) WHERE p.budget > 50000 RETURN p.name, p.budget",
            "MATCH (p:Project) RETURN p.status, count(p) as count",
        ]

    def get_entity_name_from_data(self, data: Any) -> str:
        """Extract a human-readable entity name from loaded data."""
        if hasattr(data, "name"):
            return data.name
        return "Unknown Project"


def main():
    """Demonstrate adding a new subgraph type."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()

    console.print(Panel("[bold cyan]Adding New Subgraph Type Example[/bold cyan]"))

    # Add the new subgraph to the registry
    SUBGRAPH_REGISTRY["project"] = ProjectSubgraph()

    console.print(f"✓ Available subgraphs: {list(SUBGRAPH_REGISTRY.keys())}")

    # Test the new subgraph
    from rainbow_subgraph import get_subgraph

    project_subgraph = get_subgraph("project")
    console.print(f"✓ Loaded project subgraph: {project_subgraph.name}")

    # Test methods
    data = project_subgraph.load_data("test-project")
    console.print(f"✓ Loaded data: {project_subgraph.get_entity_name_from_data(data)}")

    queries = project_subgraph.get_sample_queries()
    console.print(f"✓ Sample queries: {len(queries)} queries")

    console.print(
        Panel(
            "[bold green]✅ New subgraph added successfully![/bold green]\\n\\n"
            + "[dim]The new project subgraph is now available in the CLI:\\n"
            + "• ekg kg-add --key my-project --subgraph project\\n"
            + "• ekg kg-query --subgraph project\\n"
            + "• ekg kg-info --subgraph project[/dim]",
            title="Extension Complete",
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()
