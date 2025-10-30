# Ideas around evolition of the Tk and Bleuprint

## Hybrid search extension to genai_tk/core/embeddings_store.py
- use BM25S + Spacy (but configurable)
- call it RAG store ? 

## Optimize Markdown chunking
- use https://docs.chonkie.ai/oss/chefs/markdownchef ,  https://pypi.org/project/chonkie/
- custom Loader ? 
- "write a Markdown file chunker, inheriting LangChain Loader.  It takes a list of Markdown file as input, and chunk them using the Chonkie package https://docs.chonkie.ai/oss/chefs/markdownchef ,  https://pypi.org/project/chonkie/, https://docs.chonkie.ai/oss/chunkers/table-chunker, ... . Set filename in metadata.  Use Context7 to get Chonkie usage. Makes parameters such as cheun siez configurable, but provide common default values for that kind of file" 

## Connect BAML 'dynamic LLM selection'  to LLM Factory
- see https://docs.boundaryml.com/guide/baml-advanced/llm-client-registry 

- "Write a utility in 'genai_tk/extra' to create a BAML ClientRegistry from the LLM Factory. Try to do the best to get provider, model, api key (when not default), end points (when non default), ... Input can be an LLM if or an LLM tag.  call cr.set_primary.
ex usage : get_client_registry( llm = "coder" ) or get_client_registry( llm ="gpt_4o_openai" )




## Better 'rag' commands
- pass a configurable chunker
https://docs.chonkie.ai/oss/pipelines 

##  Better KG
- in genai_blueprint/demos/ekg/rainbow_subgraph.py (and genai_blueprint/demos/ekg/graph_schema.py ): 
1/  "Modify GraphNodeConfig  so there's a field "embedd" which allows to incorporate other BAML class within the node definition.  It replace the nodes with fields "  embed_in_parent and embed_prefix.  Ex: GraphNodeConfig (baml_class="ReviewedOpportunity", embedded =[("financial", "FinacialMetrics)], ... )  . Change graph nodes accordingly.  
2/ Create edges "IS_A" between the nodes and new nodes (that you need to create) corresponding to their class.  For example, "CNES" - ["IS_A"] - "CUSTOMER".
3/ In GraphNodeConfig, add a property "index_fields", with a list of the BAML generated pydatic object fieds to index with a vector store.  Add a method in GraphSchema that gather these fields and insert them a vector store (use an EmbeddingsStore whose config nale is given ).  Ex: GraphNodeConfig(baml_class="TechnicalApproach", indindex_fields=["architecture", "technical stack"], ..)
4/ Last but nor leaset, intoduce an abstraction to support several graph database as backends. Today we use Kuzu, but we also need to support Neo4j, and possibly other backends.  No neo4j is present yet, so postpone the tests.
5/ update  'uv cli kg info'  sub command .


Improve graph node identification and naming.  Add in the node a unique ID ("_id"), a "node_name" ( to avoid confusion with possible field called 'name' in the BAML object) whose value is given by 'name_from',  and a creation / modification date (_created_at, _updated_at). Remove _generated_key and related stuff.  Display 'node_name' in the HTML graph. update  'uv cli kg info'  sub command  . 



 Implement yet another generalisation : remove hard dependencies to the BAML generated package (here 'genai_blueprint.demos.ekg.baml_client'): 
 -  Get generated BAML path from  the YAML config file (here in: override.yaml, key 'structured') using something like global_config().get_dict("structured.{name of the config}.baml_client"   ) " (use "default" by default)
 -  remove hard coded imports (here 'import genai_blueprint.demos.ekg.baml_client.types as baml_types, from genai_blueprint.demos.ekg.baml_client.async_client import b as baml_async_client' ) and replace by dynamic loading




# To Test :
- ```cli kg delete -f ; cli kg add --key cnes-venus-tma ; cli kg export-html```

- ```uv run cli baml extract $ONEDRIVE/prj/atos-kg/rainbow-md/cnes-venus-SHORT.md --baml ReviewedOpportunity:ExtractRainbow --force```