from __future__ import annotations

from typing import Any, Dict, List, Tuple

import kuzu
from pydantic import BaseModel
from rich.console import Console

# Import new schema types

console = Console()


# Database helpers


def _get_kuzu_type(annotation: type) -> str:
    """Map Python type annotation to Kuzu type string.

    Args:
        annotation: Python type annotation

    Returns:
        Kuzu type string
    """
    if getattr(annotation, "__origin__", None) is list:
        return "STRING[]"
    elif annotation in (float,):
        return "DOUBLE"
    elif annotation in (int,):
        return "INT64"
    else:
        return "STRING"


def _detect_parent_class(embedded_node, all_nodes: list) -> type[BaseModel] | None:
    """Auto-detect parent class for embedded node based on field path.

    Args:
        embedded_node: The node to be embedded
        all_nodes: All node configurations to search through

    Returns:
        Parent node class or None if not found
    """
    field_path = getattr(
        embedded_node, "_field_path", embedded_node.field_paths[0] if embedded_node.field_paths else None
    )
    if not field_path:
        return None

    # Simple heuristic: find the node whose field_path is a prefix of this one
    field_parts = field_path.split(".")
    if len(field_parts) <= 1:
        return None

    parent_path = ".".join(field_parts[:-1])

    for node in all_nodes:
        node_field_path = getattr(node, "_field_path", node.field_paths[0] if node.field_paths else None)
        if not node.embed_in_parent and node_field_path == parent_path:
            return node.baml_class

    return None


def _find_embedded_data_in_model(root_model: BaseModel, target_class: type[BaseModel]) -> Any:
    """Find data of target_class type within the root model.

    Args:
        root_model: Root model to search in
        target_class: The class type to find

    Returns:
        Instance of target_class or None if not found
    """
    if not hasattr(root_model, "model_fields"):
        return None

    for field_name, field_info in root_model.model_fields.items():
        field_value = getattr(root_model, field_name, None)
        if field_value is None:
            continue

        # Check if this field is an instance of target_class
        if isinstance(field_value, target_class):
            return field_value

        # Check if this field's type annotation matches target_class
        if field_info.annotation == target_class:
            return field_value

    return None


def _add_embedded_fields(parent_data: dict[str, Any], root_model: BaseModel, all_nodes: list, parent_node) -> None:
    """Add embedded node fields to parent record.

    Args:
        parent_data: Parent record dictionary to modify
        root_model: Root model instance for field path resolution
        all_nodes: All node configurations (GraphNodeConfig objects)
        parent_node: Parent node configuration (GraphNodeConfig object)
    """
    # New structure: handle embedded fields from parent_node.embedded
    if hasattr(parent_node, "embedded") and parent_node.embedded:
        # Get the parent instance data
        field_path = getattr(
            parent_node, "_field_path", parent_node.field_paths[0] if parent_node.field_paths else None
        )
        parent_instance = get_field_by_path(root_model, field_path) if field_path else root_model

        for field_name, embedded_class in parent_node.embedded:
            # Get the embedded data from the parent instance
            embedded_data = getattr(parent_instance, field_name, None) if parent_instance else None

            if embedded_data is None:
                continue

            # Convert to dict if needed
            if hasattr(embedded_data, "model_dump"):
                embedded_dict = embedded_data.model_dump()
            elif isinstance(embedded_data, dict):
                embedded_dict = embedded_data
            else:
                continue

            # Add embedded fields with prefix
            prefix = f"{field_name}_"
            for emb_field_name, field_value in embedded_dict.items():
                embedded_field_name = f"{prefix}{emb_field_name}"
                parent_data[embedded_field_name] = field_value

    # Legacy: handle embed_in_parent nodes
    for embedded_node in all_nodes:
        if not embedded_node.embed_in_parent:
            continue

        # Check if this embedded node belongs to this parent
        parent_class = embedded_node.parent_node_class
        if not parent_class:
            parent_class = _detect_parent_class(embedded_node, all_nodes)

        if not parent_class or parent_class != parent_node.baml_class:
            continue

        # Extract embedded data - need to find it in the root model
        field_path = getattr(
            embedded_node, "_field_path", embedded_node.field_paths[0] if embedded_node.field_paths else None
        )
        embedded_data = get_field_by_path(root_model, field_path) if field_path else None
        if embedded_data is None:
            # Try to find the embedded data by searching for the class type in root model
            embedded_data = _find_embedded_data_in_model(root_model, embedded_node.baml_class)
            if embedded_data is None:
                continue

        # Convert to dict if needed
        if hasattr(embedded_data, "model_dump"):
            embedded_dict = embedded_data.model_dump()
        elif isinstance(embedded_data, dict):
            embedded_dict = embedded_data
        else:
            continue

        # Add embedded fields with prefix
        prefix = embedded_node.embed_prefix or f"{embedded_node.baml_class.__name__.lower()}_"
        for field_name, field_value in embedded_dict.items():
            embedded_field_name = f"{prefix}{field_name}"
            parent_data[embedded_field_name] = field_value


