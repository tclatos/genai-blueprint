"""Opportunity subgraph for EKG system.

Contains all opportunity-specific data model logic and BAML client integration.
This is the only module that imports BAML client types.
"""

from __future__ import annotations

from typing import Any, Type

from pydantic import BaseModel

from genai_blueprint.demos.ekg.baml_client.types import ReviewedOpportunity
from genai_blueprint.demos.ekg.subgraph import PydanticSubgraph, Subgraph


class ReviewedOpportunitySubgraph(PydanticSubgraph, BaseModel):
    """Opportunity data subgraph implementation."""

    top_class: Type[BaseModel] = ReviewedOpportunity
    kv_store_id: str = "default"

    def build_schema(self) -> Any:
        """Build the graph schema configuration for opportunity data.

        Returns:
            GraphSchema with all node and relationship configurations
        """
        # Define entity type nodes (for IS_A relationships)

        from genai_blueprint.demos.ekg.baml_client.types import (
            CompetitiveLandscape,
            Competitor,
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
            create_schema,
        )

        # Define nodes with descriptions
        nodes = [
            # Root node
            GraphNodeConfig(
                baml_class=self.top_class,
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
                name_from=lambda data, _: data.get("risk_category") or data.get("p_risk_description_") or "other_risk",
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
                name_from=lambda data, base: data.get("known_as") or data.get("name") or f"{base}_competitor",
                # name_from="known_as",
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
            ),
        ]

        # Create and validate the schema - this will auto-deduce all field paths
        schema = create_schema(root_model_class=self.top_class, nodes=nodes, relations=relations)

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
        if hasattr(data, "ReviewedOpportunity") and hasattr(data.opportunity, "name"):
            return data.opportunity.name
        return "Unknown Entity"


# Registry for available subgraphs
SUBGRAPH_REGISTRY = {
    "ReviewedOpportunity": ReviewedOpportunitySubgraph(),
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
