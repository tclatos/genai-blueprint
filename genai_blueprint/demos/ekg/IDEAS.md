# Ideas around evolution of the Tk and Bleuprint

## Hybrid search extension to genai_tk/core/embeddings_store.py
- use BM25S + Spacy (but configurable)
- call it RAG store ? 

## Optimize Markdown chunking
- use https://docs.chonkie.ai/oss/chefs/markdownchef ,  https://pypi.org/project/chonkie/
- custom Loader ? 
- "write a Markdown file chunker, inheriting LangChain Loader.  It takes a list of Markdown file as input, and chunk them using the Chonkie package https://docs.chonkie.ai/oss/chefs/markdownchef ,  https://pypi.org/project/chonkie/, https://docs.chonkie.ai/oss/chunkers/table-chunker, ... . Set filename in metadata.  Use Context7 to get Chonkie usage. Makes parameters such as cheun siez configurable, but provide common default values for that kind of file" 



# Merging
We want to add several documents in the Knowledge Graph, with merging of duplicated nodes. So the goal 
is to improve the 'add' CLI command in /home/tcl/prj/genai-blueprint/genai_blueprint/demos/ekg/cli_commands/commands_ekg.py.  For now, we focus on adding document in the same sub-graph (ie same schemas).
You'll notably need to refactor genai_blueprint/demos/ekg/graph_backend.py so it allows incremental addition of nodes and edges (replace CREATE NODE TABLE by CREATE NODE TABLE IF NOT EXISTS, use MERGE  instead or CREATE NODE, etc).
Use the 'name' property to check that 2 nodes of same type can be merged.
Do not use APOC ! (so you need to call pure Cy^her code to move relationships and delete duplicated).
For test, use : .... 









1/  first,  refactor to get usage close than other commands : replace 'subgraph' parameter by the name of the top level BAML class. Refactor ReviewedOpportunitySubgraph accordingly, simplify ()

# Text2Cypher


- Create a full KG schema  with BAML from 
    - the Kuzu schema
- generate text2qsl wit 
- possibly Prune the schema with https://kuzudb.github.io/blog/post/improving-text2cypher-for-graphrag-via-schema-pruning/#pruned-graph-schema-results



## Better 'rag' commands
- pass a configurable chunker
https://docs.chonkie.ai/oss/pipelines 

##  Better KG



# To Test :
- ```uv run cli kg delete -f ; uv run cli kg add --key cnes-venus-tma ; uv run cli kg export-html```

- ```uv run cli baml extract $ONEDRIVE/prj/atos-kg/rainbow-md/cnes-venus-tma.md --function ExtractRainbow --force```

- ```cli kg schema```


# Misc

Use https://github.com/GrahamDumpleton/wrapt for @once
