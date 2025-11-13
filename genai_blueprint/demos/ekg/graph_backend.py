"""Graph database backend abstraction layer.

This module provides an abstract interface for graph databases and concrete
implementations for different backends (Kuzu, Neo4j, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class QueryExecutor(ABC):
    """Thin abstraction for anything that can execute Cypher-like queries.

    Implemented by GraphBackend and can be satisfied by raw connections that
    expose a compatible ``execute`` method.
    """

    @abstractmethod
    def execute(self, query: str, parameters: dict[str, Any] | None = None) -> Any:
        """Execute a query and return backend-specific results."""
        ...


class GraphBackend(QueryExecutor, ABC):
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
        """Create a node table in Kuzu (idempotent)."""
        fields_str = ", ".join([f"{name} {type_}" for name, type_ in fields.items()])
        create_sql = f"CREATE NODE TABLE IF NOT EXISTS {table_name}({fields_str}, PRIMARY KEY({primary_key}))"
        self.execute(create_sql)

    def create_relationship_table(
        self,
        rel_name: str,
        from_table: str,
        to_table: str,
        properties: dict[str, str] | None = None,
    ) -> None:
        """Create a relationship table in Kuzu (idempotent)."""
        if properties:
            props_str = ", " + ", ".join([f"{name} {type_}" for name, type_ in properties.items()])
        else:
            props_str = ""
        create_rel_sql = f"CREATE REL TABLE IF NOT EXISTS {rel_name}(FROM {from_table} TO {to_table}{props_str})"
        self.execute(create_rel_sql)

    def drop_table(self, table_name: str) -> None:
        """Drop a table in Kuzu."""
        try:
            self.execute(f"DROP TABLE {table_name};")
        except Exception:
            pass

    def insert_node(self, table_name: str, data: dict[str, Any]) -> None:
        """Insert a node in Kuzu.

        DEPRECATED: Use merge_node() instead for incremental graph construction.
        This method creates duplicate nodes and should only be used for initial loads.
        """
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

    def merge_node(
        self, node_type: str, node_data: dict[str, Any], schema_config: Any | None = None
    ) -> tuple[bool, str]:
        """Merge a node into the graph database using MERGE semantics.

        Wrapper around graph_merge.merge_node_in_graph that uses this backend's connection.

        Args:
            node_type: Node label/type
            node_data: Node properties dictionary
            schema_config: Optional schema configuration

        Returns:
            Tuple of (was_created: bool, node_id: str)
        """
        from genai_blueprint.demos.ekg.graph_merge import merge_node_in_graph

        return merge_node_in_graph(
            conn=self.conn,
            node_type=node_type,
            node_data=node_data,
            schema_config=schema_config,
        )

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


def create_in_memory_backend() -> GraphBackend:
    """Create an in-memory graph backend for temporary graphs/tests.

    Currently returns a Kuzu-based backend connected to an in-memory database.
    """
    backend = KuzuBackend()
    backend.connect(":memory:")
    return backend


def create_backend_from_config(config_key: str = "default") -> GraphBackend:
    """Create a graph backend from YAML configuration.

    Reads configuration from global_config()["graph_db"][config_key] and creates
    the appropriate backend with connection parameters.

    Args:
        config_key: Key in graph_db config section

    Returns:
        Connected GraphBackend instance
    """
    from genai_tk.utils.config_mngr import global_config

    config = global_config()
    graph_db_config = config.get("graph_db", {})

    if config_key not in graph_db_config:
        raise ValueError(f"Graph database config '{config_key}' not found. Available: {list(graph_db_config.keys())}")

    db_config = graph_db_config[config_key]
    backend_type = db_config.get("type")
    connection_path = db_config.get("path")

    if not backend_type:
        raise ValueError(f"Missing 'type' in graph_db config for '{config_key}'")
    if not connection_path:
        raise ValueError(f"Missing 'path' in graph_db config for '{config_key}'")

    # Create backend instance
    backend = create_backend(backend_type)

    # Handle different backend types
    if backend_type.lower() == "kuzu":
        # Ensure parent directory exists for Kuzu
        db_path = Path(connection_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        backend.connect(connection_path)
    elif backend_type.lower() == "neo4j":
        # Neo4j connection with credentials
        username = db_config.get("username")
        password = db_config.get("password")
        # Note: Neo4j backend not yet implemented, but config structure is ready
        backend.connect(connection_path)
    else:
        # Generic connection
        backend.connect(connection_path)

    return backend


def get_db_path_from_config(config_key: str = "default") -> Path:
    """Get database path from configuration.

    Args:
        config_key: Key in graph_db config section

    Returns:
        Path to the database
    """
    from genai_tk.utils.config_mngr import global_config

    config = global_config()
    graph_db_config = config.get("graph_db", {})

    if config_key not in graph_db_config:
        raise ValueError(f"Graph database config '{config_key}' not found. Available: {list(graph_db_config.keys())}")

    db_config = graph_db_config[config_key]
    connection_path = db_config.get("path")

    if not connection_path:
        raise ValueError(f"Missing 'path' in graph_db config for '{config_key}'")

    return Path(connection_path)
