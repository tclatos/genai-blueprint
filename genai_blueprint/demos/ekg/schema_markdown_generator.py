"""Generate Markdown schema documentation for knowledge graphs.

This module provides functionality to generate comprehensive, LLM-friendly
Markdown documentation of graph schemas, including node types, relationships,
properties, descriptions from BAML files, and indexed fields.
"""

from __future__ import annotations

import re
from enum import Enum
from functools import lru_cache
from typing import Any, get_args, get_origin

from genai_blueprint.demos.ekg.graph_schema import GraphSchema
from genai_blueprint.demos.ekg.rainbow_subgraph import get_subgraph


def generate_schema_markdown(subgraph_name: str) -> str:
    """Generate an LLM-friendly Markdown string describing the graph schema.

    Includes node types with their fields and descriptions, relationships
    with properties, and indexed fields for vector search.

    Example:
        ```python
        from genai_blueprint.demos.ekg.schema_markdown_generator import generate_schema_markdown
        
        markdown = generate_schema_markdown("opportunity")
        print(markdown)
        ```
    """
    schema = _load_schema(subgraph_name)
    baml_docs = _parse_baml_descriptions()
    node_sections = _build_node_sections(schema, baml_docs)
    rel_sections = _build_relationship_sections(schema, baml_docs)
    indexed_section = _build_indexed_fields_section(schema)

    return _format_markdown(
        subgraph_name=subgraph_name,
        node_sections=node_sections,
        rel_sections=rel_sections,
        indexed_section=indexed_section,
    )


def _load_schema(subgraph_name: str) -> GraphSchema:
    """Load and validate the subgraph schema."""
    try:
        subgraph_impl = get_subgraph(subgraph_name)
        return subgraph_impl.build_schema()
    except ValueError as e:
        raise ValueError(f"Unknown subgraph '{subgraph_name}': {e}")


@lru_cache(maxsize=1)
def _parse_baml_descriptions() -> dict[str, Any]:
    """Parse descriptions from BAML files.
    
    Returns dictionary with:
        - classes: dict[str, str] - Class name to description
        - fields: dict[str, dict[str, str]] - Class to field descriptions
        - enums: dict[str, dict[str, str]] - Enum name to value descriptions
    """
    from genai_blueprint.demos.ekg.baml_client.inlinedbaml import _file_map

    classes: dict[str, str] = {}
    fields: dict[str, dict[str, str]] = {}
    enums: dict[str, dict[str, str]] = {}

    # Exclude client and generator files
    excluded_files = {"clients.baml", "generators.baml"}

    for filename, content in _file_map.items():
        if filename in excluded_files:
            continue

        _parse_baml_content(content, classes, fields, enums)

    return {"classes": classes, "fields": fields, "enums": enums}


def _parse_baml_content(
    content: str,
    classes: dict[str, str],
    fields: dict[str, dict[str, str]],
    enums: dict[str, dict[str, str]],
) -> None:
    """Parse a single BAML file content for descriptions."""
    lines = content.split("\n")
    current_block: str | None = None
    current_block_type: str | None = None  # 'class' or 'enum'
    pending_description: str | None = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Check for standalone @@description before class/enum
        desc_match = re.match(r'@@description\s*\(\s*["\'](.+?)["\']\s*\)', stripped)
        if desc_match:
            pending_description = desc_match.group(1)
            continue

        # Check for class/enum declaration
        block_match = re.match(r"(class|enum)\s+([A-Za-z_]\w*)\s*\{", stripped)
        if block_match:
            current_block_type = block_match.group(1)
            current_block = block_match.group(2)

            # Check if @@description is on the same line or was pending
            inline_desc = re.search(r'@@description\s*\(\s*["\'](.+?)["\']\s*\)', line)
            if inline_desc:
                if current_block_type == "class":
                    classes[current_block] = inline_desc.group(1)
                elif current_block_type == "enum":
                    enums[current_block] = {}
            elif pending_description:
                if current_block_type == "class":
                    classes[current_block] = pending_description
                elif current_block_type == "enum":
                    enums[current_block] = {}
                pending_description = None
            else:
                # Initialize without description
                if current_block_type == "enum":
                    enums[current_block] = {}

            continue

        # Check for closing brace
        if stripped == "}" and current_block:
            current_block = None
            current_block_type = None
            continue

        # Inside a block - parse fields or enum values
        if current_block:
            if current_block_type == "class":
                # Parse field with optional @description
                # Match field_name type_annotation and capture @description if present
                field_match = re.match(r'([A-Za-z_]\w*)\s+([^@\n]+)', stripped)
                if field_match:
                    field_name = field_match.group(1)
                    # Look for @description in the line
                    desc_match = re.search(r'@description\s*\(\s*["\'](.+?)["\']\s*\)', line)
                    if desc_match:
                        field_desc = desc_match.group(1)
                        if current_block not in fields:
                            fields[current_block] = {}
                        fields[current_block][field_name] = field_desc

            elif current_block_type == "enum":
                # Parse enum value with optional @description
                enum_val_match = re.match(
                    r'([A-Za-z_]\w*)(?:\s+@alias\([^)]+\))?(?:\s+@description\s*\(\s*["\'](.+?)["\']\s*\))?',
                    stripped,
                )
                if enum_val_match:
                    enum_val = enum_val_match.group(1)
                    enum_desc = enum_val_match.group(2)
                    if enum_desc and current_block in enums:
                        enums[current_block][enum_val] = enum_desc


