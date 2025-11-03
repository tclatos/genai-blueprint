# Ideas around evolution of the Tk and Bleuprint

## Hybrid search extension to genai_tk/core/embeddings_store.py
- use BM25S + Spacy (but configurable)
- call it RAG store ? 

## Optimize Markdown chunking
- use https://docs.chonkie.ai/oss/chefs/markdownchef ,  https://pypi.org/project/chonkie/
- custom Loader ? 
- "write a Markdown file chunker, inheriting LangChain Loader.  It takes a list of Markdown file as input, and chunk them using the Chonkie package https://docs.chonkie.ai/oss/chefs/markdownchef ,  https://pypi.org/project/chonkie/, https://docs.chonkie.ai/oss/chunkers/table-chunker, ... . Set filename in metadata.  Use Context7 to get Chonkie usage. Makes parameters such as cheun siez configurable, but provide common default values for that kind of file" 


# Add properties to edges
We want to move some properties from nodes to edges.  For example, the property 'comment' of the BAML object 'Competitor' should not be in the 'Competitor' node, but as property of the edge between 'ReviewedOpportunity' and 'Competitor'.
We we could implement someting like :
    GraphRelationConfig(
        from_node=ReviewedOpportunity,
        to_node=Competitor,
        name="HAS_COMPETITOR",
        description="Known competitors",
        dest_properties = ["comment"]
    )
dest_properties are fields of the destination (here Competitor) that should be removed from it, and set in the relationship.

Same for property  'role' in relationship HAS_TEAM_MEMBER between ReviewedOpportunity and Person


# Text2Cypher
- Create a full KG schema  with BAML from 
    - The BAML file (taken from /baml_client/inlinedbaml.py)
    - The Pydantic model OR (better ?)  the Kuzu schema
- generate text2qsl wit 
- possibly Prune the schema with https://kuzudb.github.io/blog/post/improving-text2cypher-for-graphrag-via-schema-pruning/#pruned-graph-schema-results



## Better 'rag' commands
- pass a configurable chunker
https://docs.chonkie.ai/oss/pipelines 

##  Better KG



# To Test :
- ```cli kg delete -f ; cli kg add --key cnes-venus-tma ; cli kg export-html```

- ```uv run cli baml extract $ONEDRIVE/prj/atos-kg/rainbow-md/cnes-venus-SHORT.md --baml ReviewedOpportunity:ExtractRainbow --force```