# Ideas around evolution of the Tk and Bleuprint

## Better HTML visualisation
- User can 
  - select the types of nodes and relationsips

- Use G.V()

## Hybrid search extension to genai_tk/core/embeddings_store.py
- use BM25S + Spacy (but configurable)
- call it RAG store ? 

## Optimize Markdown chunking
- use https://docs.chonkie.ai/oss/chefs/markdownchef ,  https://pypi.org/project/chonkie/
- custom Loader ? 
- "write a Markdown file chunker, inheriting LangChain Loader.  It takes a list of Markdown file as input, and chunk them using the Chonkie package https://docs.chonkie.ai/oss/chefs/markdownchef ,  https://pypi.org/project/chonkie/, https://docs.chonkie.ai/oss/chunkers/table-chunker, ... . Set filename in metadata.  Use Context7 to get Chonkie usage. Makes parameters such as cheun siez configurable, but provide common default values for that kind of file" 


## Graph Database Factory
dans conf:
graph_db:
    default:
      type: 



# Import tables
- rename cli kg add  -> kg add-doc
- new command add-table
   - 
- new command relink


# Text2Cypher

Complete method

generate_schema_markdown


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

- ```uv run cli baml run FakeRainbow -i "Project for CNES; Marc Ferrer as sales lead in Atos team" --kvstore-key fake_cnes_1 --force```

- ```cli kg schema```


# Misc

Use https://github.com/GrahamDumpleton/wrapt for @once
