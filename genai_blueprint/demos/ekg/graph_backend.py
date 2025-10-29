"""Graph database backend abstraction layer.

This module provides an abstract interface for graph databases and concrete
implementations for different backends (Kuzu, Neo4j, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class GraphBackend(ABC):
    """Abstract base class for graph database backends."""

    @abstractmethod
    def connect(self, connection_string: str) -> None:
        """Connect to the graph database.

        Args:
            connection_string: Database connection string or path
        """
        ...

    @abstractmethod
    def execute(self, query: str, parameters: dict[str, Any] | None = None) -> Any:
        """Execute a query on the graph database.

        Args:
            query: Query string in the backend's query language
            parameters: Optional query parameters

        Returns:
            Query results
        """
        ...

    @abstractmethod
    def create_node_table(
        self,
        table_name: str,
        fields: dict[str, str],
        primary_key: str,
    ) -> None:
        """Create a node table.

        Args:
            table_name: Name of the node table
            fields: Mapping of field names to types
            primary_key: Primary key field name
        """
        ...

    @abstractmethod
    def create_relationship_table(
        self,
        rel_name: str,
        from_table: str,
        to_table: str,
        properties: dict[str, str] | None = None,
    ) -> None:
        """Create a relationship table.

        Args:
            rel_name: Relationship name/type
            from_table: Source node table
            to_table: Target node table
            properties: Optional relationship properties
        """
        ...

    @abstractmethod
    def drop_table(self, table_name: str) -> None:
        """Drop a table (node or relationship).

        Args:
            table_name: Name of the table to drop
        """
        ...

    @abstractmethod
    def insert_node(self, table_name: str, data: dict[str, Any]) -> None:
        """Insert a node.

        Args:
            table_name: Node table name
            data: Node properties
        """
        ...

    @abstractmethod
    def insert_relationship(
        self,
        rel_name: str,
        from_table: str,
        from_key: str,
        to_table: str,
        to_key: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Insert a relationship.

        Args:
            rel_name: Relationship name/type
            from_table: Source node table
            from_key: Source node key value
            to_table: Target node table
            to_key: Target node key value
            properties: Optional relationship properties
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the database connection."""
        ...

    @abstractmethod
    def get_query_language(self) -> str:
        """Get the query language used by this backend.

        Returns:
            Query language name (e.g., 'Cypher', 'KuzuQL')
        """
        ...


