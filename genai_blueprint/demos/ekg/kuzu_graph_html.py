"""Generate an interactive HTML visualization of a Kuzu graph from a given connection.

This module is standalone (no Cognee dependencies). It queries nodes and edges
from the connected Kuzu database, builds a simple JSON model, and embeds it in
an HTML page rendered with D3 force-directed layout.

Usage example:
```
from kuzu import Database, Connection
from kuzu_graph_html import generate_kuzu_graph_html
from graph_schema import GraphSchema

db = Database("/path/to/graph.db")
conn = Connection(db)
# Option 1: Use with GraphSchema
html = generate_kuzu_graph_html(conn, "/tmp/graph_visualization.html")
# Option 2: Pass legacy format configs (auto-detected)
html = generate_kuzu_graph_html(conn, "/tmp/graph_visualization.html", legacy_nodes, legacy_relations)
print("Wrote:", "/tmp/graph_visualization.html")
```
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import kuzu  # Requires the `kuzu` package

# Import new schema types

# from genai_blueprint.demos.ekg.graph_schema import GraphNodeConfig, GraphRelationConfig, GraphSchema


def _generate_node_id(node_type: str, node_name: str, max_length: int = 50) -> str:
    """Generate a consistent node ID from node type and name.

    Args:
        node_type: The node type/table name
        node_name: The node name/display name
        max_length: Maximum length for the ID

    Returns:
        A consistent node ID string
    """
    # Clean the name for use in ID
    clean_name = str(node_name).replace(" ", "_").replace("/", "_").replace("\n", "_")
    # Create ID and ensure it doesn't exceed max length
    node_id = f"{node_type}_{clean_name}"
    if len(node_id) > max_length:
        # Truncate but keep the type intact
        available_length = max_length - len(node_type) - 1  # -1 for the underscore
        if available_length > 0:
            node_id = f"{node_type}_{clean_name[:available_length]}"
        else:
            node_id = node_type[:max_length]
    return node_id


def _get_node_raw_name(node_dict: dict[str, Any], node_type: str) -> str:
    """Extract the raw name for a node without truncation (for ID generation).

    Args:
        node_dict: Node properties dictionary
        node_type: The node type/table name

    Returns:
        Raw name for the node (no truncation)
    """
    # PRIORITY 1: Check for our custom _name field first
    if "_name" in node_dict and node_dict["_name"] is not None:
        value = str(node_dict["_name"]).strip()
        if value:
            return value

    # PRIORITY 2: Common name fields to check in order of preference
    name_fields = ["name", "title", "description", "label", "id"]

    for field in name_fields:
        if field in node_dict and node_dict[field] is not None:
            value = str(node_dict[field]).strip()
            if value:
                return value

    # PRIORITY 3: If no name field found, use the first non-empty string field
    for key, value in node_dict.items():
        if isinstance(value, str) and value.strip() and key not in ["type", "id", "_name"]:
            return str(value)

    # Fallback to node type
    return node_type


def _get_node_display_name(node_dict: dict[str, Any], node_type: str, max_length: int = 30) -> str:
    """Generate a display name for a node based on its properties.

    Args:
        node_dict: Node properties dictionary
        node_type: The node type/table name
        max_length: Maximum length for the display name

    Returns:
        Display name for the node
    """
    # Get the raw name first
    raw_name = _get_node_raw_name(node_dict, node_type)

    # Apply truncation only for display
    if len(raw_name) > max_length:
        return raw_name[:max_length] + "..."
    return raw_name

    # If no name field found, use the first non-empty string field
    for key, value in node_dict.items():
        if isinstance(value, str) and value.strip() and key not in ["type", "id"]:
            truncated = str(value)[:max_length]
            return truncated + ("..." if len(str(value)) > max_length else "")

    # Fallback to node type
    return node_type


def _get_node_color(node_type: str, custom_colors: dict[str, str] | None = None) -> str:
    """Get color for a node type.

    Args:
        node_type: The node type/table name
        custom_colors: Optional custom color mapping

    Returns:
        Hex color code for the node
    """
    if custom_colors and node_type in custom_colors:
        return custom_colors[node_type]

    # Generate a consistent color based on node type hash
    import hashlib

    # Create a hash of the node type
    hash_object = hashlib.md5(node_type.encode())
    hex_hash = hash_object.hexdigest()

    # Use first 6 characters as color, but ensure it's not too dark
    color = "#" + hex_hash[:6]

    # Brighten the color if it's too dark
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)

    # Ensure minimum brightness
    min_brightness = 100
    if r < min_brightness:
        r = min(255, r + min_brightness)
    if g < min_brightness:
        g = min(255, g + min_brightness)
    if b < min_brightness:
        b = min(255, b + min_brightness)

    return f"#{r:02x}{g:02x}{b:02x}"


def _fetch_graph_data(
    connection: kuzu.Connection,
    node_configs: list | None = None,
    relation_configs: list | None = None,
) -> tuple[list[tuple[str, dict]], list[tuple[str, str, str, dict]]]:
    """Fetch all nodes and edges from the Kuzu database via the provided connection.

    Args:
        connection: Kuzu database connection
        node_configs: Optional list of node configurations (legacy or new format)
        relation_configs: Optional list of relation configurations (legacy or new format)

    Returns:
        The function returns two lists:
        - nodes: list of (node_id, properties_dict)
        - edges: list of (source_id, target_id, relationship_name, properties_dict)
    """
    nodes: list[tuple[str, dict]] = []
    edges: list[tuple[str, str, str, dict]] = []

    # Get all tables first to understand the schema
    try:
        tables_result = connection.execute("CALL show_tables() RETURN *")
        tables_df = tables_result.get_as_df()

        node_tables = []

        for _, row in tables_df.iterrows():
            table_name = row["name"]
            table_type = row["type"]
            if table_type == "NODE":
                node_tables.append(table_name)

        # Create a mapping to store UUID to node data for relationship matching
        uuid_to_node_data = {}

        # Fetch nodes from all node tables using simple RETURN n query
        for table_name in node_tables:
            try:
                # Always use simple query to avoid field extraction issues
                nodes_query = f"MATCH (n:{table_name}) RETURN n"
                nodes_result = connection.execute(nodes_query)
                result_df = nodes_result.get_as_df()

                for idx, row in result_df.iterrows():
                    node_dict = {}

                    # Extract node data from the first column (the node object)
                    node_obj = row.iloc[0] if len(row) > 0 else None

                    if isinstance(node_obj, dict):
                        # Handle dictionary-based results (most common)
                        for key, val in node_obj.items():
                            # Keep metadata fields like _name, _created_at, _updated_at
                            # but skip Kuzu internal fields like _id, _label
                            if key in ("_name", "_created_at", "_updated_at"):
                                node_dict[key] = str(val).strip() if str(val).strip() else str(val)
                            elif not key.startswith("_") and val is not None:
                                node_dict[key] = str(val).strip() if str(val).strip() else str(val)
                    else:
                        # Handle object-based results (fallback)
                        try:
                            for attr in dir(node_obj):
                                if not attr.startswith("_") and hasattr(node_obj, attr):
                                    val = getattr(node_obj, attr)
                                    if val is not None and not callable(val):
                                        node_dict[attr] = str(val).strip() if str(val).strip() else str(val)
                        except Exception:
                            # Last resort: skip this node
                            continue

                    # Skip empty nodes
                    if not node_dict:
                        continue

                    # Generate display name and add node metadata
                    node_name = _get_node_display_name(node_dict, table_name)
                    node_dict["type"] = table_name
                    node_dict["name"] = node_name

                    # Generate UUID-based ID for absolute uniqueness and consistency
                    node_uuid = str(uuid.uuid4())

                    # Store mapping for relationship resolution
                    # Use Kuzu internal ID for perfect consistency
                    kuzu_id = None
                    if isinstance(node_obj, dict) and "_id" in node_obj:
                        kuzu_id = str(node_obj["_id"])  # Use internal Kuzu ID as key

                    if kuzu_id:
                        uuid_to_node_data[kuzu_id] = {"uuid": node_uuid, "type": table_name, "node_dict": node_dict}

                    nodes.append((node_uuid, node_dict))

            except Exception as e:
                print(f"Error fetching nodes from {table_name}: {e}")
                continue

        # If no nodes, return early
        if not nodes:
            return [], []

        # UUID mapping complete

        # Fetch relationships using explicit queries
        try:
            # Try to get all relationships - basic Kuzu syntax
            rel_query = "MATCH (n)-[r]->(m) RETURN n, r, m"
            rel_result = connection.execute(rel_query)
            rel_df = rel_result.get_as_df()

            for _, row in rel_df.iterrows():
                # Extract source and destination node data
                src_node = row["n"]
                dst_node = row["m"]
                rel_obj = row["r"]

                # Get relationship type from relationship object (Kuzu returns dict)
                rel_type = "RELATED_TO"
                edge_props = {}
                if isinstance(rel_obj, dict):
                    if "_label" in rel_obj:
                        rel_type = rel_obj["_label"]
                    # Extract edge properties (non-internal fields)
                    for key, value in rel_obj.items():
                        if not key.startswith("_") and value is not None:
                            edge_props[key] = value
                elif hasattr(rel_obj, "__class__"):
                    rel_type = rel_obj.__class__.__name__.replace("Relationship", "").replace("Record", "")
                    if not rel_type or rel_type == "object":
                        rel_type = "RELATED_TO"

                # Extract node types and names from dictionary-based Kuzu results
                def extract_node_info(node_obj) -> tuple[str, str]:
                    """Extract node type and name from a Kuzu node object (dictionary)."""
                    node_type = "Unknown"
                    node_name = "unknown"

                    # Handle dictionary-based Kuzu results
                    if isinstance(node_obj, dict):
                        # Get node type from _label
                        if "_label" in node_obj:
                            node_type = node_obj["_label"]

                        # Create a clean dictionary for name extraction (exclude internal Kuzu fields)
                        node_dict = {}
                        for key, value in node_obj.items():
                            if not key.startswith("_") and value is not None:
                                node_dict[key] = value

                        if node_dict:
                            node_name = _get_node_raw_name(node_dict, node_type)
                    else:
                        # Fallback for object-based results (if any)
                        if hasattr(node_obj, "__class__"):
                            class_name = node_obj.__class__.__name__
                            if class_name != "object":
                                node_type = class_name

                        # Extract name using attribute access
                        node_dict = {}
                        for attr in dir(node_obj):
                            if not attr.startswith("_") and hasattr(node_obj, attr):
                                try:
                                    value = getattr(node_obj, attr)
                                    if value is not None and not callable(value):
                                        node_dict[attr] = value
                                except Exception:
                                    continue

                        if node_dict:
                            node_name = _get_node_raw_name(node_dict, node_type)

                    return node_type, node_name

                # Extract Kuzu internal IDs for perfect matching
                src_kuzu_id = None
                dst_kuzu_id = None

                if isinstance(src_node, dict) and "_id" in src_node:
                    src_kuzu_id = str(src_node["_id"])
                if isinstance(dst_node, dict) and "_id" in dst_node:
                    dst_kuzu_id = str(dst_node["_id"])

                src_uuid = None
                dst_uuid = None

                if src_kuzu_id and src_kuzu_id in uuid_to_node_data:
                    src_uuid = uuid_to_node_data[src_kuzu_id]["uuid"]

                if dst_kuzu_id and dst_kuzu_id in uuid_to_node_data:
                    dst_uuid = uuid_to_node_data[dst_kuzu_id]["uuid"]

                # Only add if we have valid UUIDs for both nodes
                if src_uuid and dst_uuid:
                    edges.append((src_uuid, dst_uuid, rel_type, edge_props))

        except Exception as e:
            print(f"Error fetching relationships: {e}")
            print(f"Error in schema-aware relationship extraction: {e}")

        # Note: UUID-based IDs ensure all relationships are valid

        # If we have nodes but no relationships and relation_configs are provided,
        # we could potentially create logical connections based on the relation configs
        # However, for a truly generic solution, we'll just use what we found

    except Exception as e:
        print(f"Error in _fetch_graph_data: {e}")
        return [], []

    return nodes, edges


def generate_kuzu_graph_html(
    connection: kuzu.Connection,
    destination_file_path: str | None = None,
    node_configs: list | None = None,
    relation_configs: list | None = None,
    custom_colors: dict[str, str] | None = None,
) -> str:
    """Generate an HTML graph visualization from a Kuzu connection.

    Args:
        connection: An active kuzu.Connection connected to a database that uses
            a schema with Node(id, name, type, properties) and EDGE(relationship_name, properties).
        destination_file_path: Optional path to write the HTML file. If omitted,
            the file will be saved as "graph_visualization.html" in the user's home directory.
        node_configs: Optional list of node configurations (legacy or new format)
        relation_configs: Optional list of relation configurations (legacy or new format)
        custom_colors: Optional mapping of node types to hex color codes

    Returns:
        The HTML content as a string.
    """
    nodes_data, edges_data = _fetch_graph_data(connection, node_configs, relation_configs)

    # Build visualization model using generic color assignment

    nodes_list: list[dict[str, Any]] = []
    for node_id, node_info in nodes_data:
        node_info = dict(node_info)  # shallow copy
        node_info["id"] = str(node_id)
        node_type = node_info.get("type", "Unknown")
        node_info["color"] = _get_node_color(node_type, custom_colors)
        node_info["name"] = node_info.get("name", str(node_id))
        # Trim noisy timestamp fields if present
        node_info.pop("updated_at", None)
        node_info.pop("created_at", None)
        nodes_list.append(node_info)

    links_list: list[dict[str, Any]] = []
    for source, target, relation, edge_info in edges_data:
        source_s = str(source)
        target_s = str(target)

        # Extract weight variations
        all_weights: dict[str, float] = {}
        primary_weight: float | None = None
        edge_info = edge_info or {}

        if "weight" in edge_info:
            try:
                primary_weight = float(edge_info["weight"])  # best effort
                all_weights["default"] = primary_weight
            except (TypeError, ValueError):
                pass

        if "weights" in edge_info and isinstance(edge_info["weights"], dict):
            for k, v in edge_info["weights"].items():
                try:
                    all_weights[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue
            if primary_weight is None and all_weights:
                primary_weight = next(iter(all_weights.values()))

        for key, value in edge_info.items():
            if key.startswith("weight_"):
                try:
                    all_weights[key[7:]] = float(value)
                except (TypeError, ValueError):
                    continue

        links_list.append(
            {
                "source": source_s,
                "target": target_s,
                "relation": relation,
                "weight": primary_weight,
                "all_weights": all_weights,
                "relationship_type": edge_info.get("relationship_type"),
                "edge_info": edge_info,
            }
        )

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <script src="https://d3js.org/d3.v5.min.js"></script>
        <style>
            body, html { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: linear-gradient(90deg, #101010, #1a1a2e); color: white; font-family: 'Inter', sans-serif; }

            svg { width: 100vw; height: 100vh; display: block; }
            .links line { stroke: rgba(255, 255, 255, 0.4); stroke-width: 2px; }
            .links line.weighted { stroke: rgba(255, 215, 0, 0.7); }
            .links line.multi-weighted { stroke: rgba(0, 255, 127, 0.8); }
            .nodes circle { stroke: white; stroke-width: 0.5px; filter: drop-shadow(0 0 5px rgba(255,255,255,0.3)); }
            .node-label { font-size: 8px; font-weight: bold; fill: white; text-anchor: middle; dominant-baseline: middle; font-family: 'Inter', sans-serif; pointer-events: none; }
            .edge-label { font-size: 3px; fill: rgba(255, 255, 255, 0.7); text-anchor: middle; dominant-baseline: middle; font-family: 'Inter', sans-serif; pointer-events: none; }
            
            .tooltip {
                position: absolute;
                text-align: left;
                padding: 8px;
                font-size: 10px;
                background: rgba(0, 0, 0, 0.9);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                pointer-events: none;
                opacity: 0;
                transition: opacity 0.2s;
                z-index: 1000;
                max-width: 500px;
                word-wrap: break-word;
                max-height: 80vh;
                overflow-y: auto;
            }
        </style>
    </head>
    <body>
        <svg></svg>
        <div class="tooltip" id="tooltip"></div>
        <script>
            var nodes = {nodes};
            var links = {links};

            var svg = d3.select("svg"),
                width = window.innerWidth,
                height = window.innerHeight;

            var container = svg.append("g");
            var tooltip = d3.select("#tooltip");

            var simulation = d3.forceSimulation(nodes)
                .force("link", d3.forceLink(links).id(d => d.id).strength(0.1))
                .force("charge", d3.forceManyBody().strength(-275))
                .force("center", d3.forceCenter(width / 2, height / 2))
                .force("x", d3.forceX().strength(0.1).x(width / 2))
                .force("y", d3.forceY().strength(0.1).y(height / 2));

            var link = container.append("g")
                .attr("class", "links")
                .selectAll("line")
                .data(links)
                .enter().append("line")
                .attr("stroke-width", d => {
                    if (d.weight) return Math.max(2, d.weight * 5);
                    if (d.all_weights && Object.keys(d.all_weights).length > 0) {
                        var avgWeight = Object.values(d.all_weights).reduce((a, b) => a + b, 0) / Object.values(d.all_weights).length;
                        return Math.max(2, avgWeight * 5);
                    }
                    return 2;
                })
                .attr("class", d => {
                    if (d.all_weights && Object.keys(d.all_weights).length > 1) return "multi-weighted";
                    if (d.weight || (d.all_weights && Object.keys(d.all_weights).length > 0)) return "weighted";
                    return "";
                })
                .on("mouseover", function(d) {
                    // Create tooltip content for edge
                    var content = "<strong>Edge Information</strong><br/>";
                    content += "Relationship: " + d.relation + "<br/>";

                    // Show all weights
                    if (d.all_weights && Object.keys(d.all_weights).length > 0) {
                        content += "<strong>Weights:</strong><br/>";
                        Object.keys(d.all_weights).forEach(function(weightName) {
                            content += "&nbsp;&nbsp;" + weightName + ": " + d.all_weights[weightName] + "<br/>";
                        });
                    } else if (d.weight !== null && d.weight !== undefined) {
                        content += "Weight: " + d.weight + "<br/>";
                    }

                    if (d.relationship_type) {
                        content += "Type: " + d.relationship_type + "<br/>";
                    }
                    // Add other edge properties
                    if (d.edge_info) {
                        Object.keys(d.edge_info).forEach(function(key) {
                            if (key !== 'weight' && key !== 'weights' && key !== 'relationship_type' && 
                                key !== 'source_node_id' && key !== 'target_node_id' && 
                                key !== 'relationship_name' && key !== 'updated_at' && 
                                !key.startsWith('weight_')) {
                                content += key + ": " + d.edge_info[key] + "<br/>";
                            }
                        });
                    }

                    tooltip.html(content)
                        .style("left", (d3.event.pageX + 10) + "px")
                        .style("top", (d3.event.pageY - 10) + "px")
                        .style("opacity", 1);
                })
                .on("mouseout", function(d) {
                    tooltip.style("opacity", 0);
                });

            var edgeLabels = container.append("g")
                .attr("class", "edge-labels")
                .selectAll("text")
                .data(links)
                .enter().append("text")
                .attr("class", "edge-label")
                .text(d => {
                    var label = d.relation;
                    if (d.all_weights && Object.keys(d.all_weights).length > 1) {
                        // Show count of weights for multiple weights
                        label += " (" + Object.keys(d.all_weights).length + " weights)";
                    } else if (d.weight) {
                        label += " (" + d.weight + ")";
                    } else if (d.all_weights && Object.keys(d.all_weights).length === 1) {
                        var singleWeight = Object.values(d.all_weights)[0];
                        label += " (" + singleWeight + ")";
                    }
                    return label;
                });

            var nodeGroup = container.append("g")
                .attr("class", "nodes")
                .selectAll("g")
                .data(nodes)
                .enter().append("g");

            var node = nodeGroup.append("circle")
                .attr("r", 13)
                .attr("fill", d => d.color)
                .call(d3.drag()
                    .on("start", dragstarted)
                    .on("drag", dragged)
                    .on("end", dragended));

            nodeGroup.append("text")
                .attr("class", "node-label")
                .attr("dy", 4)
                .attr("text-anchor", "middle")
                .text(d => d.name);

            nodeGroup.on("mouseover", function(d) {
                // Helper function to create tree-like HTML representation
                function createTreeHTML(obj, indent = 0) {
                    var html = "";
                    var indentStr = "&nbsp;".repeat(indent * 4);
                    
                    for (var key in obj) {
                        // Filter out unwanted properties
                        if (key === 'color' || key === 'index' || key === 'id' || 
                            key === 'x' || key === 'y' || key === 'vx' || key === 'vy' || 
                            key === 'fx' || key === 'fy') {
                            continue;
                        }
                        
                        var value = obj[key];
                        
                        if (value === null || value === undefined) {
                            continue;
                        }
                        
                        if (typeof value === 'object' && !Array.isArray(value)) {
                            // Nested object
                            html += indentStr + "<strong>" + key + ":</strong><br/>";
                            html += createTreeHTML(value, indent + 1);
                        } else if (Array.isArray(value)) {
                            // Array
                            html += indentStr + "<strong>" + key + ":</strong> [" + value.length + " items]<br/>";
                            value.forEach(function(item, idx) {
                                if (typeof item === 'object') {
                                    html += indentStr + "&nbsp;&nbsp;[" + idx + "]:<br/>";
                                    html += createTreeHTML(item, indent + 2);
                                } else {
                                    html += indentStr + "&nbsp;&nbsp;[" + idx + "]: " + item + "<br/>";
                                }
                            });
                        } else {
                            // Simple value
                            var displayValue = String(value);
                            if (displayValue.length > 100) {
                                displayValue = displayValue.substring(0, 100) + "...";
                            }
                            html += indentStr + "<strong>" + key + ":</strong> " + displayValue + "<br/>";
                        }
                    }
                    
                    return html;
                }
                
                var content = "<strong style='font-size: 9px;'>" + d.type + "</strong><br/><br/>";
                content += createTreeHTML(d);
                
                tooltip.html(content)
                    .style("left", (d3.event.pageX + 10) + "px")
                    .style("top", (d3.event.pageY - 10) + "px")
                    .style("opacity", 1);
            })
            .on("mouseout", function(d) {
                tooltip.style("opacity", 0);
            });
            simulation.on("tick", function() {
                link.attr("x1", d => d.source.x)
                    .attr("y1", d => d.source.y)
                    .attr("x2", d => d.target.x)
                    .attr("y2", d => d.target.y);

                edgeLabels
                    .attr("x", d => (d.source.x + d.target.x) / 2)
                    .attr("y", d => (d.source.y + d.target.y) / 2 - 5);

                // FIXED: Use nodeGroup for positioning, not individual circles
                nodeGroup.attr("transform", d => "translate(" + d.x + "," + d.y + ")");
            });

            svg.call(d3.zoom().on("zoom", function() {
                container.attr("transform", d3.event.transform);
            }));

            function dragstarted(d) {
                if (!d3.event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            }

            function dragged(d) {
                d.fx = d3.event.x;
                d.fy = d3.event.y;
            }

            function dragended(d) {
                if (!d3.event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            }

            window.addEventListener("resize", function() {
                width = window.innerWidth;
                height = window.innerHeight;
                svg.attr("width", width).attr("height", height);
                simulation.force("center", d3.forceCenter(width / 2, height / 2));
                simulation.alpha(1).restart();
            });
        </script>
    </body>
    </html>
    """

    html_content = html_template.replace("{nodes}", json.dumps(nodes_list))
    html_content = html_content.replace("{links}", json.dumps(links_list))

    if not destination_file_path:
        home_dir = os.path.expanduser("~")
        destination_file_path = os.path.join(home_dir, "graph_visualization.html")

    os.makedirs(os.path.dirname(destination_file_path) or ".", exist_ok=True)
    with open(destination_file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return html_content


# Alias for backward compatibility
def generate_html_visualization(
    connection: kuzu.Connection,
    destination_file_path: str | None = None,
    title: str = "Knowledge Graph",
    node_configs: list | None = None,
    relation_configs: list | None = None,
    custom_colors: dict[str, str] | None = None,
) -> str:
    """Generate an HTML graph visualization from a Kuzu connection.

    Alias for generate_kuzu_graph_html for backward compatibility.

    Args:
        connection: An active kuzu.Connection
        destination_file_path: Optional path to write the HTML file
        title: Title for the visualization (currently unused)
        node_configs: Optional list of node configurations
        relation_configs: Optional list of relation configurations
        custom_colors: Optional mapping of node types to hex color codes

    Returns:
        The HTML content as a string.
    """
    return generate_kuzu_graph_html(
        connection=connection,
        destination_file_path=destination_file_path,
        node_configs=node_configs,
        relation_configs=relation_configs,
        custom_colors=custom_colors,
    )


class KnowledgeGraphHTMLVisualizer:
    """Class-based wrapper for HTML visualization functionality."""

    def __init__(self, custom_colors: dict[str, str] | None = None):
        """Initialize the visualizer.

        Args:
            custom_colors: Optional custom color mapping for node types
        """
        self.custom_colors = custom_colors or {}

    def generate_html(self, nodes: list[tuple[str, dict]], links: list[tuple[str, str, str, dict]]) -> str:
        """Generate HTML visualization from node and link data.

        Args:
            nodes: List of (node_id, properties_dict) tuples
            links: List of (source_id, target_id, relationship_name, properties_dict) tuples

        Returns:
            HTML content as string
        """
        # Convert to the format expected by the HTML template
        nodes_list = []
        for node_id, node_info in nodes:
            node_info = dict(node_info)  # shallow copy
            node_info["id"] = str(node_id)
            node_type = node_info.get("type", "Unknown")
            node_info["color"] = _get_node_color(node_type, self.custom_colors)
            node_info["name"] = node_info.get("name", str(node_id))
            # Trim noisy timestamp fields if present
            node_info.pop("updated_at", None)
            node_info.pop("created_at", None)
            nodes_list.append(node_info)

        links_list = []
        for source, target, relation, edge_info in links:
            source_s = str(source)
            target_s = str(target)

            # Extract weight variations
            all_weights = {}
            primary_weight = None
            edge_info = edge_info or {}

            if "weight" in edge_info:
                try:
                    primary_weight = float(edge_info["weight"])
                    all_weights["default"] = primary_weight
                except (TypeError, ValueError):
                    pass

            if "weights" in edge_info and isinstance(edge_info["weights"], dict):
                for k, v in edge_info["weights"].items():
                    try:
                        all_weights[str(k)] = float(v)
                    except (TypeError, ValueError):
                        continue
                if primary_weight is None and all_weights:
                    primary_weight = next(iter(all_weights.values()))

            for key, value in edge_info.items():
                if key.startswith("weight_"):
                    try:
                        all_weights[key[7:]] = float(value)
                    except (TypeError, ValueError):
                        continue

            links_list.append(
                {
                    "source": source_s,
                    "target": target_s,
                    "relation": relation,
                    "weight": primary_weight,
                    "all_weights": all_weights,
                    "relationship_type": edge_info.get("relationship_type"),
                    "edge_info": edge_info,
                }
            )

        # Generate the HTML using the existing template
        html_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <script src="https://d3js.org/d3.v5.min.js"></script>
    <style>
        body, html { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: linear-gradient(90deg, #101010, #1a1a2e); color: white; font-family: 'Inter', sans-serif; }

        svg { width: 100vw; height: 100vh; display: block; }
        .links line { stroke: rgba(255, 255, 255, 0.4); stroke-width: 2px; }
        .links line.weighted { stroke: rgba(255, 215, 0, 0.7); }
        .links line.multi-weighted { stroke: rgba(0, 255, 127, 0.8); }
        .nodes circle { stroke: white; stroke-width: 0.5px; filter: drop-shadow(0 0 5px rgba(255,255,255,0.3)); }
        .node-label { font-size: 8px; font-weight: bold; fill: white; text-anchor: middle; dominant-baseline: middle; font-family: 'Inter', sans-serif; pointer-events: none; }
        .edge-label { font-size: 3px; fill: rgba(255, 255, 255, 0.7); text-anchor: middle; dominant-baseline: middle; font-family: 'Inter', sans-serif; pointer-events: none; }
        
        .tooltip {
            position: absolute;
            text-align: left;
            padding: 8px;
            font-size: 8px;
            background: rgba(0, 0, 0, 0.9);
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 4px;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.2s;
            z-index: 1000;
            max-width: 500px;
            word-wrap: break-word;
            max-height: 80vh;
            overflow-y: auto;
        }
    </style>
</head>
<body>
    <svg></svg>
    <div class="tooltip" id="tooltip"></div>
    <script>
        var nodes = {nodes};
        var links = {links};

        var svg = d3.select("svg"),
            width = window.innerWidth,
            height = window.innerHeight;

        var container = svg.append("g");
        var tooltip = d3.select("#tooltip");

        var simulation = d3.forceSimulation(nodes)
            .force("link", d3.forceLink(links).id(d => d.id).strength(0.1))
            .force("charge", d3.forceManyBody().strength(-275))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("x", d3.forceX().strength(0.1).x(width / 2))
            .force("y", d3.forceY().strength(0.1).y(height / 2));

        var link = container.append("g")
            .attr("class", "links")
            .selectAll("line")
            .data(links)
            .enter().append("line")
            .attr("stroke-width", d => {
                if (d.weight) return Math.max(2, d.weight * 5);
                if (d.all_weights && Object.keys(d.all_weights).length > 0) {
                    var avgWeight = Object.values(d.all_weights).reduce((a, b) => a + b, 0) / Object.values(d.all_weights).length;
                    return Math.max(2, avgWeight * 5);
                }
                return 2;
            })
            .attr("class", d => {
                if (d.all_weights && Object.keys(d.all_weights).length > 1) return "multi-weighted";
                if (d.weight || (d.all_weights && Object.keys(d.all_weights).length > 0)) return "weighted";
                return "";
            })
            .on("mouseover", function(d) {
                // Create tooltip content for edge
                var content = "<strong>Edge Information</strong><br/>";
                content += "Relationship: " + d.relation + "<br/>";

                // Show all weights
                if (d.all_weights && Object.keys(d.all_weights).length > 0) {
                    content += "<strong>Weights:</strong><br/>";
                    Object.keys(d.all_weights).forEach(function(weightName) {
                        content += "&nbsp;&nbsp;" + weightName + ": " + d.all_weights[weightName] + "<br/>";
                    });
                } else if (d.weight !== null && d.weight !== undefined) {
                    content += "Weight: " + d.weight + "<br/>";
                }

                if (d.relationship_type) {
                    content += "Type: " + d.relationship_type + "<br/>";
                }
                // Add other edge properties
                if (d.edge_info) {
                    for (let prop in d.edge_info) {
                        if (prop !== 'weight' && prop !== 'weights' && prop !== 'relationship_type') {
                            content += prop + ": " + d.edge_info[prop] + "<br/>";
                        }
                    }
                }

                tooltip.html(content)
                    .style("left", (d3.event.pageX + 10) + "px")
                    .style("top", (d3.event.pageY - 10) + "px")
                    .style("opacity", 1);
            })
            .on("mouseout", function(d) {
                tooltip.style("opacity", 0);
            });

        var node = container.append("g")
            .attr("class", "nodes")
            .selectAll("g")
            .data(nodes)
            .enter().append("g")
            .call(d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended))
            .on("mouseover", function(d) {
                // Helper function to create tree-like HTML representation
                function createTreeHTML(obj, indent = 0) {
                    var html = "";
                    var indentStr = "&nbsp;".repeat(indent * 4);
                    
                    for (var key in obj) {
                        // Filter out unwanted properties
                        if (key === 'color' || key === 'index' || key === 'id' || 
                            key === 'x' || key === 'y' || key === 'vx' || key === 'vy' || 
                            key === 'fx' || key === 'fy') {
                            continue;
                        }
                        
                        var value = obj[key];
                        
                        if (value === null || value === undefined) {
                            continue;
                        }
                        
                        if (typeof value === 'object' && !Array.isArray(value)) {
                            // Nested object
                            html += indentStr + "<strong>" + key + ":</strong><br/>";
                            html += createTreeHTML(value, indent + 1);
                        } else if (Array.isArray(value)) {
                            // Array
                            html += indentStr + "<strong>" + key + ":</strong> [" + value.length + " items]<br/>";
                            value.forEach(function(item, idx) {
                                if (typeof item === 'object') {
                                    html += indentStr + "&nbsp;&nbsp;[" + idx + "]:<br/>";
                                    html += createTreeHTML(item, indent + 2);
                                } else {
                                    html += indentStr + "&nbsp;&nbsp;[" + idx + "]: " + item + "<br/>";
                                }
                            });
                        } else {
                            // Simple value
                            var displayValue = String(value);
                            if (displayValue.length > 100) {
                                displayValue = displayValue.substring(0, 100) + "...";
                            }
                            html += indentStr + "<strong>" + key + ":</strong> " + displayValue + "<br/>";
                        }
                    }
                    
                    return html;
                }
                
                var content = "<strong style='font-size: 10px;'>" + d.type + "</strong><br/><br/>";
                content += createTreeHTML(d);
                
                tooltip.html(content)
                    .style("left", (d3.event.pageX + 10) + "px")
                    .style("top", (d3.event.pageY - 10) + "px")
                    .style("opacity", 1);
            })
            .on("mouseout", function(d) {
                tooltip.style("opacity", 0);
            });

        node.append("circle")
            .attr("r", 10)
            .attr("fill", d => d.color);

        node.append("text")
            .attr("class", "node-label")
            .attr("dy", "0.35em")
            .text(d => d.name);

        // Add zoom behavior
        var zoom = d3.zoom()
            .scaleExtent([0.1, 10])
            .on("zoom", function() {
                container.attr("transform", d3.event.transform);
            });

        svg.call(zoom);

        simulation.on("tick", function() {
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            node.attr("transform", d => "translate(" + d.x + "," + d.y + ")");
        });

        function dragstarted(d) {
            if (!d3.event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }

        function dragged(d) {
            d.fx = d3.event.x;
            d.fy = d3.event.y;
        }

        function dragended(d) {
            if (!d3.event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }

        // Handle window resize
        window.addEventListener('resize', function() {
            width = window.innerWidth;
            height = window.innerHeight;
            svg.attr("width", width).attr("height", height);
            simulation.force("center", d3.forceCenter(width / 2, height / 2));
            simulation.alpha(1).restart();
        });
    </script>
</body>
</html>
        """

        html_content = html_template.replace("{nodes}", json.dumps(nodes_list))
        html_content = html_content.replace("{links}", json.dumps(links_list))

        return html_content
