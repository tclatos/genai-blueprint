# GenAI Blueprint Agents and Applications

This document outlines the specific agents, applications, and use cases implemented in the GenAI Blueprint (`genai_bp`). This package builds on the GenAI Toolkit (`genai_tk`) to provide ready-to-use applications and demonstrations.

## Overview

GenAI Blueprint provides:
- **Ready-to-use Applications** - Complete applications built with the toolkit
- **Demo Applications** - Working examples and prototypes
- **Web Interface** - Streamlit-based user interfaces
- **CLI Tools** - Command-line interfaces for common tasks
- **Integration Examples** - Real-world integration patterns

## Application Structure

### Main Applications (`src/main/`)

#### CLI Application (`cli.py`)
Command-line interface providing access to core AI functionality:
```bash
# Run a joke agent
cli run joke "Tell me a joke about programming"

# Run with specific model
cli run joke -m openai/gpt-4 "Tell me a technical joke"
```

#### Web Applications
- **Streamlit App** (`streamlit.py`) - Main web interface for interactive AI experiences
- **FastAPI App** (`fastapi_app.py`) - REST API backend for AI services  
- **LangServe App** (`langserve_app.py`) - LangChain serving for production deployment
- **Modal App** (`modal_app.py`) - Serverless deployment configuration

### Demo Applications (`src/demos/`)

#### Enterprise Knowledge Graph (`ekg/`)
Comprehensive knowledge graph solution for enterprise documents:

**Components:**
- **Graph Core** (`graph_core.py`) - Core graph operations and schema
- **BAML Integration** (`baml_src/`, `cli_commands_baml.py`) - Structured data extraction
- **Ladybug Database** - Graph database backend with Cypher queries (Kuzu-compatible maintained fork)
- **Document Processing** (`struct_rag_doc_processing.py`) - RAG with structured extraction
- **CLI Tools** (`cli_commands_ekg.py`) - Command-line management interface

**Capabilities:**
- Document ingestion and graph construction
- Semantic search over knowledge graphs  
- Structured question answering
- Graph visualization and exploration

#### Deep Agents (`deep_agents/`)
Advanced reasoning agents for complex tasks:
- **Research Agent** (`research_agent_example.py`) - Automated research and synthesis
- **Coding Agent** (`coding_agent_example.py`) - Code analysis and generation

#### Maintenance Agent (`maintenance_agent/`)
Industrial maintenance assistant:
- **Tools** (`tools.py`) - Maintenance-specific tool integrations
- **Data** (`dummy_data.py`) - Sample maintenance procedures and workflows

#### Master Search (`mon_master_search/`)
Advanced search capabilities across document collections:
- **Search Engine** (`search.py`) - Multi-modal search implementation
- **Document Loader** (`loader.py`) - Document processing and indexing
- **Model Integration** (`model_subset.py`) - Optimized model subsets for search

### Web Interface (`genai_blueprint/webapp/`)

#### Streamlit Pages

**Training & Learning** (`pages/training/`)
- **Embeddings Explorer** (`embeddings.py`) - Interactive embeddings visualization
- **Runnable Playground** (`runnable_playground.py`) - LangChain runnable testing
- **CLI Runner** (`CLI_runner.py`) - Web-based CLI execution
- **Tokenization** (`tokenization.py`) - Token analysis and visualization

**Demo Showcase** (`pages/demos/`)
- **ReAct Agent** (`reAct_agent.py`) - Interactive ReAct pattern demonstration
- **Deep Agent** (`deep_agent.py`) - Deep reasoning agent interface  
- **Code Agent** (`codeAct_agent.py`) - Code-focused agent interactions
- **Graph RAG** (`graph_RAG.py`) - Knowledge graph RAG demonstration
- **Cognee KG** (`cognee_KG.py`) - Cognee knowledge graph integration
- **Anonymization** (`anonymization.py`) - PII detection and anonymization demo
- **Maintenance Agent** (`maintenance_agent.py`) - Industrial maintenance interface

**Configuration** (`pages/settings/`)
- **Configuration Editor** (`configuration.py`) - Interactive config management
- **MCP Servers** (`MCP_servers.py`) - Model Context Protocol server management
- **Welcome** (`welcome.py`) - Onboarding and system overview

#### UI Components (`ui_components/`)
- **LLM Selector** (`llm_selector.py`) - Model selection interface
- **SmolAgents Integration** (`smolagents_streamlit.py`) - SmolAgents web interface
- **Chat Interface** (`streamlit_chat.py`) - Chat UI components
- **Config Editor** (`config_editor.py`) - Configuration editing widgets
- **Graph Display** (`cypher_graph_display.py`) - Graph visualization components

### Processing Chains (`src/ai_chains/`)

