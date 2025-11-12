""" """

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Type

from genai_tk.utils.pydantic.kv_store import PydanticStore
from pydantic import BaseModel
from rich.console import Console

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


class PydanticSubgraph(Subgraph, BaseModel):
    top_class: Type[BaseModel]
    kv_store_id: str

    @property
    def name(self) -> str:
        """Name of the subgraph."""
        return self.top_class.__name__

    def load_data(self, key: str) -> Any | None:
        """Load graph data from the key-value store.

        Args:
            key: The identifier to load

        Returns:
            Top class instance or None if not found
        """
        try:
            store = PydanticStore(kvstore_id=self.kv_store_id, model=self.top_class)
            opportunity = store.load_object(key)
            return opportunity
        except Exception as e:
            console.print(f"[red]Error loading opportunity data: {e}[/red]")
            return None