def restart_database() -> tuple[kuzu.Database, kuzu.Connection]:
    """Restart the database connection to clear all tables.

    Returns:
        Tuple of (Database, Connection)
    """
    db = kuzu.Database(":memory:")
    conn = kuzu.Connection(db)
    console.print("[yellow]🔄 Database restarted - all tables cleared[/yellow]")
    return db, conn


def create_synthetic_key(data: Dict[str, Any], base_name: str) -> str:
    """Generate a synthetic key when primary key is missing.

    Args:
        data: The node data
        base_name: Node type to prefix the synthetic key

    Returns:
        Generated synthetic key
    """
    return f"{base_name}_{hash(str(sorted(data.items()))) % 10000}"


# Schema


def create_schema(conn: kuzu.Connection, nodes: list, relations: list) -> None:
    """Create node and relationship tables in Kuzu database.

    Creates CREATE NODE TABLE and CREATE REL TABLE statements based on GraphNodeConfig
    and GraphRelationConfig. Handles table drops and recreation for
    idempotency. Embedded nodes have their fields merged into parent tables.

    Args:
        conn: Kuzu database connection
        nodes: List of GraphNodeConfig objects
        relations: List of GraphRelationConfig objects
    """
    # Drop existing rel tables first
    for relation in relations:
        table_name = relation.name
        try:
            conn.execute(f"DROP TABLE {table_name};")
        except Exception:
            pass

    # Drop node tables
    dropped_tables: set[str] = set()
    for node in nodes:
        table_name = node.baml_class.__name__
        if table_name in dropped_tables:
            continue
        try:
            conn.execute(f"DROP TABLE {table_name};")
            dropped_tables.add(table_name)
        except Exception:
            pass

    # Create node tables (skip embedded ones)
    created_tables: set[str] = set()
    embedded_fields_by_parent: dict[str, list[tuple[str, str]]] = {}

    # First, collect embedded fields for each parent (new structure)
    for node in nodes:
        if hasattr(node, "embedded") and node.embedded:
            parent_name = node.baml_class.__name__
            if parent_name not in embedded_fields_by_parent:
                embedded_fields_by_parent[parent_name] = []

            for field_name, embedded_class in node.embedded:
                prefix = f"{field_name}_"
                for emb_field_name, emb_field_info in embedded_class.model_fields.items():
                    embedded_field_name = f"{prefix}{emb_field_name}"
                    kuzu_type = _get_kuzu_type(emb_field_info.annotation)
                    embedded_fields_by_parent[parent_name].append((embedded_field_name, kuzu_type))

    # Legacy: handle embed_in_parent nodes
    for node in nodes:
        if node.embed_in_parent:
            # Find parent node class
            parent_class = node.parent_node_class
            if not parent_class:
                # Auto-detect parent from field_path
                parent_class = _detect_parent_class(node, nodes)

            if parent_class:
                parent_name = parent_class.__name__
                if parent_name not in embedded_fields_by_parent:
                    embedded_fields_by_parent[parent_name] = []

                # Add embedded fields with prefix
                prefix = node.embed_prefix or f"{node.baml_class.__name__.lower()}_"
                for field_name, field_info in node.baml_class.model_fields.items():
                    embedded_field_name = f"{prefix}{field_name}"
                    kuzu_type = _get_kuzu_type(field_info.annotation)
                    embedded_fields_by_parent[parent_name].append((embedded_field_name, kuzu_type))

    for node in nodes:
        if node.embed_in_parent:
            continue  # Skip creating tables for embedded nodes

        table_name = node.baml_class.__name__
        if table_name in created_tables:
            continue

        key_field = node.key
        fields: list[str] = []
        model_fields = node.baml_class.model_fields

        # Add metadata fields first
        fields.append("id STRING")  # UUID primary key
        fields.append("_name STRING")  # Human-readable name from name_from
        fields.append("_created_at STRING")  # ISO timestamp
        fields.append("_updated_at STRING")  # ISO timestamp

        # Add regular fields (excluding any specified excluded_fields)
        for field_name, field_info in model_fields.items():
            if field_name not in node.excluded_fields:
                kuzu_type = _get_kuzu_type(field_info.annotation)
                fields.append(f"{field_name} {kuzu_type}")

        # Add embedded fields if this is a parent table
        if table_name in embedded_fields_by_parent:
            for embedded_field_name, kuzu_type in embedded_fields_by_parent[table_name]:
                fields.append(f"{embedded_field_name} {kuzu_type}")

        fields_str = ", ".join(fields)
        create_sql = f"CREATE NODE TABLE {table_name}({fields_str}, PRIMARY KEY({key_field}))"
        console.print(f"[cyan]Creating node table:[/cyan] {create_sql}")
        conn.execute(create_sql)
        created_tables.add(table_name)

    # Create relationship tables
    for relation in relations:
        from_table = relation.from_node.__name__
        to_table = relation.to_node.__name__
        rel_name = relation.name
        create_rel_sql = f"CREATE REL TABLE {rel_name}(FROM {from_table} TO {to_table})"
        console.print(f"[cyan]Creating relationship table:[/cyan] {create_rel_sql}")
        conn.execute(create_rel_sql)


