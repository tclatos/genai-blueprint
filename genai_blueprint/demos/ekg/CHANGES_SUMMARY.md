# EKG Schema Enhancements - Summary

## Overview
This document summarizes the changes made to the EKG (Enhanced Knowledge Graph) system to support:
1. New embedded field structure
2. Vector store indexing
3. Graph backend abstraction
4. IS_A relationships (design documented)

## 1. Modified GraphNodeConfig - Embedded Fields

### Changes in `graph_schema.py`

**Before:**
```python
class GraphNodeConfig(BaseModel):
    baml_class: Type[BaseModel]
    key: str
    embed_in_parent: bool = False
    embed_prefix: str = ""
```

**After:**
```python
class GraphNodeConfig(BaseModel):
    baml_class: Type[BaseModel]
    key: str
    embedded: List[Tuple[str, Type[BaseModel]]] = []  # NEW
    index_fields: List[str] = []  # NEW
    
    # Legacy fields (deprecated but maintained for backward compatibility)
    embed_in_parent: bool = False
    embed_prefix: str = ""
```

### Usage Example

**Old approach:**
```python
GraphNodeConfig(
    baml_class=FinancialMetrics,
    key="tcv",
    embed_in_parent=True,
    embed_prefix="financial_",
)
```

**New approach:**
```python
GraphNodeConfig(
    baml_class=Opportunity,
    key="name",
    embedded=[("financial", FinancialMetrics)],  # Embed FinancialMetrics as "financial"
    index_fields=["name", "status"],  # Index these fields in vector store
)
```

### Benefits
- **Clearer semantics**: The parent explicitly lists its embedded children
- **Multiple embeddings**: Can embed multiple classes in one parent
- **Field naming control**: Explicit field name in the embedded tuple
- **Backward compatible**: Old `embed_in_parent` still works

## 2. Vector Store Indexing

### New Features

Added `index_fields` property to `GraphNodeConfig`:
```python
GraphNodeConfig(
    baml_class=TechnicalApproach,
    key="technical_stack",
    index_fields=["architecture", "technical_stack"],  # These fields will be indexed
)
```

### Vector Store Integration

New method in `GraphSchema`:
```python
def index_fields_in_vector_store(
    self, 
    model_instance: BaseModel, 
    embeddings_store_config: str
) -> None:
    """Index specified fields from model instance in a vector store."""
```

### Usage
```python
schema = build_schema()
schema.index_fields_in_vector_store(
    model_instance=reviewed_opportunity,
    embeddings_store_config="postgres"  # Config name from baseline.yaml
)
```

This will:
1. Extract all fields marked with `index_fields`
2. Convert them to LangChain Documents
3. Store them in the specified vector store with metadata

### Metadata Structure
Each indexed field creates a document with:
```python
{
    "page_content": str(field_value),
    "metadata": {
        "node_type": "TechnicalApproach",
        "field_name": "architecture",
        "primary_key": "microservices_stack",
        "field_path": "technical_approach"
    }
}
```

## 3. Graph Backend Abstraction

### New File: `graph_backend.py`

Created an abstract interface for graph databases:

```python
class GraphBackend(ABC):
    """Abstract base class for graph database backends."""
    
    @abstractmethod
    def connect(self, connection_string: str) -> None: ...
    
    @abstractmethod
    def execute(self, query: str, parameters: dict | None = None) -> Any: ...
    
    @abstractmethod
    def create_node_table(self, table_name: str, fields: dict, primary_key: str) -> None: ...
    
    @abstractmethod
    def create_relationship_table(self, rel_name: str, from_table: str, to_table: str) -> None: ...
```

### Implementations

**KuzuBackend** - Fully implemented
```python
backend = create_backend("kuzu")
backend.connect("/path/to/db")
backend.execute("MATCH (n) RETURN n LIMIT 10")
```

**Neo4jBackend** - Placeholder for future implementation
```python
backend = create_backend("neo4j")  # Raises NotImplementedError
```

### Usage
```python
from genai_blueprint.demos.ekg.graph_backend import create_backend

# Create backend
backend = create_backend("kuzu")
backend.connect("~/kuzu/ekg_database.db")

# Execute queries
result = backend.execute("MATCH (n:Customer) RETURN count(n)")

# Get query language
lang = backend.get_query_language()  # "Cypher"
```

### Benefits
- **Pluggable backends**: Easy to switch between Kuzu, Neo4j, etc.
- **Consistent interface**: Same API regardless of backend
- **Future-proof**: Adding new backends doesn't require changing core logic

## 4. IS_A Relationships

### Design

IS_A relationships create a taxonomy connecting instances to entity types:
```
(CNES:Customer) -[:IS_A]-> (CUSTOMER:EntityType)
(Venus:Opportunity) -[:IS_A]-> (OPPORTUNITY:EntityType)
```

