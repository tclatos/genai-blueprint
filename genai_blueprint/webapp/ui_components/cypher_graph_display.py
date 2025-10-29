"""Cypher graph visualization utilities.

This module provides functions to convert graph data from a Cypher grap database to
a JSON format usable by Cytoscape-js, a graph visualisation library.

It's been tested with Kuzu, but should work with limited change with other Cyper graph databases.

"""

from langchain_community.graphs.graph_store import GraphStore

# should work with langchain_community.graphs.graph_store.GraphStore


def get_cytoscape_json(graph: GraphStore) -> dict:
    """Convert GraphStore data to Cytoscape JSON format.

    Args:
        graph: The GraphStore containing nodes and relationships

    Returns:
        dict: Cytoscape-compatible JSON with nodes and edges, excluding text_chunk nodes
    """
    cyto_data = {"nodes": [], "edges": []}

    # Query all nodes
    nodes_query = "MATCH (n) RETURN n"
    nodes_result = graph.query(nodes_query)

    # Add nodes to Cytoscape data, excluding text_chunk nodes
    for node in nodes_result:
        if node["n"]["type"] != "text_chunk":
            cyto_data["nodes"].append(
                {"data": {"id": node["n"]["id"], "label": node["n"]["_label"], "type": node["n"]["type"]}}
            )

    # Query all relationships
    rels_query = "MATCH (a)-[r]->(b) RETURN a, r, b"
    rels_result = graph.query(rels_query)

    # Add relationships to Cytoscape data, excluding those involving text_chunk nodes
    for rel in rels_result:
        if rel["a"]["type"] != "text_chunk" and rel["b"]["type"] != "text_chunk":
            cyto_data["edges"].append(
                {
                    "data": {
                        "id": f"{rel['a']['id']}-{rel['r']['_label']}-{rel['b']['id']}",
                        "source": rel["a"]["id"],
                        "target": rel["b"]["id"],
                        "label": rel["r"]["_label"],
                    }
                }
            )
    return cyto_data


def get_cytoscape_style() -> list[dict]:
    """Get default styling for Cytoscape graph visualization.

    Returns:
        list[dict]: List of style definitions for nodes and edges
    """
    style = [
        {
            "selector": "node",
            "css": {
                "content": "data(id)",
                "text-valign": "center",
                "text-halign": "center",
                "color": "white",
                "background-color": "#002733",
                "width": "label",
                "height": "label",
                "padding": "10px",
                "shape": "ellipse",
                "font-size": "10px",
                "border-width": 2,
                "border-color": "#444",
            },
        },
        {
            "selector": "edge",
            "css": {
                "content": "data(label)",
                "curve-style": "bezier",
                "target-arrow-shape": "triangle",
                "line-color": "#999",
                "target-arrow-color": "#999",
                "font-size": "6px",
                "text-margin-y": "-10px",
                "text-rotation": "autorotate",
                "width": 2,
                "arrow-scale": 1,
            },
        },
    ]
    return style