# Extraction helpers


def _auto_deduce_node_field_path(node_info: NodeInfo, root_model: BaseModel, all_nodes: list[NodeInfo]) -> str | None:
    """Auto-deduce field_path for a node if not provided.

    Args:
        node_info: The node configuration
        root_model: The root model to inspect
        all_nodes: All node configurations for context

    Returns:
        The deduced field path or None for root nodes
    """
    if node_info.field_path is not None:
        return node_info.field_path  # Already set

    # If this is the root model class, no field path needed
    if node_info.baml_class == type(root_model):
        return None

    # Search for field in root model that matches this class
    target_class = node_info.baml_class
    target_class_name = target_class.__name__

    def find_field_path(obj: BaseModel, current_path: str = "") -> str | None:
        """Recursively search for a field that matches the target class."""
        if not hasattr(obj, "model_fields"):
            return None

        for field_name, field_info in obj.model_fields.items():
            field_path = f"{current_path}.{field_name}" if current_path else field_name

            # Check field annotation
            annotation = field_info.annotation

            # Handle List[TargetClass]
            if hasattr(annotation, "__origin__") and annotation.__origin__ is list:
                list_args = getattr(annotation, "__args__", [])
                if list_args and list_args[0] == target_class:
                    return field_path

            # Handle direct TargetClass
            elif annotation == target_class:
                return field_path

            # Handle nested models - search one level deeper
            elif hasattr(annotation, "__origin__") and annotation.__origin__ is not list:
                # Don't recurse too deep to avoid infinite loops
                pass
            elif hasattr(annotation, "model_fields"):
                # This is a nested BaseModel, search inside it
                try:
                    # Create a dummy instance to inspect
                    dummy = annotation.model_construct()
                    nested_path = find_field_path(dummy, field_path)
                    if nested_path:
                        return nested_path
                except Exception:
                    pass

        return None

    return find_field_path(root_model)


