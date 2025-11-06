# Ideas around evolution of the Tk and Bleuprint

## Hybrid search extension to genai_tk/core/embeddings_store.py
- use BM25S + Spacy (but configurable)
- call it RAG store ? 

## Optimize Markdown chunking
- use https://docs.chonkie.ai/oss/chefs/markdownchef ,  https://pypi.org/project/chonkie/
- custom Loader ? 
- "write a Markdown file chunker, inheriting LangChain Loader.  It takes a list of Markdown file as input, and chunk them using the Chonkie package https://docs.chonkie.ai/oss/chefs/markdownchef ,  https://pypi.org/project/chonkie/, https://docs.chonkie.ai/oss/chunkers/table-chunker, ... . Set filename in metadata.  Use Context7 to get Chonkie usage. Makes parameters such as cheun siez configurable, but provide common default values for that kind of file" 




# Text2Cypher

- warp: Create a function that returns a Markdown string with information of nodes (including node type, fields name and their type, embedded fields,  .. ) and edges (name, spurce/destibation, properties), and a CLI command name 'schema' that call it and print the string. The purpose is to provide context information to an LLM so it can genere correct Cypher code.

The content should include information gathered from the graph database  (you can use content from CLI command 'show_info' in genai_tk/extra/structured/commands_baml.py ), and/or from the parameters passed to create_simplified_schema and/or , and, for missing descriptions, from class / fields description  extracted from the BAML file (to do so, import dynamically the BAML generated file ekg/baml_client/inlinedbaml.py and search using regexp in all keys of _file_map (except clients.baml and generators.baml)).  
Avoid code duplication. 
Return also, in another section, the list of fields that are indexed.
Test with command 'uv run cli kg schema'

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
- ```uv run cli kg delete -f ; uv run cli kg add --key cnes-venus-tma ; uv run cli kg export-html```

- ```uv run cli baml extract $ONEDRIVE/prj/atos-kg/rainbow-md/cnes-venus-tma.md --function ExtractRainbow --force```