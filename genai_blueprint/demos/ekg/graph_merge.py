"""Generic graph node merging utilities for incremental knowledge graph construction.

This module provides utilities to merge nodes into a Kuzu graph database using pure
Cypher MERGE statements. It supports incremental addition of documents by merging
nodes based on a configurable key field (default: _name) and preserving creation
timestamps while updating modification timestamps.

The merging strategy follows these principles:
- Nodes are matched by a merge_on_field (default: _name)
- On first creation, all properties plus _created_at and _updated_at are set
- On subsequent matches, only _updated_at is refreshed
- No APOC dependencies - uses pure Cypher only
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from genai_tk.core.prompts import dedent_ws
from rich.console import Console

console = Console()


def _format_value_for_cypher(value: Any) -> str:
    """Format a Python value for use in Cypher queries.

    Handles strings (with escaping), lists, None, booleans, and numbers
    according to Cypher syntax requirements.

    Args:
        value: Python value to format

    Returns:
        Formatted string ready for Cypher query insertion
    """
    if value is None:
        return "NULL"
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, str):
        # Escape single quotes for Cypher
        escaped = value.replace("'", "\\'")
        return f"'{escaped}'"
    elif isinstance(value, list):
        # Recursively format list elements
        formatted_items = [_format_value_for_cypher(item) for item in value]
        return f"[{', '.join(formatted_items)}]"
    elif isinstance(value, (int, float)):
        return str(value)
    elif hasattr(value, "value"):  # Enum types
        escaped = str(value.value).replace("'", "\\'")
        return f"'{escaped}'"
    else:
        # Complex objects - convert to string
        escaped = str(value).replace("'", "\\'")
        return f"'{escaped}'"


def build_merge_query(
    node_type: str,
    node_data: dict[str, Any],
    key_field: str = "id",
    merge_on_field: str = "_name",
) -> tuple[str, str]:
    """Build queries for upserting a node using MATCH + conditional CREATE.

    Since Kuzu doesn't support MERGE with ON CREATE/ON MATCH, we use two queries:
    1. Check if node exists (MATCH)
    2. Either UPDATE or CREATE based on existence

    Args:
        node_type: Label/type of the node
        node_data: Dictionary of node properties
        key_field: Primary key field name
        merge_on_field: Field to match on for merging

    Returns:
        Tuple of (check_query, upsert_query)
    """
    # Get the merge value
    merge_value = node_data.get(merge_on_field)
    if merge_value is None:
        raise ValueError(f"Node data missing required merge field '{merge_on_field}'")

    # Generate current timestamp
    timestamp = datetime.utcnow().isoformat() + "Z"

    # Format merge value
    merge_value_formatted = _format_value_for_cypher(merge_value)

    # Query 1: Check if node exists and get its id
    check_query = dedent_ws(f"""
        MATCH (n:{node_type} {{{merge_on_field}: {merge_value_formatted}}})
        RETURN n.{key_field} as id, n._created_at as created_at
        LIMIT 1
        """)

    # Query 2a: Update existing node (timestamp only)
    # Query 2b: Create new node with all properties
    # We'll return a template that the caller will use based on check results

    # Build properties for CREATE
    create_props = []
    for key, value in node_data.items():
        formatted_value = _format_value_for_cypher(value)
        create_props.append(f"{key}: {formatted_value}")

    # Add timestamps
    create_props.append(f"_created_at: '{timestamp}'")
    create_props.append(f"_updated_at: '{timestamp}'")

    props_str = ", ".join(create_props)

    # Return both check query and upsert info
    # The caller will decide which operation to perform
    return check_query.strip(), props_str


def merge_node_in_graph(
    conn: Any,
    node_type: str,
    node_data: dict[str, Any],
    schema_config: Any | None = None,
    merge_on_field: str = "_name",
) -> tuple[bool, str]:
    """Merge a single node into the graph database.

    Executes a check-then-upsert operation: first checks if node exists,
    then either updates timestamp or creates new node.

    Args:
        conn: Graph database connection (kuzu.Connection or similar)
        node_type: Node label/type
        node_data: Node properties dictionary
        schema_config: Optional schema configuration
        merge_on_field: Field to match nodes on

    Returns:
        Tuple of (was_created: bool, node_id: str)
    """
    try:
        timestamp = datetime.utcnow().isoformat() + "Z"
        # merge_value = node_data.get(merge_on_field)
        # merge_value_formatted = _format_value_for_cypher(merge_value)

        # Build queries
        check_query, props_str = build_merge_query(
            node_type=node_type,
            node_data=node_data,
            key_field="id",
            merge_on_field=merge_on_field,
        )

        # Step 1: Check if node exists
        result = conn.execute(check_query)
        df = result.get_as_df()

        if not df.empty:
            # Node exists - update timestamp only
            row = df.iloc[0]
            existing_id = str(row["id"])

            # Update _updated_at timestamp
            update_query = dedent_ws(f"""
                MATCH (n:{node_type})
                WHERE n.id = '{existing_id.replace("'", "\\'")}'
                SET n._updated_at = '{timestamp}'
                RETURN n.id as id
                """)
            conn.execute(update_query)
            return False, existing_id
        else:
            # Node doesn't exist - create it
            create_query = f"CREATE (n:{node_type} {{{props_str}}}) RETURN n.id as id"
            result = conn.execute(create_query)
            df = result.get_as_df()

            if df.empty:
                console.print(f"[yellow]Warning: CREATE returned no ID for {node_type}[/yellow]")
                return True, ""

            node_id = str(df.iloc[0]["id"])
            return True, node_id

    except Exception as e:
        console.print(f"[red]Error merging {node_type} node:[/red] {e}")
        console.print(f"[dim]Node data: {node_data.get(merge_on_field, 'unknown')}[/dim]")
        raise


def merge_nodes_batch(
    conn: Any,
    nodes_dict: dict[str, list[dict[str, Any]]],
    schema_config: Any | None = None,
    merge_on_field: str = "_name",
) -> tuple[dict[str, dict[str, int]], dict[tuple[str, str], str]]:
    """Merge multiple nodes into the graph database in batch.

    Processes all nodes by type, tracking statistics and building an ID mapping
    for relationship creation.

    Args:
        conn: Graph database connection (kuzu.Connection or similar)
        nodes_dict: Mapping of node_type to list of node data dicts
        schema_config: Optional schema configuration
        merge_on_field: Field to match nodes on

    Returns:
        Tuple of:
        - Statistics dict: {node_type: {created, matched, total}}
        - ID mapping: {(node_type, original_id): merged_global_id}
    """
    stats: dict[str, dict[str, int]] = {}
    id_mapping: dict[tuple[str, str], str] = {}

    for node_type, node_list in nodes_dict.items():
        if not node_list:
            continue

        console.print(f"[cyan]Merging {len(node_list)} {node_type} nodes...[/cyan]")

        type_stats = {"created": 0, "matched": 0, "total": len(node_list)}

        for node_data in node_list:
            # Get original ID before merge
            original_id = node_data.get("id", "")

            # Merge the node
            was_created, merged_id = merge_node_in_graph(
                conn=conn,
                node_type=node_type,
                node_data=node_data,
                schema_config=schema_config,
                merge_on_field=merge_on_field,
            )

            # Update statistics
            if was_created:
                type_stats["created"] += 1
            else:
                type_stats["matched"] += 1

            # Register ID mapping for relationship creation
            if original_id and merged_id:
                id_mapping[(node_type, original_id)] = merged_id

        stats[node_type] = type_stats
        console.print(
            f"[green]  ✓ {node_type}: {type_stats['created']} created, {type_stats['matched']} matched[/green]"
        )

    return stats, id_mapping