def _auto_deduce_relation_paths(
    relation_info: RelationInfo, nodes: list[NodeInfo], root_model: BaseModel
) -> tuple[str | None, str | None]:
    """Auto-deduce from_field_path and to_field_path for a relationship.

    Args:
        relation_info: The relationship configuration
        nodes: All node configurations
        root_model: The root model instance to inspect

    Returns:
        Tuple of (from_field_path, to_field_path)
    """
    from_field_path = relation_info.from_field_path
    to_field_path = relation_info.to_field_path

    # Auto-deduce from_field_path if not provided
    if from_field_path is None:
        # Find the node configuration for from_node
        from_node_info = next((n for n in nodes if n.baml_class == relation_info.from_node), None)
        if from_node_info:
            from_field_path = from_node_info.field_path

    # Auto-deduce to_field_path if not provided
    if to_field_path is None:
        # Try to find a field that matches the target class
        target_class_name = relation_info.to_node.__name__
        target_class_lower = target_class_name.lower()

        # Get the source object to inspect its fields
        source_obj = get_field_by_path(root_model, from_field_path) if from_field_path else root_model

        if source_obj and hasattr(source_obj, "model_fields"):
            # Look for fields that might contain the target type
            for field_name, field_info in source_obj.model_fields.items():
                # Check if field name matches target class (singular or plural)
                if (
                    field_name.lower() == target_class_lower
                    or field_name.lower() == target_class_lower + "s"
                    or field_name.lower() == target_class_lower[:-1]
                    if target_class_lower.endswith("s")
                    else False
                ):
                    # Construct the full path
                    if from_field_path:
                        to_field_path = f"{from_field_path}.{field_name}"
                    else:
                        to_field_path = field_name
                    break

                # Check if the field type annotation matches
                annotation = field_info.annotation
                if hasattr(annotation, "__origin__") and annotation.__origin__ is list:
                    # Handle List[TargetClass]
                    list_args = getattr(annotation, "__args__", [])
                    if list_args and list_args[0] == relation_info.to_node:
                        if from_field_path:
                            to_field_path = f"{from_field_path}.{field_name}"
                        else:
                            to_field_path = field_name
                        break
                elif annotation == relation_info.to_node:
                    # Handle direct TargetClass
                    if from_field_path:
                        to_field_path = f"{from_field_path}.{field_name}"
                    else:
                        to_field_path = field_name
                    break

    return from_field_path, to_field_path


def get_field_by_path(obj: Any, path: str) -> Any:
    """Get an attribute by a dot-separated path.

    Args:
        obj: Root object or dict
        path: Dot path like a.b.c

    Returns:
        Value at that path or None if not found
    """
    try:
        current = obj
        for part in path.split("."):
            if hasattr(current, part):
                current = getattr(current, part)
            elif isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current
    except (AttributeError, KeyError, TypeError):
        return None