def _build_node_sections(schema: GraphSchema, baml_docs: dict[str, Any]) -> list[dict[str, Any]]:
    """Build structured node section data for formatting."""
    sections = []
    # Track embedded classes to exclude from main type listing
    embedded_classes = set()
    
    for node in schema.nodes:
        for _, embedded_class in node.embedded:
            embedded_classes.add(embedded_class.__name__)

    for node in schema.nodes:
        node_name = node.baml_class.__name__
        
        # Skip embedded classes from main listing
        if node_name in embedded_classes:
            continue
        
        # Prefer schema description, fallback to BAML
        description = node.description or baml_docs["classes"].get(node_name, "")

        # Build field information
        field_list = []
        for field_name, field_info in node.baml_class.model_fields.items():
            if field_name not in node.excluded_fields:
                field_type = _humanize_type(field_info.annotation)
                field_desc = baml_docs["fields"].get(node_name, {}).get(field_name, "")
                field_list.append({"name": field_name, "type": field_type, "description": field_desc})

        # Build embedded fields with their nested structure
        embedded_list = []
        for field_name, embedded_class in node.embedded:
            # Get fields of the embedded class
            embedded_fields = []
            for emb_field_name, emb_field_info in embedded_class.model_fields.items():
                emb_field_type = _humanize_type(emb_field_info.annotation)
                emb_field_desc = baml_docs["fields"].get(embedded_class.__name__, {}).get(emb_field_name, "")
                embedded_fields.append({
                    "name": f"{field_name}.{emb_field_name}",
                    "type": emb_field_type,
                    "description": emb_field_desc
                })
            embedded_list.extend(embedded_fields)

        sections.append(
            {
                "name": node_name,
                "description": description,
                "fields": field_list,
                "embedded": embedded_list,
                "index_fields": node.index_fields,
            }
        )

    return sections


def _build_relationship_sections(schema: GraphSchema, baml_docs: dict[str, Any]) -> list[dict[str, Any]]:
    """Build structured relationship section data for formatting."""
    sections = []

    for relation in schema.relations:
        source = relation.from_node.__name__
        dest = relation.to_node.__name__
        description = relation.description

        # Extract properties from p_*_ pattern in to_node
        properties = []
        if hasattr(relation.to_node, "model_fields"):
            for field_name, field_info in relation.to_node.model_fields.items():
                if field_name.startswith("p_") and field_name.endswith("_"):
                    # Extract property name without p_ prefix and _ suffix
                    prop_name = field_name[2:-1]
                    prop_type = _humanize_type(field_info.annotation)
                    prop_desc = baml_docs["fields"].get(dest, {}).get(field_name, "")
                    properties.append({"name": prop_name, "type": prop_type, "description": prop_desc})

        sections.append(
            {
                "name": relation.name,
                "source": source,
                "dest": dest,
                "description": description,
                "properties": properties,
            }
        )

    return sections


def _build_indexed_fields_section(schema: GraphSchema) -> list[str]:
    """Build list of indexed fields in NodeType.field_name format."""
    indexed = []
    for node in schema.nodes:
        node_name = node.baml_class.__name__
        for field in node.index_fields:
            indexed.append(f"{node_name}.{field}")
    return indexed