### Implementation Guide

See `IS_A_RELATIONSHIPS.md` for detailed implementation instructions.

**Key components:**
1. EntityType node class
2. Methods to generate entity type nodes
3. Methods to create IS_A relationships
4. Integration with graph_core.py

**Status:** Design documented, implementation postponed

## 5. Updated CLI Command

### `uv cli kg info` Enhancements

The info command now shows:

1. **Backend Information**
   ```
   Database Type: Kuzu Graph Database
   Backend: Kuzu (via GraphBackend abstraction)
   ```

2. **Indexed Fields**
   ```
   Vector Store Indexed Fields
   ┌──────────────────┬──────────────────────────┐
   │ Node Type        │ Indexed Fields           │
   ├──────────────────┼──────────────────────────┤
   │ Opportunity      │ name, status             │
   │ TechnicalApproach│ architecture, tech_stack │
   └──────────────────┴──────────────────────────┘
   ```

3. **Embedded Fields**
   ```
   Fields Embedded in Parent Nodes
   ┌──────────────┬────────────────┬─────────────────┐
   │ Parent Node  │ Embedded Field │ Embedded Class  │
   ├──────────────┼────────────────┼─────────────────┤
   │ Opportunity  │ financial      │ FinancialMetrics│
   └──────────────┴────────────────┴─────────────────┘
   ```

## 6. Updated Files

### Modified Files
1. **graph_schema.py**
   - Added `embedded` field to GraphNodeConfig
   - Added `index_fields` field to GraphNodeConfig
   - Added `index_fields_in_vector_store()` method to GraphSchema
   - Updated `_compute_excluded_fields()` to handle new structure
   - Added deprecation warning for `embed_in_parent`

2. **rainbow_subgraph.py**
   - Updated node definitions to use new `embedded` structure
   - Added `index_fields` to relevant nodes
   - Removed legacy FinancialMetrics node with `embed_in_parent`

3. **graph_core.py**
   - Updated NodeInfo class to include `embedded` field
   - Updated `create_schema()` to handle new embedded structure
   - Updated `_add_embedded_fields()` to process both old and new formats
   - Maintained backward compatibility with legacy approach

4. **commands_ekg.py**
   - Enhanced `kg info` command to show backend type
   - Added indexed fields display
   - Added embedded fields display

### New Files
1. **graph_backend.py** - Graph backend abstraction layer
2. **IS_A_RELATIONSHIPS.md** - IS_A implementation guide
3. **CHANGES_SUMMARY.md** - This file

## 7. Backward Compatibility

All changes maintain backward compatibility:

- Old `embed_in_parent` nodes still work (with deprecation warning)
- Existing schemas continue to function without modification
- New features are additive, not breaking

## 8. Migration Guide

### For Embedded Fields

**Step 1:** Update parent node to use `embedded`
```python
# From:
GraphNodeConfig(baml_class=Opportunity, key="name")

# To:
GraphNodeConfig(
    baml_class=Opportunity, 
    key="name",
    embedded=[("financial", FinancialMetrics)]
)
```

**Step 2:** Remove child node with `embed_in_parent`
```python
# Remove this:
GraphNodeConfig(
    baml_class=FinancialMetrics,
    key="tcv",
    embed_in_parent=True,
    embed_prefix="financial_",
)
```

### For Vector Indexing

Add `index_fields` to nodes you want to search:
```python
GraphNodeConfig(
    baml_class=TechnicalApproach,
    key="technical_stack",
    index_fields=["architecture", "technical_stack"],
)
```

Then index after graph creation:
```python
schema.index_fields_in_vector_store(data, "postgres")
```

## 9. Testing

To test the changes:

```bash
# 1. Test graph creation with new schema
uv run cli kg delete  # Clear existing data
uv run cli kg add --key cnes-venus-tma

# 2. Check schema info
uv run cli kg info

# 3. Query the graph
uv run cli kg query

# 4. Test vector indexing (in your code)
schema = subgraph.build_schema()
schema.index_fields_in_vector_store(data, "postgres")
```

## 10. Next Steps

1. **Implement IS_A relationships** (see IS_A_RELATIONSHIPS.md)
2. **Add Neo4j backend** implementation
3. **Create vector search tools** that use indexed fields
4. **Add configuration** for enabling/disabling features
5. **Performance testing** with large graphs
6. **Documentation** updates in main README

## Questions?

For questions about these changes, refer to:
- `graph_schema.py` - Schema definitions
- `graph_backend.py` - Backend abstraction
- `IS_A_RELATIONSHIPS.md` - IS_A implementation guide
- `rainbow_subgraph.py` - Example usage