def extract_graph_data(model: BaseModel, nodes: list, relations: list) -> Tuple[Dict[str, List[Dict]], List[Tuple]]:
    """Generic extraction of nodes and relationships from any Pydantic model.

    Args:
        model: Pydantic model instance
        nodes: List of GraphNodeConfig objects
        relations: List of GraphRelationConfig objects

    Returns:
        nodes_dict: Mapping of node type to list of property dicts
        relationships: Tuples of (from_type, from_id, to_type, to_id, rel_name)
    """
    nodes_dict: Dict[str, List[Dict]] = {}
    relationships: List[Tuple] = []
    node_registry: Dict[str, set[str]] = {}  # For deduplication: node_type -> set of dedup values
    id_registry: Dict[str, Dict[str, str]] = {}  # For relationships: node_type -> {dedup_value: _id}

    # Field paths are already set as _field_path in create_graph

    # Init buckets
    for node_info in nodes:
        node_type = node_info.baml_class.__name__
        nodes_dict[node_type] = []
        node_registry[node_type] = set()
        id_registry[node_type] = {}

    # Nodes
    for node_info in nodes:
        if node_info.embed_in_parent:
            continue  # Handle embedded nodes separately

        node_type = node_info.baml_class.__name__

        # Process ALL field paths for this node type, not just the first one
        field_paths_to_process = node_info.field_paths if node_info.field_paths else [None]

        for field_path in field_paths_to_process:
            field_data = get_field_by_path(model, field_path) if field_path else model
            if field_data is None:
                continue

            # Check if this field path represents a list
            is_list = (
                node_info.is_list_at_paths.get(field_path, False) if hasattr(node_info, "is_list_at_paths") else False
            )
            items = field_data if is_list else [field_data]

            for item in items:
                if item is None:
                    continue

                if hasattr(item, "model_dump"):
                    item_data = item.model_dump()
                elif isinstance(item, dict):
                    item_data = item.copy()
                else:
                    continue

                # Generate metadata fields FIRST, before removing excluded fields
                import uuid
                from datetime import datetime

                # Generate UUID for id
                item_data["id"] = str(uuid.uuid4())

                # Get _name from name_from using get_name_value
                item_data["_name"] = node_info.get_name_value(item_data, node_type)

                # Filter out excluded fields to avoid complex data issues
                if node_info.excluded_fields:
                    for excluded_field in node_info.excluded_fields:
                        item_data.pop(excluded_field, None)

                # Add embedded fields to this parent record
                _add_embedded_fields(item_data, model, nodes, node_info)

                # Add timestamps
                now = datetime.utcnow().isoformat() + "Z"
                item_data["_created_at"] = now
                item_data["_updated_at"] = now

                # Deduplication - use _name for deduplication if deduplication_key not specified
                if node_info.deduplication_key:
                    dedup_value = item_data.get(node_info.deduplication_key)
                else:
                    # Use _name for deduplication by default
                    dedup_value = item_data.get("_name")

                if dedup_value:
                    # Convert to string to handle unhashable types like dicts
                    dedup_str = str(dedup_value)
                    if dedup_str not in node_registry[node_type]:
                        nodes_dict[node_type].append(item_data)
                        node_registry[node_type].add(dedup_str)
                        # Register id for relationship lookups
                        id_registry[node_type][dedup_str] = item_data["id"]
                else:
                    # No dedup value, always add (but still register id)
                    nodes_dict[node_type].append(item_data)
                    # Use id itself as the registry key if no other dedup available
                    id_registry[node_type][item_data["id"]] = item_data["id"]

    # Relationships
    for relation_info in relations:
        from_type = relation_info.from_node.__name__
        to_type = relation_info.to_node.__name__

        # Skip relationships involving embedded nodes
        from_node_info = next((n for n in nodes if n.baml_class.__name__ == from_type), None)
        to_node_info = next((n for n in nodes if n.baml_class.__name__ == to_type), None)

        if not from_node_info or not to_node_info:
            continue

        # Skip if either node is embedded (no separate table created)
        if from_node_info.embed_in_parent or to_node_info.embed_in_parent:
            continue

        # Get field paths from relation config
        from_field_path = getattr(relation_info, "_from_field_path", None)
        to_field_path = getattr(relation_info, "_to_field_path", None)

        from_data = get_field_by_path(model, from_field_path) if from_field_path else model
        to_data = get_field_by_path(model, to_field_path) if to_field_path else None
        if from_data is None or to_data is None:
            # Skip if we couldn't find the target data
            continue

        # Get dedup value for from_node to lookup id
        from_dict = from_data.model_dump() if hasattr(from_data, "model_dump") else from_data

        # Get dedup value for from node
        if from_node_info.deduplication_key:
            from_dedup_value = from_dict.get(from_node_info.deduplication_key)
        else:
            # Use _name as dedup value (same logic as in node extraction)
            from_dedup_value = from_node_info.get_name_value(from_dict, from_type)

        from_dedup_str = str(from_dedup_value) if from_dedup_value else None
        from_id = id_registry[from_type].get(from_dedup_str) if from_dedup_str else None

        if not from_id:
            continue  # Skip if we can't find the from node id

        to_items = to_data if isinstance(to_data, list) else [to_data]
        for to_item in to_items:
            if to_item is None:
                continue
            to_dict = to_item.model_dump() if hasattr(to_item, "model_dump") else to_item

            # Get dedup value for to node
            if to_node_info.deduplication_key:
                to_dedup_value = to_dict.get(to_node_info.deduplication_key)
            else:
                # Use _name as dedup value
                to_dedup_value = to_node_info.get_name_value(to_dict, to_type)

            to_dedup_str = str(to_dedup_value) if to_dedup_value else None
            to_id = id_registry[to_type].get(to_dedup_str) if to_dedup_str else None

            if to_id:
                # Use id values for relationships
                relationships.append((from_type, from_id, to_type, to_id, relation_info.name))

    return nodes_dict, relationships


# Loading


