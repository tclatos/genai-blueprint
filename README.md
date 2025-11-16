# GenAI Framework

A framework for building and deploying Generative AI/ Agentic AI applications with the following features:

- **Core Components**: Factories for LLMs, Embeddings, Vector Stores and Runnables
- **Modular Architecture**: Plug-and-play components for AI workflows
- **Agent Systems**:
  - ReAct and Plan-and-Execute agents
  - Multi-tool calling agents
  - Hybrid search (semantic + keyword)
  - Research and data analysis agents
  - Multi-agent coordination (CrewAI, MCP, AutoGen)

- Built on LangChain with extensions for enterprise use cases.
- Extensive use of 'factory' and 'inversion of control' patterns to improve extendibility

## Core Stack

**Foundation**:
- `LangChain` - AI orchestration
- `LangGraph` - Agent workflows  
- `Pydantic` - Data modelisation & validation
- `FastAPI` - REST endpoints
- `Streamlit` - Web interfaces
- `Typer` - CLI framework
- `OmegaConf` - Configuration management


**Key Integrations**:
- `Tavily` - Web search
- `GPT Researcher` - Autonomous research
- `MCP` - Model Context Protocol
- `AutoGen` - Multi-agent systems
- `pgvector` - Vector database

## Documentation

For an overview of the code structure and patterns:
[Tutorial: https://deepwiki.com/tclatos/genai-blueprint/1-overview) 

Note: The tutorial was automatically generated and may be slightly outdated - refer to the code for current implementations.

## Getting Started

**Prerequisites**:
- Python 3.12 (installed automatically via `uv`). The code should however work with Python 3.11 or 3.13.
- `uv` for dependency management
- `make` for build commands

It has been tested on Linux, WSL/Ubuntu and MacOS.

**Installation**:
```bash
make install
```

**Configuration**:

**🚀 Enhanced Configuration System**
The configuration system now supports **flexible project directory discovery**:
- Works from **any subdirectory** (notebooks/, demos/, etc.) - automatically finds config files
- **Parent directory search** - searches up the directory tree for configuration files
- **Hierarchical overrides** - environment-specific configurations
- **Dynamic path resolution** - paths automatically adjust based on project location

**Main Configuration Files**:
- `config/app_conf.yaml`: Main application settings and paths
- `config/baseline.yaml`: Core LLM, embeddings, and vector store configurations
- `config/overrides.yaml`: Environment-specific overrides (selected via `BLUEPRINT_CONFIG`)
- `config/mcp_servers.yaml`: MCP server configurations
- `config/basic_auth.yaml`: Basic authentication settings
- `.env`: API keys and environment variables (can be in project root or parent directories)

**Development Configuration**:
- `config/.vscode/`: VSCode development settings
  - `settings.json`: Editor configuration for the project

**Agent Configurations**:
- `config/agents/`: Agent-specific configurations
  - `deepagents.yaml`: Deep agent configurations
  - `langchain.yaml`: LangChain agent settings
  - `smolagents.yaml`: SmolAgents configurations

**Provider Configurations**:
- `config/providers/llm.yaml`: LLM model definitions and provider configurations
- `config/providers/embeddings.yaml`: Embedding model configurations

**Demo and Component Configurations**:
- `config/demos/`: Demo-specific configurations
  - `cli_examples.yaml`: CLI demo configurations
  - `cognee_kg.yaml`: Cognee knowledge graph settings
  - `graph_rag.yaml`: Graph RAG configurations
  - `mergekit.yaml`: MergeKit demo settings
  - `presidio_anonymization.yaml`: Presidio anonymization demo
  - `README.md`: Demo documentation
- `config/components/`: Component-specific configurations
  - `gpt_researcher.yaml`: GPT Researcher component settings
- `config/schemas/`: Schema definitions for structured data
  - `document_extractor.yaml`: Document extraction schema

**Development Configuration**:
- `pyproject.toml`: Project dependencies and build configuration
- Uses modern Python packaging with `uv` for fast dependency management


**Quick Test**:
```bash
make test_install  # Verifies basic functionality
make test         # Runs test suite (some parallel tests may need adjustment)
make webapp       # launch the Streamlit app
```

**Alternative Quick Test**:
```bash
python quick_test.py  # Quick functionality verification script
```
Configure LLMs via `/config/providers/llm.yaml` after setting up API keys.



### Key Files and Directories

#### Core AI Components
- `genai_blueprint/ai_chains/`: AI chain implementations and examples
  - `A_1_joke.py`: Simple joke generation chain example
  - `B_1_naive_rag_example.py`: Basic RAG implementation
  - `B_2_self_query.py`: Self-querying retrieval demo
  - `C_1_tools_example.py`: Tool usage examples
  - `C_2_advanced_rag_langgraph.py`: Advanced RAG with LangGraph
  - `C_2_advanced_rag_langgraph_functional.py`: Functional approach to advanced RAG
  - `C_2_Agentic_Rag_Functional.py`: Agentic RAG functional approach
  - `C_3_essay_writer_agent.py`: Essay writing agent
  - `C_4_agent_structured_output.py`: Structured output agents
  - `fabric_chain.py`: Fabric pattern chain implementation

#### Main Application Components
- `genai_blueprint/main/`: Main application entry points
  - `cli.py`: Command-line interface implementation
  - `fastapi_app.py`: FastAPI web application
  - `langserve_app.py`: LangServe integration
  - `modal_app.py`: Modal deployment setup
  - `streamlit.py`: Streamlit web application

#### Demos and Examples
- `genai_blueprint/demos/`: Various demonstration implementations
  - `deep_agents/`: Deep learning agent demonstrations
    - `coding_agent_example.py`: Coding agent implementation
    - `research_agent_example.py`: Research agent demonstration
  - `ekg/`: Enterprise Knowledge Graph demos
    - `baml_src/`: BAML schema definitions
      - `clients.baml`: Client data schemas
      - `generators.baml`: Data generation schemas
      - `rainbow_project_kg.baml`: Knowledge graph schemas
    - `cli_commands/`: EKG CLI command implementations
      - `commands.py`: Main CLI commands
      - `commands_baml.py`: BAML-specific CLI commands
      - `commands_ekg.py`: EKG-specific commands
    - `notebooks/`: Jupyter notebooks for EKG development
      - `0_scratchpad_ekg2.ipynb`: EKG development scratchpad
      - `0_struct_rag.ipynb`: Structured RAG notebook
      - `scratchpad.ipynb`: General development scratchpad
    - `struct_rag/`: Structured RAG implementations
      - `struct_rag_doc_processing.py`: Document processing
      - `struct_rag_tool_factory.py`: RAG tool factory
    - `example_new_subgraph.py`: Subgraph example
    - `generate_fake_rainbows.py`: Synthetic data generation
    - `graph_core.py`: Core graph functionality
    - `graph_schema.py`: Graph schema definitions
    - `kuzu_graph_html.py`: Kuzu graph HTML visualization
    - `rainbow_subgraph.py`: Rainbow subgraph implementation
    - `test_baml_extract.py`: BAML extraction testing
    - `test_graph.py`: Graph functionality testing
    - `test_refactored_ekg.py`: Refactored EKG testing
  - `maintenance_agent/`: System maintenance agent demos
    - `dummy_data.py`: Test data generation
    - `tools.py`: Maintenance tools implementation
  - `mon_master_search/`: Master search functionality
    - `loader.py`: Data loading utilities
    - `model_subset.py`: Model subset management
    - `search.py`: Search implementation
  - `todo/`: Additional demo implementations
    - `20_▫️_CrewAI_demo.py`: CrewAI demonstration
    - `azure_gpt4o.py`: Azure GPT-4o integration
    - `human-in-loop-agent.py`: Human-in-the-loop agent
  - `mergekit.yml`: MergeKit configuration

- `genai_blueprint/webapp/`: Streamlit web application
  - `pages/`: Streamlit page implementations organized by category
    - `demos/`: Main demo pages
      - `mon_master.py`: Hybrid search UI
      - `deep_search_agent.py`: Research agent with logging
      - `codeAct_agent.py`: CodeAct agent implementation
      - `reAct_agent.py`: ReAct agent implementation
      - `graph_RAG.py`: Graph-based RAG demo
      - `anonymization.py`: Presidio anonymization demo
      - `cognee_KG.py`: Cognee knowledge graph demo
      - `deep_agent.py`: Deep agent implementations
      - `maintenance_agent.py`: System maintenance agent
    - `settings/`: Configuration and setup pages
      - `welcome.py`: Welcome and overview page
      - `configuration.py`: System configuration interface
      - `MCP_servers.py`: MCP server management
    - `unmaintained/`: Legacy demo pages (preserved for reference)
      - `12_▫️_Crew_AI.py`: CrewAI demonstration
      - `13_▫️_OCR_Ollama.py`: OCR with Ollama
      - `15_▫️_Chat_Human_in_Loop.py`: Human-in-the-loop chat
      - `20_browser_control.py`: Browser control demo
      - `3_▫️_Stock_Price.py`: Stock price analysis
      - `4_▫️_Dataframe_Agent.py`: Dataframe agent demo
      - `991_ Terminal.py`: Terminal interface demo
      - `991_test scroll.py`: Scroll testing
      - `99_▫️_Folium_Map_State.py`: Folium map visualization
      - `9_▫️_SmollAgent.py`: SmolAgent demonstration
  - `ui_components/`: Reusable Streamlit components
    - `smolagents_streamlit.py`: SmolAgents UI components
    - `streamlit_chat.py`: Helper to display LangGraph chat in Streamlit
    - `config_editor.py`: Configuration editing interface
    - `cypher_graph_display.py`: Cypher graph visualization component
    - `llm_selector.py`: LLM selection component
  - `cli_commands.py`: Webapp-specific CLI commands


#### Utilities and Infrastructure
- `genai_blueprint/utils/`: Utility functions and helpers
  - `streamlit/`: Streamlit-specific utilities
    - `auto_scroll.py`: Auto-scrolling functionality
    - `capturing_callback_handler.py`: Callback handler for capturing
    - `clear_result.py`: State management
    - `recorder.py`: Streamlit action recording
    - `thread_issue_fix.py`: Streamlit threading fixes

- `genai_blueprint/mcp_server/`: MCP server implementations
  - `math_server.py`: Mathematical computation server
  - `tech_news.py`: Technology news server
  - `weather_server.py`: Weather information server

#### Documentation and Examples
- `docs/`: Additional documentation and guides
  - `deep_agent_cli_examples.md`: Deep agent CLI usage examples
- `examples/`: Standalone example implementations
  - `vllm_demo.py`: vLLM inference demo
- `vibe_coding/`: Development conventions and scripts
  - `CONVENTIONS.md`: Coding conventions used by Aider-chat
  - `scripts.md`: Development scripts reference

#### Test Data and Use Cases
- `use_case_data/`: Sample data for testing and demonstrations
  - `generated/`: Generated test data
  - `maintenance/`: Maintenance procedure documents
  - `ocr/`: OCR test images and samples
  - `scientific_papers/`: Research paper PDFs for testing
  - `other/`: Miscellaneous test data (CSV, images, text files)

#### Testing and Development
- `tests/`: Unit and integration tests
  - `unit_tests/`: Unit test implementations
  - `integration_tests/`: Integration test suites
- `genai_blueprint/wip/`: Work in progress and experimental features
- `Makefile`: Common development and deployment tasks

#### Project Root Files
- `Agents.md`: Additional agent documentation and examples
- `package.json` & `package-lock.json`: Node.js dependencies for some components
- `quick_test.py`: Quick testing script for basic functionality verification

#### Deployment
  - `Dockerfile`: Optimized dockerfile
  - `deploy/`: Deployment scripts and configurations
    - `docker.mk` : build and run a container locally
    - `aws.mk` : deploy in AWS
    - `azure.mk` : deploy in Azure
    - `modal.mk` : deploy in Modal


## Streamlit Demos Configuration
- The `Streamit` app can be somewhat configured in `app_conf.yaml`  (key: `ui`).
- Most Demos can be configured with YAML file in `config/demos`


## CLI Usage Examples

**🎯 Works from Any Directory!**
Thanks to the enhanced configuration system, CLI commands work from any project directory:

```bash
# From project root
cd /path/to/genai-blueprint && uv run cli info config

# From notebooks directory
cd /path/to/genai-blueprint/notebooks && uv run cli info config

# From any subdirectory - automatically finds project configuration!
cd /path/to/genai-blueprint/genai_blueprint/demos && uv run cli info config
```

**Available Commands**:
The framework provides extensive CLI commands for AI interactions, implemented in `cli_command.py` files and registered in `app_conf.yaml`:

```bash
uv run cli --help       # List all available commands with descriptions
uv run cli info config  # Show current configuration and available models
```

**Basic LLM Interaction**
```bash
uv run cli core llm "Hello world"              # Simple LLM query
echo "Hello world" | uv run cli core llm       # Pipe input
uv run cli core llm "Hello" --llm gpt-4 --stream  # Use specific model with streaming
uv run cli core run joke --input "bears"       # Run a joke chain
```

**Agent with tools / MCP**
```bash
uv run cli agents mcp --server filesystem --chat        # start interactive shell
echo "get news from atos.net web site" | uv run cli agents mcp --server playwright --server filesystem # ReAct Agent
uv run cli agents smolagents "How many seconds would it take for a leopard at full speed to run through Pont des Arts?" -t web_search  # CodeAct Agent
```

**Deep Agents (Enhanced with beautiful markdown rendering)**
```bash
# Research agent with markdown output
uv run cli agents deep research --input "Latest AI developments" --llm gpt-4

# Coding agent for development tasks
uv run cli agents deep coding --input "Write a Python async web scraper" --llm gpt-4

# Analysis agent for data insights
uv run cli agents deep analysis --input "Analyze sales trends" --files sales_data.csv --llm gpt-4

# Custom agent with specific instructions
uv run cli agents deep custom --input "Plan a project timeline" --instructions "You are a project manager" --llm gpt-4
```

**Knowledge Graph & Document Processing**
```bash
# Extract structured data from documents
uv run cli structured extract "*.md" --schema "project_schema"
uv run cli structured extract-baml "*.md" --class ReviewedOpportunity --force
uv run cli structured gen-fake "projects/*.json" --output-dir ./fake --count 5

# Knowledge graph operations
uv run cli kg add --key project-alpha
uv run cli kg query --query "MATCH (p:Project) RETURN p.name"
uv run cli kg agent --input "Find all Python projects"
uv run cli kg export-html --output-dir ./viz
```

**Utilities**
```bash
uv run cli info models         # List available models
uv run cli info config         # Show current configuration
uv run cli info mcp-tools --filter playwright  # List available MCP tools
uv run cli tools markdownize document.pdf      # Convert documents to markdown
```

## Aditional install (for some demos / components)
**install Ollama**
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama run gemma3:4b   # example LLM
ollama pull snowflake-arctic-embed:22m  # example embeddings
```
**Install Chrome and Playwright**
```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install ./google-chrome-stable_current_amd64.deb
uv add playwright
playwright install --with-deps
```

**Spacy models in uv**
```bash
uv pip install pip
uv run --with spacy spacy download fr_core_news_sm
uv run --with spacy spacy download en_core_web_lg 
```
or 
```bash
make install_spacy_models
```

**Install Node (for some MCP servers)** 
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh | bash
nvm install --lts
```

## 🔧 Troubleshooting

### Configuration Issues

**Problem**: `AssertionError: cannot find config file` when running from subdirectories

**Solution**: ✅ **Fixed!** The enhanced configuration system now automatically searches parent directories for config files. Commands work from any project directory:

```bash
# All of these work now:
cd /project/root && uv run cli info config
cd /project/root/notebooks && uv run cli info config  
cd /project/root/genai_blueprint/demos && uv run cli info config
```

### Dependency Issues

**Problem**: `ModuleNotFoundError: No module named 'langchain_postgres'`

**Solution**: ✅ **Fixed!** Optional dependencies are now handled gracefully. Missing packages won't break the system.

### Directory Rename Issues

**Problem**: Build errors after renaming the `src/` directory

**Solution**: ✅ **Fixed!** All configuration files and path references have been updated to use the new `genai_blueprint/` directory structure.

### Development Workflow

For local development with both projects:

```bash
# Use PYTHONPATH for development (optional)
export GENAI_DEV_PATH="/path/to/local/genai-tk:$PYTHONPATH"
alias uv-dev="PYTHONPATH=$GENAI_DEV_PATH uv"

# Then use uv-dev for development:
uv-dev run cli info config
```

Or rely on the standard Git dependency system - just push changes to genai-tk and run:
```bash
uv cache clean genai-tk && uv sync -U
```