#### Basic Examples
- **Joke Chain** (`A_1_joke.py`) - Simple LLM interaction example
- **Naive RAG** (`B_1_naive_rag_example.py`) - Basic RAG implementation
- **Self Query** (`B_2_self_query.py`) - Self-querying retrieval
- **Tools Example** (`C_1_tools_example.py`) - Tool use demonstration

#### Advanced Patterns
- **Advanced RAG** (`C_2_advanced_rag_langgraph.py`) - LangGraph-based RAG
- **Agentic RAG** (`C_2_Agentic_Rag_Functional.py`) - Agent-driven retrieval
- **Essay Writer** (`C_3_essay_writer_agent.py`) - Long-form content generation
- **Structured Output** (`C_4_agent_structured_output.py`) - Type-safe agent responses

### MCP Servers (`src/mcp_server/`)

Model Context Protocol servers for tool integration:
- **Math Server** (`math_server.py`) - Mathematical computation server
- **Weather Server** (`weather_server.py`) - Weather information server  
- **Tech News** (`tech_news.py`) - Technology news aggregation

## Key Use Cases

### 1. Enterprise Document Processing
Transform unstructured documents into queryable knowledge graphs:
- PDF/document ingestion
- Entity extraction and relationship mapping
- Semantic search and Q&A
- Graph visualization and exploration

### 2. Industrial Maintenance
AI-powered maintenance assistance:
- Procedure lookup and guidance
- Equipment troubleshooting
- Maintenance scheduling optimization
- Knowledge base integration

### 3. Research and Analysis
Automated research workflows:
- Multi-source information gathering
- Content synthesis and summarization  
- Citation tracking and verification
- Report generation

### 4. Code Analysis and Generation
Software development assistance:
- Code review and analysis
- Bug detection and fixing suggestions
- Documentation generation
- Architecture recommendations

### 5. Data Analysis and Visualization
Interactive data exploration:
- DataFrame manipulation and analysis
- Chart generation and visualization
- Statistical analysis and insights
- Data quality assessment

## Configuration and Deployment

### Development
```bash
# Install with development dependencies
uv sync

# Run Streamlit app
make webapp

# Run CLI tools
uv run cli --help
```

### Production Deployment

**Streamlit Cloud:**
```bash
streamlit run genai_blueprint/main/streamlit.py
```

**FastAPI with Uvicorn:**
```bash
uvicorn src.main.fastapi_app:app --reload
```

**Modal Serverless:**
```bash
modal deploy src/main/modal_app.py
```

**Docker:**
```bash
docker build -f deploy/Dockerfile -t genai-bp .
docker run -p 8501:8501 genai-bp
```

## Integration Examples

### Custom Agent Creation
```python
from genai_tk.core import LLMFactory
from genai_tk.extra.graphs import CustomReactAgent

# Create custom agent for specific use case
llm = LLMFactory.create("openai/gpt-4")
agent = CustomReactAgent(llm=llm)

# Add custom tools
from genai_blueprint.demos.maintenance_agent.tools import get_maintenance_tools
agent.tools.extend(get_maintenance_tools())
```

### Knowledge Graph Integration
```python
from genai_blueprint.demos.ekg.graph_core import EKGGraphCore
from genai_tk.extra.cognee_utils import CogneeUtils

# Initialize knowledge graph
graph = EKGGraphCore()
graph.initialize_schema()

# Process documents
documents = ["path/to/docs/*.pdf"]
graph.ingest_documents(documents)

# Query graph
result = graph.query("What are the main risk factors?")
```

### Streamlit Integration
```python
import streamlit as st
from genai_tk.core import LLMFactory
from genai_blueprint.utils.streamlit import CapturingCallbackHandler

# Create interactive agent interface
llm = LLMFactory.create("openai/gpt-4")
callback_handler = CapturingCallbackHandler()

with st.chat_message("assistant"):
    response = llm.invoke(
        user_input, 
        callbacks=[callback_handler]
    )
    st.write(response)
```

## Testing and Validation

### Unit Tests
```bash
# Run all tests
make test

# Run specific test categories
pytest unit_tests/
pytest integration_tests/
```

### Integration Testing
```bash
# Test installation and dependencies
make test-install

# Test specific demo applications
python src/demos/ekg/test_graph.py
python src/demos/deep_agents/research_agent_example.py
```

## Related Documentation

- **GenAI Toolkit** - See `genai_tk/Agents.md` for core component documentation
- **Configuration** - Configuration management and environment setup
- **Deployment** - Production deployment patterns and best practices
- **API Reference** - Complete API documentation for all modules

This blueprint provides a comprehensive foundation for building production AI applications while maintaining flexibility for customization and extension.