def load_graph_data(
    conn: kuzu.Connection, nodes_dict: Dict[str, List[Dict]], relationships: List[Tuple], nodes: list
) -> None:
    """Load nodes and relationships into Kuzu database.

    Uses CREATE statements to insert data.

    Args:
        conn: Kuzu database connection
        nodes_dict: Dictionary mapping node types to list of node data dicts
        relationships: List of relationship tuples
        nodes: List of GraphNodeConfig objects
    """
    # Nodes
    for node_type, node_list in nodes_dict.items():
        if not node_list:
            continue
        console.print(f"[green]Loading {len(node_list)} {node_type} nodes...[/green]")
        for node_data in node_list:
            # Find the node configuration to get the primary key field
            node_info = next((n for n in nodes if n.baml_class.__name__ == node_type), None)
            primary_key_field = node_info.key if node_info else None

            cleaned_data: Dict[str, str] = {}
            for key, value in node_data.items():
                if value is None:
                    # Skip NULL primary keys to avoid constraint violations
                    if key == primary_key_field:
                        console.print(f"[yellow]Warning: Skipping {node_type} node with NULL primary key[/yellow]")
                        break
                    cleaned_data[key] = "NULL"
                elif isinstance(value, str):
                    escaped = value.replace("'", "\\'")
                    cleaned_data[key] = f"'{escaped}'"
                elif isinstance(value, list):
                    str_list: list[str] = []
                    for v in value:
                        # Handle enums and complex objects in lists
                        if hasattr(v, "value"):  # Enum
                            clean_v = str(v.value)
                        elif hasattr(v, "__dict__") or isinstance(v, dict):  # Complex object
                            clean_v = str(v).replace("'", "\\'").replace('"', '\\"')
                        else:
                            clean_v = str(v)
                        escaped_v = clean_v.replace("'", "\\'")
                        str_list.append(f"'{escaped_v}'")
                    cleaned_data[key] = f"[{','.join(str_list)}]"
                elif hasattr(value, "value"):  # Handle Enum types
                    escaped = str(value.value).replace("'", "\\'")
                    cleaned_data[key] = f"'{escaped}'"
                elif hasattr(value, "__dict__") or isinstance(value, dict):  # Handle complex objects
                    # Convert complex objects to JSON-like strings, but clean them
                    clean_str = str(value).replace("'", "\\'").replace('"', '\\"')
                    # Remove any enum representations like <EnumName.VALUE: 'value'>
                    import re

                    clean_str = re.sub(
                        r"<[^>]+>", lambda m: m.group(0).split("'")[1] if "'" in m.group(0) else m.group(0), clean_str
                    )
                    cleaned_data[key] = f"'{clean_str}'"
                else:
                    cleaned_data[key] = str(value)
            else:
                # This else clause is executed only if the for loop completes without break
                fields = ", ".join([f"{k}: {v}" for k, v in cleaned_data.items()])
                create_sql = f"CREATE (:{node_type} {{{fields}}})"
                try:
                    conn.execute(create_sql)
                except Exception as e:
                    console.print(f"[red]Error creating {node_type} node:[/red] {e}")
                    console.print(f"[dim]SQL: {create_sql}[/dim]")

    # Relationships - use _id for all node references
    console.print(f"[green]Loading {len(relationships)} relationships...[/green]")
    for from_type, from_id, to_type, to_id, rel_name in relationships:
        from_id_escaped = from_id.replace("'", "\\'")
        to_id_escaped = to_id.replace("'", "\\'")

        match_sql = f"""
        MATCH (from:{from_type}), (to:{to_type})
        WHERE from.id = '{from_id_escaped}'
          AND to.id = '{to_id_escaped}'
        CREATE (from)-[:{rel_name}]->(to)
        """
        try:
            conn.execute(match_sql)
        except Exception as e:
            console.print(f"[red]Error creating {rel_name} relationship:[/red] {e}")
            console.print(f"[dim]SQL: {match_sql}[/dim]")


# Orchestration
# Orchestration