class KuzuBackend(GraphBackend):
    """Kuzu graph database backend implementation."""

    def __init__(self) -> None:
        """Initialize Kuzu backend."""
        self.db: Any = None
        self.conn: Any = None

    def connect(self, connection_string: str) -> None:
        """Connect to Kuzu database."""
        import kuzu

        self.db = kuzu.Database(connection_string)
        self.conn = kuzu.Connection(self.db)

    def execute(self, query: str, parameters: dict[str, Any] | None = None) -> Any:
        """Execute a Cypher query on Kuzu."""
        if not self.conn:
            raise RuntimeError("Not connected to database")
        return self.conn.execute(query)

    def create_node_table(
        self,
        table_name: str,
        fields: dict[str, str],
        primary_key: str,
    ) -> None:
        """Create a node table in Kuzu."""
        fields_str = ", ".join([f"{name} {type_}" for name, type_ in fields.items()])
        create_sql = f"CREATE NODE TABLE {table_name}({fields_str}, PRIMARY KEY({primary_key}))"
        self.execute(create_sql)

    def create_relationship_table(
        self,
        rel_name: str,
        from_table: str,
        to_table: str,
        properties: dict[str, str] | None = None,
    ) -> None:
        """Create a relationship table in Kuzu."""
        if properties:
            props_str = ", " + ", ".join([f"{name} {type_}" for name, type_ in properties.items()])
        else:
            props_str = ""
        create_rel_sql = f"CREATE REL TABLE {rel_name}(FROM {from_table} TO {to_table}{props_str})"
        self.execute(create_rel_sql)

    def drop_table(self, table_name: str) -> None:
        """Drop a table in Kuzu."""
        try:
            self.execute(f"DROP TABLE {table_name};")
        except Exception:
            pass

    def insert_node(self, table_name: str, data: dict[str, Any]) -> None:
        """Insert a node in Kuzu."""
        cleaned_data: dict[str, str] = {}
        for key, value in data.items():
            if value is None:
                cleaned_data[key] = "NULL"
            elif isinstance(value, str):
                escaped = value.replace("'", "\\'")
                cleaned_data[key] = f"'{escaped}'"
            elif isinstance(value, list):
                str_list: list[str] = []
                for v in value:
                    if hasattr(v, "value"):
                        clean_v = str(v.value)
                    elif hasattr(v, "__dict__") or isinstance(v, dict):
                        clean_v = str(v).replace("'", "\\'").replace('"', '\\"')
                    else:
                        clean_v = str(v)
                    escaped_v = clean_v.replace("'", "\\'")
                    str_list.append(f"'{escaped_v}'")
                cleaned_data[key] = f"[{','.join(str_list)}]"
            elif hasattr(value, "value"):
                escaped = str(value.value).replace("'", "\\'")
                cleaned_data[key] = f"'{escaped}'"
            elif hasattr(value, "__dict__") or isinstance(value, dict):
                import re

                clean_str = str(value).replace("'", "\\'").replace('"', '\\"')
                clean_str = re.sub(
                    r"<[^>]+>", lambda m: m.group(0).split("'")[1] if "'" in m.group(0) else m.group(0), clean_str
                )
                cleaned_data[key] = f"'{clean_str}'"
            else:
                cleaned_data[key] = str(value)

        fields = ", ".join([f"{k}: {v}" for k, v in cleaned_data.items()])
        create_sql = f"CREATE (:{table_name} {{{fields}}})"
        self.execute(create_sql)

    def insert_relationship(
        self,
        rel_name: str,
        from_table: str,
        from_key: str,
        to_table: str,
        to_key: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Insert a relationship in Kuzu."""
        from_key_escaped = from_key.replace("'", "\\'")
        to_key_escaped = to_key.replace("'", "\\'")

        # Note: This assumes the primary key field names are known
        # In practice, you'd need to track these or pass them in
        match_sql = f"""
        MATCH (from:{from_table}), (to:{to_table})
        WHERE from.{from_table.lower()}_key = '{from_key_escaped}'
          AND to.{to_table.lower()}_key = '{to_key_escaped}'
        CREATE (from)-[:{rel_name}]->(to)
        """
        self.execute(match_sql)

    def close(self) -> None:
        """Close Kuzu connection."""
        # Kuzu doesn't require explicit closing
        self.db = None
        self.conn = None

    def get_query_language(self) -> str:
        """Get query language."""
        return "Cypher"


class Neo4jBackend(GraphBackend):
    """Neo4j graph database backend implementation (placeholder)."""

    def __init__(self) -> None:
        """Initialize Neo4j backend."""
        self.driver: Any = None

    def connect(self, connection_string: str) -> None:
        """Connect to Neo4j database."""
        raise NotImplementedError("Neo4j backend not yet implemented")

    def execute(self, query: str, parameters: dict[str, Any] | None = None) -> Any:
        """Execute a Cypher query on Neo4j."""
        raise NotImplementedError("Neo4j backend not yet implemented")

    def create_node_table(
        self,
        table_name: str,
        fields: dict[str, str],
        primary_key: str,
    ) -> None:
        """Create a node table in Neo4j."""
        raise NotImplementedError("Neo4j backend not yet implemented")

    def create_relationship_table(
        self,
        rel_name: str,
        from_table: str,
        to_table: str,
        properties: dict[str, str] | None = None,
    ) -> None:
        """Create a relationship table in Neo4j."""
        raise NotImplementedError("Neo4j backend not yet implemented")

    def drop_table(self, table_name: str) -> None:
        """Drop a table in Neo4j."""
        raise NotImplementedError("Neo4j backend not yet implemented")

    def insert_node(self, table_name: str, data: dict[str, Any]) -> None:
        """Insert a node in Neo4j."""
        raise NotImplementedError("Neo4j backend not yet implemented")

    def insert_relationship(
        self,
        rel_name: str,
        from_table: str,
        from_key: str,
        to_table: str,
        to_key: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Insert a relationship in Neo4j."""
        raise NotImplementedError("Neo4j backend not yet implemented")

    def close(self) -> None:
        """Close Neo4j connection."""
        raise NotImplementedError("Neo4j backend not yet implemented")

    def get_query_language(self) -> str:
        """Get query language."""
        return "Cypher"


def create_backend(backend_type: str = "kuzu") -> GraphBackend:
    """Create a graph backend instance.

    Args:
        backend_type: Type of backend ('kuzu', 'neo4j')

    Returns:
        GraphBackend instance
    """
    backends = {
        "kuzu": KuzuBackend,
        "neo4j": Neo4jBackend,
    }

    backend_class = backends.get(backend_type.lower())
    if not backend_class:
        raise ValueError(f"Unknown backend type: {backend_type}. Available: {list(backends.keys())}")

    return backend_class()