def _humanize_type(annotation: Any) -> str:
    """Convert Python type annotation to LLM-friendly string.
    
    Converts Pydantic and typing annotations to simplified, readable strings.
    """
    # Handle None/NoneType
    if annotation is type(None):
        return "null"

    # Unwrap Optional
    base_type, is_optional = _unwrap_optional(annotation)

    # Get the actual type to process
    origin = get_origin(base_type)
    args = get_args(base_type)

    # Handle generic types
    if origin is list:
        inner = _humanize_type(args[0]) if args else "any"
        # Remove optional marker from inner type for list display
        inner_clean = inner.replace(" (optional)", "").rstrip("?")
        result = f"{inner_clean}[]"
    elif origin is set:
        inner = _humanize_type(args[0]) if args else "any"
        inner_clean = inner.replace(" (optional)", "").rstrip("?")
        result = f"{inner_clean}[]"
    elif origin is tuple:
        inner = _humanize_type(args[0]) if args else "any"
        inner_clean = inner.replace(" (optional)", "").rstrip("?")
        result = f"{inner_clean}[]"
    elif origin is dict:
        result = "object"
    # Handle basic types
    elif base_type is str:
        result = "string"
    elif base_type is int:
        result = "int"
    elif base_type is float:
        result = "float"
    elif base_type is bool:
        result = "boolean"
    # Handle Enums
    elif isinstance(base_type, type) and issubclass(base_type, Enum):
        result = f"enum {base_type.__name__}"
    # Default to class name
    elif hasattr(base_type, "__name__"):
        result = base_type.__name__
    else:
        result = str(base_type)

    # Add optional marker in parentheses format
    if is_optional:
        result = f"{result} (optional)"

    return result


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    """Unwrap Optional/Union types to get base type and optionality."""
    import types
    from typing import Union
    
    origin = get_origin(annotation)
    
    # Check for Union (including Optional which is Union[T, None])
    # Handle both Union (typing.Union) and UnionType (| syntax)
    if origin is Union or (hasattr(types, 'UnionType') and origin is types.UnionType):
        args = get_args(annotation)
        # Filter out NoneType
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            return non_none_args[0], True
        # Multiple non-None types - return first
        return non_none_args[0] if non_none_args else annotation, True
    
    return annotation, False


def _format_markdown(
    subgraph_name: str,
    node_sections: list[dict[str, Any]],
    rel_sections: list[dict[str, Any]],
    indexed_section: list[str],
) -> str:
    """Format all sections into final Markdown document."""
    lines = [
        f"# Knowledge Graph Schema — Subgraph: {subgraph_name}",
        "",
        "## Node Types",
        "",
    ]

    # Format nodes
    for node in node_sections:
        lines.append(f"### {node['name']}")
        if node["description"]:
            lines.append(f"**Description:** {node['description']}")
            lines.append("")

        if node["fields"]:
            lines.append("**Fields:**")
            for field in node["fields"]:
                field_line = f"- `{field['name']}`: {field['type']}"
                if field["description"]:
                    field_line += f" — {field['description']}"
                lines.append(field_line)
            lines.append("")

        if node["embedded"]:
            lines.append("**Embedded Fields:**")
            for emb in node["embedded"]:
                field_line = f"- `{emb['name']}`: {emb['type']}"
                if emb["description"]:
                    field_line += f" — {emb['description']}"
                lines.append(field_line)
            lines.append("")

    # Format relationships
    lines.extend(["", "## Relationships (Edges)", ""])

    for rel in rel_sections:
        lines.append(f"### {rel['name']}")
        lines.append(f"**Direction:** {rel['source']} → {rel['dest']}")
        if rel["description"]:
            lines.append(f"**Description:** {rel['description']}")
        lines.append("")

        if rel["properties"]:
            lines.append("**Properties:**")
            for prop in rel["properties"]:
                prop_line = f"- `{prop['name']}`: {prop['type']}"
                if prop["description"]:
                    prop_line += f" — {prop['description']}"
                lines.append(prop_line)
            lines.append("")

    # Format indexed fields
    lines.extend(["", "## Indexed Fields", ""])
    if indexed_section:
        lines.append("The following fields are indexed for vector search:")
        lines.append("")
        for field in indexed_section:
            lines.append(f"- `{field}`")
        lines.append("")
    else:
        lines.append("No fields are indexed for vector search.")
        lines.append("")

    return "\n".join(lines)
