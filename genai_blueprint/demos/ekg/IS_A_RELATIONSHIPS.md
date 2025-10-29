# IS_A Relationships Implementation Guide

## Overview
IS_A relationships create a taxonomy by connecting instance nodes to their entity type nodes.
For example: `CNES` (instance) -[:IS_A]-> `CUSTOMER` (entity type)

## Implementation Approach

### 1. Entity Type Nodes
Entity type nodes represent the classes/types of entities in the graph. They should be:
- Created once per entity type (not per instance)
- Have a simple schema (e.g., `type_name` as primary key)
- Serve as taxonomy anchors

### 2. Schema Extension
To implement IS_A relationships, extend `GraphSchema` with:

```python
def create_entity_type_nodes(self) -> List[GraphNodeConfig]:
    """Create entity type nodes for each configured node type.
    
    Returns:
        List of EntityType node configurations
    """
    from pydantic import BaseModel, Field
    
    class EntityType(BaseModel):
        type_name: str = Field(description="Name of the entity type")
    
    entity_types = []
    for node_config in self.nodes:
        # Skip root and embedded nodes
        if node_config.baml_class == self.root_model_class:
            continue
        if node_config.embed_in_parent:
            continue
            
        # Create entity type node
        entity_type_node = GraphNodeConfig(
            baml_class=EntityType,
            key="type_name",
            description=f"Entity type for {node_config.baml_class.__name__}",
        )
        entity_types.append(entity_type_node)
    
    return entity_types

def create_is_a_relationships(self) -> List[GraphRelationConfig]:
    """Create IS_A relationships from instances to entity types.
    
    Returns:
        List of IS_A relationship configurations
    """
    relationships = []
    for node_config in self.nodes:
        # Skip root and embedded nodes
        if node_config.baml_class == self.root_model_class:
            continue
        if node_config.embed_in_parent:
            continue
            
        # Create IS_A relationship
        rel = GraphRelationConfig(
            from_node=node_config.baml_class,
            to_node=EntityType,
            name="IS_A",
            description=f"{node_config.baml_class.__name__} instances are of this type",
        )
        relationships.append(rel)
    
    return relationships
```

### 3. Graph Creation
When creating the graph, the process should:

1. Create entity type nodes first
2. Insert one EntityType node per distinct entity class
3. Create instance nodes as usual
4. Create IS_A relationships linking instances to their types

### 4. Usage in graph_core.py

```python
def create_graph_with_taxonomy(
    conn: kuzu.Connection,
    model: BaseModel,
    schema: GraphSchema,
) -> tuple[Dict[str, List[Dict]], List[Tuple]]:
    """Create graph with entity type taxonomy."""
    
    # Get entity type nodes and IS_A relationships
    entity_type_nodes = schema.create_entity_type_nodes()
    is_a_relations = schema.create_is_a_relationships()
    
    # Extend schema with taxonomy
    extended_nodes = schema.nodes + entity_type_nodes
    extended_relations = schema.relations + is_a_relations
    
    # Create schema and load data as usual
    # ... rest of graph creation logic
    
    # After loading instance nodes, create EntityType nodes
    entity_types_data = {}
    for node_config in schema.nodes:
        if node_config.baml_class != schema.root_model_class:
            type_name = node_config.baml_class.__name__
            entity_types_data[type_name] = {"type_name": type_name}
    
    # Insert EntityType nodes
    for type_name, data in entity_types_data.items():
        # INSERT EntityType node
        ...
    
    # Create IS_A relationships
    # For each instance node, create relationship to its type
    for instance_type, instances in nodes_dict.items():
        for instance in instances:
            # CREATE (instance)-[:IS_A]->(type)
            ...
```

### 5. Querying with IS_A

Once implemented, you can query the taxonomy:

```cypher
# Find all entity types
MATCH (e:EntityType) RETURN e.type_name

# Find all instances of a specific type
MATCH (n)-[:IS_A]->(t:EntityType {type_name: 'Customer'})
RETURN n

# Count instances by type
MATCH (n)-[:IS_A]->(t:EntityType)
RETURN t.type_name, count(n) as instance_count

# Find types related through instances
MATCH (n1)-[:IS_A]->(t1:EntityType),
      (n1)-[r]->(n2),
      (n2)-[:IS_A]->(t2:EntityType)
RETURN DISTINCT t1.type_name, type(r), t2.type_name
```

## Benefits
- **Taxonomy navigation**: Easy to find all instances of a type
- **Type-level queries**: Aggregate and analyze at the type level
- **Schema introspection**: Query the graph schema through the graph itself
- **Semantic clarity**: Makes the graph self-documenting

## Implementation Status
- [ ] Create EntityType node class
- [ ] Add create_entity_type_nodes() to GraphSchema
- [ ] Add create_is_a_relationships() to GraphSchema
- [ ] Update graph_core.py to create EntityType nodes
- [ ] Update graph_core.py to create IS_A relationships
- [ ] Add tests for IS_A relationship creation
- [ ] Update CLI to show taxonomy information
- [ ] Add sample queries using IS_A relationships