def create_graph(
    conn: kuzu.Connection,
    model: BaseModel,
    schema_config,
    relations=None,
) -> tuple[Dict[str, List[Dict]], List[Tuple]]:
    """Create a knowledge graph from a Pydantic model in Kuzu database.

    Args:
        conn: Kuzu database connection
        model: Root instance to convert
        schema_config: GraphSchema object with node and relationship configurations
        relations: Ignored (kept for compatibility)

    Returns:
        nodes_dict and relationships that were used to populate the graph
    """
    # Check if this is the new GraphSchema format
    if not hasattr(schema_config, "nodes") or not hasattr(schema_config, "relations"):
        raise ValueError("create_graph now only accepts GraphSchema objects. Please update your configuration.")

    schema = schema_config
    console.print("[green]Using GraphSchema format[/green]")

    # Print schema summary
    try:
        schema.print_schema_summary()
    except Exception:
        console.print(f"[yellow]Schema with {len(schema.nodes)} nodes and {len(schema.relations)} relations[/yellow]")

    console.print("[bold]Creating database schema...[/bold]")

    # Prepare nodes with computed is_list flags
    for node_config in schema.nodes:
        field_paths = node_config.field_paths or []
        field_path = field_paths[0] if field_paths else None

        # Check if field is a list by looking at the model field annotation
        is_list = False
        if field_path and hasattr(model, "model_fields"):
            try:
                field_obj = get_field_by_path(model, field_path)
                if isinstance(field_obj, list):
                    is_list = True
                # Also check the field annotation in the model
                parts = field_path.split(".")
                current_model = type(model)
                for part in parts[:-1]:
                    if hasattr(current_model, "model_fields") and part in current_model.model_fields:
                        field_info = current_model.model_fields[part]
                        if hasattr(field_info.annotation, "__origin__"):
                            current_model = field_info.annotation.__args__[0]
                # Check final field
                if hasattr(current_model, "model_fields") and parts[-1] in current_model.model_fields:
                    field_info = current_model.model_fields[parts[-1]]
                    if hasattr(field_info.annotation, "__origin__") and field_info.annotation.__origin__ is list:
                        is_list = True
            except:
                pass

        # Store is_list as a dynamic attribute
        node_config._is_list = is_list
        node_config._field_path = field_path

    # Prepare relations with field paths
    for relation_config in schema.relations:
        if relation_config.field_paths:
            from_path, to_path = relation_config.field_paths[0]
            relation_config._from_field_path = from_path
            relation_config._to_field_path = to_path
        else:
            relation_config._from_field_path = None
            relation_config._to_field_path = None

    console.print("[cyan]Creating database tables...[/cyan]")
    create_schema(conn, schema.nodes, schema.relations)

    console.print("[cyan]Extracting and loading data...[/cyan]")
    nodes_dict, relationships = extract_graph_data(model, schema.nodes, schema.relations)
    load_graph_data(conn, nodes_dict, relationships, schema.nodes)

    console.print("\n[bold green]Graph creation complete![/bold green]")
    total_nodes = sum(len(node_list) for node_list in nodes_dict.values())
    console.print(f"[green]Total nodes:[/green] {total_nodes}")
    console.print(f"[green]Total relationships:[/green] {len(relationships)}")

    return nodes_dict, relationships


class KnowledgeGraphExtractor:
    """Extract graph data from Kuzu database for visualization."""

    def __init__(self, database_path: str):
        """Initialize with database path.

        Args:
            database_path: Path to Kuzu database file
        """
        self.database_path = database_path
        self.db = kuzu.Database(database_path)
        self.conn = kuzu.Connection(self.db)

    def extract_graph_for_visualization(self) -> tuple[list[tuple[str, dict]], list[tuple[str, str, str, dict]]]:
        """Extract nodes and relationships from the database for visualization.

        Returns:
            Tuple of (nodes_list, relationships_list) where:
            - nodes_list: List of (node_id, properties_dict) tuples
            - relationships_list: List of (source_id, target_id, relationship_name, properties_dict) tuples
        """
        try:
            # Import the HTML visualization function
            from genai_blueprint.demos.ekg.kuzu_graph_html import _fetch_graph_data

            # Use the existing data fetching logic
            nodes_data, edges_data = _fetch_graph_data(self.conn)

            return nodes_data, edges_data

        except Exception as e:
            console.print(f"[red]Error extracting graph data:[/red] {e}")
            return [], []
