"""Opportunity subgraph for EKG system.

Contains all opportunity-specific data model logic and BAML client integration.
This is the only module that imports BAML client types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel
from rich.console import Console

from genai_blueprint.demos.ekg.baml_client.types import Competitor

console = Console()


class Subgraph(ABC):
    """Abstract base class for subgraph implementations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the subgraph."""
        ...

    @abstractmethod
    def load_data(self, key: str) -> Any | None:
        """Load data for the given key."""
        ...

    @abstractmethod
    def build_schema(self) -> Any:
        """Build and return the graph schema configuration."""
        ...

    def get_node_labels(self) -> dict[str, str]:
        """Get mapping of node types to human-readable descriptions from schema."""
        schema = self.build_schema()
        return {node.baml_class.__name__: node.description for node in schema.nodes}

    def get_relationship_labels(self) -> dict[str, tuple[str, str]]:
        """Get mapping of relationship types to (direction, meaning) tuples from schema."""
        schema = self.build_schema()
        result = {}
        for relation in schema.relations:
            direction = f"{relation.from_node.__name__} → {relation.to_node.__name__}"
            result[relation.name] = (direction, relation.description)
        return result

    @abstractmethod
    def get_sample_queries(self) -> list[str]:
        """Get list of sample Cypher queries for this subgraph."""
        ...

    def get_entity_name_from_data(self, data: Any) -> str:
        """Extract a human-readable entity name from loaded data."""
        return "Unknown Entity"


class ReviewedOpportunitySubgraph(Subgraph, BaseModel):
    """Opportunity data subgraph implementation."""

    kv_store_id: str = "file"

    @property
    def name(self) -> str:
        """Name of the subgraph."""
        return "opportunity"

    def load_data(self, opportunity_key: str) -> Any | None:
        """Load opportunity data from the key-value store.

        Args:
            opportunity_key: The opportunity identifier to load

        Returns:
            ReviewedOpportunity instance or None if not found
        """
        try:
            from genai_tk.utils.pydantic.kv_store import PydanticStore

            from genai_blueprint.demos.ekg.baml_client.types import ReviewedOpportunity

            store = PydanticStore(kvstore_id=self.kv_store_id, model=ReviewedOpportunity)
            opportunity = store.load_object(opportunity_key)
            return opportunity
        except Exception as e:
            console.print(f"[red]Error loading opportunity data: {e}[/red]")
            return None

    def build_schema(self) -> Any:
        """Build the graph schema configuration for opportunity data.

        Returns:
            GraphSchema with all node and relationship configurations
        """
        # Define entity type nodes (for IS_A relationships)
        from pydantic import Field

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
        from genai_blueprint.demos.ekg.graph_schema import (
            GraphNodeConfig,
            GraphRelationConfig,
            create_simplified_schema,
        )

        class EntityType(BaseModel):
            """Entity type for taxonomy."""

            type_name: str = Field(description="Name of the entity type")

        # Define nodes with descriptions
        nodes = [
            # Root node
            GraphNodeConfig(
                baml_class=ReviewedOpportunity,
                name_from=lambda data, base: "Rainbow:" + str(data.get("start_date")),
                description="Root node containing the complete reviewed opportunity",
                embedded=[("financial_metrics", FinancialMetrics), ("competition", CompetitiveLandscape)],
            ),
            # Regular nodes - field paths auto-deduced
            GraphNodeConfig(
                baml_class=Opportunity,
                name_from="name",
                description="Core opportunity information with financial metrics embedded",
                index_fields=["name", "status"],
            ),
            GraphNodeConfig(
                baml_class=Customer,
                name_from="name",
                description="Customer organization details",
                index_fields=["name"],
            ),
            GraphNodeConfig(
                baml_class=Person,
                name_from="name",
                deduplication_key="name",
                description="Individual contacts and team members",
            ),
            GraphNodeConfig(baml_class=Partner, name_from="name", description="Partner organization information"),
            GraphNodeConfig(
                baml_class=RiskAnalysis,
                name_from="risk_caterory",
                description="Risk assessment and mitigation details",
                index_fields=["risk_description"],
            ),
            GraphNodeConfig(
                baml_class=TechnicalApproach,
                name_from=lambda data, base: data.get("technical_stack")
                or data.get("architecture")
                or f"{base}_default",
                description="Technical implementation approach and stack",
                index_fields=["architecture", "technical_stack"],
            ),
            # GraphNodeConfig(
            #     baml_class=CompetitiveLandscape,
            #     name_from=lambda data, base: data.get("competitive_position") or f"{base}_competitive_position",
            #     description="Competitive positioning and analysis",
            # ),
            GraphNodeConfig(
                baml_class=Competitor,
                name_from=lambda data, base: data.get("knwon_as") or data.get("name") or f"{base}_competitor",
                description="Competitor",
            ),
        ]

        # Define relationships with descriptions
        # Field paths are automatically deduced from the model structure
        relations = [
            GraphRelationConfig(
                from_node=ReviewedOpportunity,
                to_node=Opportunity,
                name="REVIEWS",
                description="Review relationship to core opportunity",
            ),
            GraphRelationConfig(
                from_node=Opportunity,
                to_node=Customer,
                name="HAS_CUSTOMER",
                description="Opportunity belongs to customer",
            ),
            GraphRelationConfig(
                from_node=Customer, to_node=Person, name="HAS_CONTACT", description="Customer contact persons"
            ),
            GraphRelationConfig(
                from_node=ReviewedOpportunity,
                to_node=Person,
                name="HAS_TEAM_MEMBER",
                description="Internal team members",
            ),
            GraphRelationConfig(
                from_node=ReviewedOpportunity,
                to_node=Partner,
                name="HAS_PARTNER",
                description="Partner organizations involved",
            ),
            GraphRelationConfig(
                from_node=ReviewedOpportunity,
                to_node=RiskAnalysis,
                name="HAS_RISK",
                description="Identified risks and mitigations",
            ),
            GraphRelationConfig(
                from_node=ReviewedOpportunity,
                to_node=TechnicalApproach,
                name="HAS_TECH_STACK",
                description="Technical implementation approach",
            ),
            # GraphRelationConfig(
            #     from_node=ReviewedOpportunity,
            #     to_node=CompetitiveLandscape,
            #     name="COMPETIIVE_LANDSCAPE",
            #     description="Competitive analysis",
            # ),
            GraphRelationConfig(
                from_node=ReviewedOpportunity,
                to_node=Competitor,
                name="HAS_COMPETITOR",
                description="Known competitors",
    #           dest_properties = ["comment"]
            ),
            # Note: No relationship to FinancialMetrics because it's embedded in Opportunity
        ]

        # Create and validate the schema - this will auto-deduce all field paths
        schema = create_simplified_schema(root_model_class=ReviewedOpportunity, nodes=nodes, relations=relations)

        #        debug(schema)
        return schema

    def get_sample_queries(self) -> list[str]:
        """Get list of sample Cypher queries for opportunity data."""
        return [
            "MATCH (n) RETURN labels(n)[0] as NodeType, count(n) as Count",
            "MATCH (o:Opportunity) RETURN o.name, o.status LIMIT 5",
            "MATCH (c:Customer)-[:HAS_CONTACT]->(p:Person) RETURN c.name, p.name, p.role LIMIT 5",
            "MATCH (ro:ReviewedOpportunity)-[:HAS_RISK]->(r:RiskAnalysis) RETURN r.risk_description, r.impact_level LIMIT 3",
            "MATCH (ro:ReviewedOpportunity)-[:HAS_PARTNER]->(partner:Partner) RETURN ro.start_date, partner.name, partner.role",
            "MATCH (o:Opportunity)-[:HAS_CUSTOMER]->(c:Customer) RETURN o.name, c.name, c.segment",
        ]

    def get_entity_name_from_data(self, data: Any) -> str:
        """Extract a human-readable entity name from loaded data."""
        if hasattr(data, "opportunity") and hasattr(data.opportunity, "name"):
            return data.opportunity.name
        return "Unknown Entity"


# Registry for available subgraphs
SUBGRAPH_REGISTRY = {
    "opportunity": ReviewedOpportunitySubgraph(),
}


def get_subgraph(name: str) -> Subgraph:
    """Get subgraph instance by name.

    Args:
        name: Name of the subgraph to retrieve

    Returns:
        Subgraph instance

    Raises:
        ValueError: If subgraph name is not found
    """
    if name not in SUBGRAPH_REGISTRY:
        available = ", ".join(SUBGRAPH_REGISTRY.keys())
        raise ValueError(f"Unknown subgraph '{name}'. Available: {available}")
    return SUBGRAPH_REGISTRY[name]
