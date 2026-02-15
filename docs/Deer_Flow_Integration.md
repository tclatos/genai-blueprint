# Deer-flow Integration Guide

## Overview

This document describes the integration of [Deer-flow](https://github.com/bytedance/deer-flow) (ByteDance's LangGraph-based agent system) into GenAI Blueprint. The integration enables Deer-flow agents to run within the GenAI Blueprint Streamlit interface while sharing resources like MCP servers, tools, and LLM configurations.

**Key Design Principles:**
- ✅ **Zero modifications** to deer-flow backend code
- ✅ **Resource sharing** - deer-flow agents use GenAI Blueprint's MCP servers, tools, and LLM configurations
- ✅ **Config bridge** - automatic translation from GenAI Blueprint YAML configs to deer-flow format
- ✅ **Unified UI** - consistent Streamlit interface across all agent runtimes
- ✅ **Direct in-process** - no separate server processes required

## Architecture

### Integration Approach

The integration uses a **Direct In-Process** pattern:

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Process                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  deer_flow_agent.py (Streamlit Page)                 │   │
│  └────────────────┬─────────────────────────────────────┘   │
│                   │                                          │
│  ┌────────────────▼─────────────────────────────────────┐   │
│  │  genai_blueprint/deer_flow/agent.py                  │   │
│  │  • Profile loading (deerflow.yaml)                   │   │
│  │  • Tool resolution (GenAI BP tool factories)         │   │
│  │  • Config bridge (YAML → deer-flow format)           │   │
│  └────────────────┬─────────────────────────────────────┘   │
│                   │                                          │
│  ┌────────────────▼─────────────────────────────────────┐   │
│  │  deer-flow/backend (via sys.path)                    │   │
│  │  • make_lead_agent() → CompiledStateGraph            │   │
│  │  • Middlewares, tools, subagents                     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Why Direct In-Process?**
- Simpler deployment (no nginx, no separate LangGraph Server)
- Lower latency (no HTTP overhead)
- Easier debugging (single process)
- Better resource sharing (same Python process)

### Component Overview

#### 1. Path Setup (`genai_blueprint/deer_flow/_path_setup.py`)
Resolves the deer-flow backend location and adds it to `sys.path`:

**Search order:**
1. `DEER_FLOW_PATH` environment variable
2. `ext/deer-flow/backend` (relative to project root)
3. `../deer-flow/backend` (parallel directory)
4. `~/ext_prj/deer-flow/backend` (home directory)

**Sets environment variables:**
- `DEER_FLOW_CONFIG_PATH` - Points to deer-flow root for config file generation

#### 2. Config Bridge (`genai_blueprint/deer_flow/config_bridge.py`)
Translates GenAI Blueprint configurations into deer-flow's expected format:

**Inputs:**
- `config/providers/llm.yaml` - LLM provider configurations
- `config/mcp_servers.yaml` - MCP server definitions
- GenAI Blueprint tool configurations

**Outputs:**
- `<deer-flow-root>/config.yaml` - Deer-flow model configurations
- `<deer-flow-root>/extensions_config.json` - MCP server configurations

**Example model translation:**
```yaml
# GenAI Blueprint (llm.yaml)
ollama:
  base_url: http://localhost:11434
  models:
    - llama3.2:latest
    - qwen2.5-coder:32b

# Generated deer-flow (config.yaml)
models:
  - name: ollama/llama3.2:latest
    provider: ollama
    base_url: http://localhost:11434
  - name: ollama/qwen2.5-coder:32b
    provider: ollama
    base_url: http://localhost:11434
```

**Example MCP translation:**
```yaml
# GenAI Blueprint (mcp_servers.yaml)
tavily-mcp:
  command: uvx
  args: [tavily-mcp-server]
  env:
    TAVILY_API_KEY: ${TAVILY_API_KEY}

# Generated deer-flow (extensions_config.json)
{
  "mcp": {
    "servers": {
      "tavily-mcp": {
        "command": "uvx",
        "args": ["tavily-mcp-server"],
        "env": {"TAVILY_API_KEY": "..."}
      }
    }
  }
}
```

#### 3. Agent Wrapper (`genai_blueprint/deer_flow/agent.py`)

**Key Functions:**

- **`load_deer_flow_profiles()`** - Loads agent profiles from `config/agents/deerflow.yaml`
- **`resolve_tools_from_config()`** - Resolves GenAI Blueprint tool specifications:
  ```yaml
  # Profile with tool factory
  tools:
    - factory: create_sql_tool_from_config
      config:
        database: chinook
        dialect: sqlite
  ```
- **`create_deer_flow_agent_simple()`** - Main entry point:
  1. Setup deer-flow path
  2. Generate config files
  3. Resolve tools from profile
  4. Create agent via deer-flow's `make_lead_agent()`
  5. Return `CompiledStateGraph` with combined tools

**Profile Structure:**
```python
@dataclass
class DeerFlowAgentConfig:
    name: str                          # Display name
    description: str                   # Description for UI
    tool_groups: List[str]             # e.g., ["web", "file", "bash"]
    subagent_enabled: bool = True      # Enable subagent spawning
    thinking_enabled: bool = True      # Enable chain-of-thought
    mcp_servers: List[str] = []        # MCP server names to include
    tool_configs: List[Dict] = []      # Additional tool specifications
    features: List[str] = []           # Feature badges for UI
    example_queries: List[str] = []    # Example prompts
```

#### 4. Streamlit Page (`genai_blueprint/webapp/pages/demos/deer_flow_agent.py`)

**UI Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  Sidebar                │  Main Area                        │
│  ───────────            │  ──────────                       │
│  • LLM Selector         │  ┌──────────┬──────────┐          │
│  • Config Editor        │  │ Trace    │ Chat     │          │
│  • Profile Picker       │  │ (Left)   │ (Right)  │          │
│  • Feature Badges       │  │          │          │          │
│  • Example Queries      │  │ Thought  │ Messages │          │
│  • Clear Buttons        │  │ Tool Use │ Input    │          │
│                         │  └──────────┴──────────┘          │
└─────────────────────────────────────────────────────────────┘
```

**Key Features:**
- **Async streaming** - Real-time agent output via `agent.astream()`
- **Interleaved traces** - Shows reasoning steps alongside chat
- **Profile switching** - Change agent capabilities on the fly
- **LangSmith integration** - Links to trace viewer

## Installation

### 1. Clone Deer-flow Backend

```bash
# Option 1: Use Makefile (recommended)
make deer-flow-install

# Option 2: Manual clone
git clone --depth 1 https://github.com/bytedance/deer-flow.git ext/deer-flow
```

The deer-flow backend will be cloned to `ext/deer-flow/` or can be placed in any location specified by `DEER_FLOW_PATH`.

### 2. Install Dependencies

```bash
# Install deer-flow dependency group
uv sync --group deerflow

# Or with pip
pip install -e '.[deerflow]'
```

**Installed dependencies:**
- `agent-sandbox>=0.0.19` - Sandboxed code execution
- `markitdown[all,xlsx]>=0.0.1a2` - Document conversion
- `readabilipy>=0.3.0` - Web page readability
- `ddgs>=9.10.0` - DuckDuckGo search
- `langchain-mcp-adapters>=0.1.0` - MCP integration
- `langchain-deepseek>=1.0.1` - DeepSeek models
- `markdownify>=1.2.2` - HTML to Markdown
- `duckdb>=1.4.4` - Embedded database

### 3. Verify Installation

```bash
# Run validation script
python -c "
from genai_blueprint.deer_flow import setup_deer_flow_path
path = setup_deer_flow_path()
print(f'✅ Deer-flow backend found: {path}')
"
```

## Configuration

### Agent Profiles

Agent profiles are defined in `config/agents/deerflow.yaml`. Each profile specifies:

```yaml
profiles:
  - name: "Research Assistant"
    description: "Web research with subagents and knowledge graphs"
    tool_groups:
      - web
    subagent_enabled: true
    thinking_enabled: true
    mcp_servers:
      - tavily-mcp
    features:
      - "🌐 Web Search"
      - "🤖 Subagents"
      - "🧠 Deep Thinking"
    example_queries:
      - "Research the latest developments in quantum computing"
      - "Compare different approaches to RAG systems"
```

### Available Tool Groups

Deer-flow provides several predefined tool groups:

| Group | Tools | Description |
|-------|-------|-------------|
| `web` | web_search, web_fetch, extract_page_content | Web browsing and search |
| `file` | read_file, write_file, list_directory | File operations |
| `bash` | run_bash_command | Shell command execution |
| `image` | generate_image, analyze_image | Image generation/analysis |
| `skills` | Various | User-defined Python functions |

### Custom Tools via GenAI Blueprint

You can add GenAI Blueprint tools to profiles:

```yaml
profiles:
  - name: "Database Analyst"
    tool_groups:
      - web
    tool_configs:
      # Tool factory pattern
      - factory: create_sql_tool_from_config
        config:
          database: chinook
          dialect: sqlite
          
      # Direct function reference
      - function: genai_tk.tools.data_analysis.analyze_dataframe
      
      # Class instantiation
      - class: langchain_community.tools.DuckDuckGoSearchRun
        kwargs:
          max_results: 5
```

### MCP Server Configuration

MCP servers are automatically shared from GenAI Blueprint:

```yaml
# config/mcp_servers.yaml
mcp_servers:
  tavily-mcp:
    command: uvx
    args: [tavily-mcp-server]
    env:
      TAVILY_API_KEY: ${TAVILY_API_KEY}
      
  weather-mcp:
    command: python
    args: [genai_blueprint/mcp_server/weather_server.py]
```

Reference them in profiles:
```yaml
profiles:
  - name: "Weather Agent"
    mcp_servers:
      - weather-mcp
      - tavily-mcp
```

## Usage

### Running the Streamlit App

```bash
# Start the web app
make webapp

# Or directly
streamlit run genai_blueprint/main/streamlit.py
```

Navigate to **Demos → Deer-flow Agent** in the sidebar.

### Using the Interface

1. **Select LLM** - Choose model from sidebar (e.g., `ollama/llama3.2:latest`)
2. **Choose Profile** - Select agent configuration from dropdown
3. **View Features** - Check enabled capabilities in feature badges
4. **Try Examples** - Click example queries or type your own
5. **Monitor Traces** - Watch agent reasoning in left panel
6. **See Results** - View responses in right panel

### Programmatic Usage

```python
from genai_tk.core.llm_factory import get_llm
from genai_blueprint.deer_flow.agent import (
    load_deer_flow_profiles,
    create_deer_flow_agent_simple
)

# Load profiles
profiles = load_deer_flow_profiles()
research_profile = next(p for p in profiles if p.name == "Research Assistant")

# Create agent
llm = get_llm("ollama/llama3.2:latest")
agent = create_deer_flow_agent_simple(
    llm=llm,
    profile=research_profile
)

# Run query
config = {"configurable": {"thread_id": "my-thread"}}
result = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Search for AI papers"}]},
    config=config
)
```

### Streaming Usage

```python
async for chunk in agent.astream(
    {"messages": [{"role": "user", "content": "Research topic"}]},
    config=config
):
    if "messages" in chunk:
        print(chunk["messages"][-1])
    if "thinking" in chunk:
        print(f"💭 {chunk['thinking']}")
```

## Agent Modes

Deer-flow supports four agent modes that control behavior and capabilities:

| Mode | Thinking | Planning | Subagents | Best For |
|------|----------|----------|-----------|----------|
| **Flash** | ❌ | ❌ | ❌ | Quick answers, simple queries |
| **Thinking** | ✅ | ❌ | ❌ | Reasoning tasks, analysis |
| **Pro** | ✅ | ✅ | ❌ | Complex research, multi-step tasks |
| **Ultra** | ✅ | ✅ | ✅ | Large projects, parallel execution |

**Configuration:**
```yaml
profiles:
  - name: "Quick Assistant"
    mode: "flash"  # Fast, no thinking overhead
    
  - name: "Research Agent"
    mode: "pro"    # Planning with todo lists
    
  - name: "Full-Power"
    mode: "ultra"  # All features enabled
```

**Mode Behaviors:**
- **Flash**: Direct answers without chain-of-thought. Fastest response time.
- **Thinking**: Shows reasoning steps. Good for complex questions.
- **Pro**: Creates and maintains todo lists for multi-step tasks. Shows progress tracking.
- **Ultra**: Can spawn subagents for parallel execution. Best for large, complex projects.

## Skills Library

### Built-in Deer-flow Skills

Deer-flow includes 16 public skills in `/skills/public/`:

| Skill | Description | Tools Used |
|-------|-------------|------------|
| **deep-research** | Multi-source research with synthesis | Web search, content extraction |
| **data-analysis** | DataFrame analysis and insights | Python, pandas, matplotlib |
| **chart-visualization** | Create charts from data | Plotting libraries |
| **github-deep-research** | Analyze GitHub repositories | GitHub API, code analysis |
| **image-generation** | Generate images from prompts | Image generation APIs |
| **video-generation** | Create videos programmatically | Video processing tools |
| **podcast-generation** | Generate podcast episodes | TTS, audio processing |
| **ppt-generation** | Create PowerPoint presentations | Office automation |
| **frontend-design** | Design UI mockups | Design tools |
| **consulting-analysis** | Business analysis | Research, data tools |
| **skill-creator** | Create new skills | Code generation |
| **find-skills** | Search available skills | Skill registry |
| **surprise-me** | Random creative task | Various |
| **web-design-guidelines** | Web design best practices | Design knowledge |
| **vercel-deploy-claimable** | Deploy to Vercel | Deployment tools |

### Adding Skills to Profiles

```yaml
deerflow_agents:
  - name: "Data Analyst"
    mode: "pro"
    skills:
      - data-analysis          # Public skill (implicit public/ prefix)
      - chart-visualization
      - deep-research
    
  - name: "Developer"
    skills:
      - public/github-deep-research   # Explicit category
      - custom/my-company-skill       # Custom skill
```

### Custom GenAI Blueprint Skills

You can integrate custom tools as skills:

```yaml
deerflow_agents:
  - name: "Custom Agent"
    skills:
      - data-analysis
    tools:
      # GenAI Blueprint tool factory
      - factory: my_module.create_custom_tool
        config:
          api_key: ${MY_API_KEY}
```

## UI Features

### Artifacts Viewer

The Deer-flow UI displays generated artifacts (code, documents, data files):

- **Code blocks** - Syntax-highlighted with copy button
- **Data tables** - Rendered as DataFrames
- **Images** - Inline display with zoom
- **Documents** - Formatted previews

**In agent output:**
```python
# Agent saves artifact
state["artifacts"].append("analysis_report.md")
```

**UI displays:**
```
📄 Artifacts (2)
├── analysis_report.md
└── chart.png [Click to view]
```

### Mermaid Diagram Rendering

Agents can generate interactive diagrams using Mermaid syntax:

**Agent response with diagram:**
```markdown
Here's a diagram of the architecture:

flowchart TD
    A[Input] --> B[Process]
    B --> C[Output]
```

**UI renders as:**
- 🎨 **Interactive SVG diagram** - Not code blocks
- ✨ **Automatic detection** - Both fenced (` ```mermaid`) and bare syntax
- 🖼️ **Iframe embedding** - Uses Mermaid.js v11 from CDN via `st.components.html()`
- 📐 **Responsive layout** - 400px height with scrolling for large diagrams

**Supported diagram types:**
- `flowchart`, `graph` - Node-link diagrams
- `sequenceDiagram` - Interaction flows
- `classDiagram` - Class relationships
- `stateDiagram` - State machines
- `erDiagram` - Entity-relationship models
- `gantt` - Project timelines
- `pie` - Pie charts
- `journey` - User journeys
- Plus: `gitGraph`, `mindmap`, `timeline`, `sankey`, `block`

**Technical implementation:**
- Uses `genai_blueprint.webapp.ui_components.message_renderer.render_message_with_mermaid()`
- Embeds Mermaid.js library via HTML component (no separate package required)
- Matches deer-flow's frontend diagram capabilities

### Todo List Tracking

In `pro` and `ultra` modes, agents use TodoListMiddleware to track progress:

**Agent creates todos:**
```
📋 Todo List
├── ✅ Research quantum computing papers
├── 🔄 Analyze key findings
└── ⏳ Write summary report
```

**Real-time updates:**
- Agent marks tasks as in-progress, completed, or failed
- UI shows live progress as agent works
- Helps users understand multi-step workflows

### Image Viewer

Agents can generate or analyze images:

**Generated images appear inline:**
```
🖼️ Generated: landscape.png
[Image preview]
[Download] [View Full Size]
```

**Viewed images from agent analysis:**
```
Agent: "Analyzing the uploaded chart..."
🔍 Viewing: sales_chart.png
[Image preview with agent annotations]
```

### Mode Selector

Switch modes on-the-fly in the sidebar:

```
⚡ Mode: Flash  ▼
├── Flash (current)
├── Thinking
├── Pro
└── Ultra
```

Changing mode updates agent behavior immediately for new conversations.

### 6. Visual Explainer
**Best for:** Direct explanations with diagrams (e.g., "Explain MOE to a 12-year-old")

**Capabilities:**
- Chart and diagram generation
- Clear explanations with visuals
- Web research for accuracy
- Minimal clarification questions

**Example queries:**
- "Explain what MOE is to a 12-year-old boy"
- "Explain transformer architecture with a diagram"
- "Create a flowchart of the RAG pipeline"

**Why this profile exists:**
This profile is specifically optimized for queries like the deer-flow demo's "Explain MOE" example. It:
- Uses `thinking` mode (reasoning without excessive planning)
- Includes `chart-visualization` skill for diagrams
- Has `file` and `bash` tool groups enabled for diagram generation
- Configured to give direct answers with visual aids

## Example Workflows

### 1. Research Assistant
**Best for:** Literature review, competitive analysis, market research

**Capabilities:**
- Web search with multiple sources
- Subagent spawning for parallel research
- Knowledge graph construction
- Citation tracking

**Example queries:**
- "Research the latest developments in quantum computing"
- "Compare different approaches to RAG systems"
- "What are the main competitors in the AI agent space?"

### 2. Coder
**Best for:** Code analysis, debugging, system design

**Capabilities:**
- File operations (read/write)
- Bash command execution
- Web research for documentation
- Subagents for complex tasks

**Example queries:**
- "Analyze the codebase structure and suggest improvements"
- "Debug why my Flask app is returning 500 errors"
- "Create a REST API for user authentication"

### 3. Web Browser
**Best for:** Web scraping, content extraction, monitoring

**Capabilities:**
- Full web browsing with Playwright
- Content extraction and summarization
- Screenshot capture
- Multi-page workflows

**Example queries:**
- "Extract all product prices from this e-commerce site"
- "Monitor HackerNews for mentions of LangChain"
- "Summarize the main topics from this blog post"

### 4. Database + Research
**Best for:** Data analysis with context from web

**Capabilities:**
- SQL query execution (Chinook DB)
- Web search for context
- Data visualization recommendations
- MCP tools (Tavily search)

**Example queries:**
- "Query the Chinook database: which artists have the most tracks?"
- "Find which genres are most popular and research why"
- "Analyze customer purchase patterns"

### 5. Weather & Files
**Best for:** File operations with external data

**Capabilities:**
- File read/write operations
- Weather information (via MCP)
- PowerPoint generation (via MCP)
- Web research

**Example queries:**
- "Check the weather in Tokyo and summarize it in a report"
- "Create a PowerPoint presentation about climate change"
- "Read my notes and organize them by topic"

## Technical Details

### Compatibility Matrix

| Component | GenAI Blueprint | Deer-flow | Compatible |
|-----------|----------------|-----------|------------|
| LangChain | 1.2.7 | 1.2.3 | ✅ Yes |
| LangGraph | 1.0.7 | 1.0.6 | ✅ Yes |
| langchain-mcp-adapters | 0.2.1 | 0.1.0 | ✅ Yes |
| Python | 3.11+ | 3.11+ | ✅ Yes |

### Agent Creation Flow

```python
# High-level flow in create_deer_flow_agent_simple()

1. setup_deer_flow_path()
   → Adds deer-flow/backend to sys.path
   
2. setup_deer_flow_config(mcp_server_names)
   → Generates config.yaml with models
   → Generates extensions_config.json with MCP servers
   
3. resolve_tools_from_config(profile.tool_configs)
   → Resolves GenAI Blueprint tool factories
   → Returns List[BaseTool]
   
4. make_lead_agent(config) or create_agent_with_extra_tools()
   → Creates CompiledStateGraph
   → Includes deer-flow built-in tools + extra tools
   → Applies 11 middlewares (ThreadData, Sandbox, Memory, etc.)
   
5. Return CompiledStateGraph
   → Ready for .ainvoke() or .astream()
```

### Generated File Locations

The config bridge writes files to the deer-flow backend root:

```
deer-flow/
├── backend/
│   └── src/          # Deer-flow source code (untouched)
├── config.yaml       # Generated models config (gitignored)
└── extensions_config.json  # Generated MCP config (gitignored)
```

**Note:** These files are gitignored by deer-flow's `.gitignore`, so they won't dirty the deer-flow repository.

### Tool Resolution Details

GenAI Blueprint tool specifications are resolved using `genai_tk`'s tool loading system:

**Factory pattern:**
```yaml
- factory: create_sql_tool_from_config
  config: {...}
```
→ Calls `genai_tk.tools.factories.create_sql_tool_from_config(config)`

**Function pattern:**
```yaml
- function: genai_tk.tools.data_analysis.analyze_dataframe
```
→ Imports and wraps function as LangChain tool

**Class pattern:**
```yaml
- class: langchain_community.tools.DuckDuckGoSearchRun
  kwargs: {max_results: 5}
```
→ Instantiates class with kwargs

### Memory and Checkpointing

Deer-flow agents use LangGraph's checkpointing for conversation memory:

- **Thread-based:** Each conversation has a unique `thread_id`
- **Persistent:** Stored in memory (can be configured for PostgreSQL/Redis)
- **Resumable:** Can continue conversations across sessions

```python
config = {
    "configurable": {
        "thread_id": "user-123-session-456",
        "model_name": "ollama/llama3.2:latest"
    }
}
```

## Troubleshooting

### Agent asks questions instead of directly answering

**Behavior:** Agent uses clarification questions like "What aspect would you like me to focus on?"

**Cause:** Deer-flow includes a `ClarificationMiddleware` that gives the agent an `ask_clarification` tool. Some models (especially instruction-tuned models like GPT-4o) are trained to ask clarifying questions for ambiguous requests.

**Solutions:**
1. **Be more specific** in your prompts:
   - ❌ "Explain MOE"
   - ✅ "Explain what MOE (Mixture of Experts) is to a 12-year-old boy using simple language and diagrams"

2. **Use appropriate mode**:
   - `flash` mode: Gives direct answers without much deliberation
   - `thinking`/`pro`/`ultra`: May ask clarifying questions for better results

3. **Prepend "directly"**: "Directly explain what MOE is..."

**Note:** This is a deer-flow feature, not a bug. The agent asks questions when it needs more context to provide a better answer.

### No diagrams or visualizations in response

**Behavior:** Text-only responses for queries that would benefit from diagrams (e.g., "Explain MOE")

**Cause:** Profile missing visualization skills or required tool groups.

**Solutions:**

1. **Enable chart-visualization skill**:
   ```yaml
   deerflow_agents:
     - name: "Research Assistant"
       skills:
         - deep-research
         - chart-visualization  # Add this
   ```

2. **Add required tool groups**:
   ```yaml
   deerflow_agents:
     - name: "Research Assistant"
       tool_groups:
         - web
         - file   # Required for saving charts
         - bash   # Required for running generation scripts
   ```

3. **Request diagrams explicitly**:
   - ✅ "Explain MOE with a diagram showing how experts are selected"
   - ✅ "Create a flowchart explaining the transformer architecture"
   - ✅ "Draw a mind map of deep learning concepts"

**Available visualization skills:**
- `chart-visualization` - Generates Mermaid diagram syntax (26 types: flowcharts, mind maps, network graphs, etc.)
- `image-generation` - AI-generated artistic images (requires image generation API)

**Mermaid rendering:**
- ✅ **Automatic** - Diagrams render as interactive SVGs (not code blocks)
- ✅ **Detection** - Works with both ` ```mermaid` fences and bare syntax
- ✅ **Auto-fix** - Labels with special chars (`:`, `()`, `·`, `^`) are automatically quoted
- ✅ **UI Component** - Uses `render_message_with_mermaid()` with Mermaid.js v11 via HTML component
- ✅ **No packages needed** - Embeds Mermaid.js from CDN, no separate installation

**Special character handling:**
```mermaid
# Agent generates (with special chars):
graph TD
    A[Input] --> B[Process: Query, Key]
    B --> C[Attention (Q·K^T)]

# Auto-fixed to:
graph TD
    A[Input] --> B["Process: Query, Key"]
    B --> C["Attention (Q·K^T)"]
```

**Why deer-flow demo shows diagrams:**
- Skills are pre-enabled in deer-flow's default config
- Models may be prompted to use visualizations more proactively
- Skills directory is mounted in sandbox with file/bash tools enabled
- ✅ Frontend renders Mermaid automatically (GenAI Blueprint now does too!)

### Deer-flow backend not found

**Error:** `FileNotFoundError: Deer-flow backend not found...`

**Solutions:**
1. Run `make deer-flow-install` to clone the repository
2. Set `DEER_FLOW_PATH` environment variable to your clone location
3. Verify clone exists: `ls ext/deer-flow/backend/src`

### Missing dependencies

**Error:** `ModuleNotFoundError: No module named 'agent_sandbox'`

**Solution:**
```bash
uv sync --group deerflow
```

### Model not available

**Error:** Agent fails to start or uses wrong model

**Solutions:**
1. Check LLM is running: `curl http://localhost:11434/api/tags` (for Ollama)
2. Verify API keys are set in `.env`
3. Check model name matches provider format: `ollama/llama3.2:latest`
4. Review generated `config.yaml` in deer-flow root

### MCP server connection failed

**Error:** Agent starts but MCP tools missing

**Solutions:**
1. Test MCP server manually:
   ```bash
   python genai_blueprint/mcp_server/weather_server.py
   ```
2. Check server command is correct in `mcp_servers.yaml`
3. Verify API keys in environment variables
4. Review `extensions_config.json` in deer-flow root

### Agent runs but tools not working

**Error:** Tools appear in agent but fail when called

**Solutions:**
1. Check tool factory config is valid
2. Test tool directly:
   ```python
   from genai_tk.tools.factories import create_sql_tool_from_config
   tool = create_sql_tool_from_config({"database": "chinook"})
   result = tool.invoke("SELECT * FROM artists LIMIT 1")
   ```
3. Review trace logs in UI for error details

### Config files show old values

**Error:** Agent uses stale configuration

**Solutions:**
1. Restart Streamlit app to regenerate configs
2. Manually delete generated files:
   ```bash
   rm ext/deer-flow/config.yaml
   rm ext/deer-flow/extensions_config.json
   ```
3. Clear Streamlit cache: `st.cache_data.clear()` in sidebar

## Recommended Models

Different models behave differently with deer-flow. Here's a guide:

### For Direct Answers (Less Questioning)
- **Llama 3.3 70B** - Great balance of capability and directness
- **Qwen 2.5 Coder 32B** - Excellent for technical explanations
- **DeepSeek R1** - Strong reasoning without excessive questioning
- **Claude Sonnet 3.5** - Good balance when properly prompted

### For Interactive Work (More Clarification)
- **GPT-4o** - Asks clarifying questions frequently, good for exploratory work
- **GPT-4.1** - Similar to GPT-4o, emphasizes understanding user intent
- **Claude Opus** - Thoughtful but may seek clarification

### For Speed (Flash Mode)
- **Llama 3.2 3B/11B** - Fast, direct answers
- **Gemma 2 9B** - Quick responses for simple queries
- **Qwen 2.5 7B** - Good speed/quality balance

### Model Selection Tips
1. **For explanatory queries** ("Explain X"): Use smaller, faster models in flash mode
2. **For research/analysis**: Use larger models in pro/ultra modes with appropriate skills
3. **For diagram generation**: Ensure skills + tool groups are enabled (model matters less)
4. **To reduce questions**: Use flash mode or prepend "directly" to queries

### Vision Support
Models with `supports_vision: true` in config get the `view_image_tool`:
- GPT-4o, GPT-4.1
- Claude Sonnet 3.5, Claude Opus
- Llama 3.2 Vision
- Qwen 2.5 VL

This enables:
- Analyzing uploaded images
- Viewing generated charts/diagrams
- Image-based reasoning

## Performance Considerations

### Agent Creation Time
- **First run:** ~2-3 seconds (path setup + config generation + tool resolution)
- **Cached:** ~0.5-1 second (profile loading only)
- **Optimization:** Profiles are cached for 60 seconds in Streamlit

### Streaming Response
- **Latency:** Near real-time (50-200ms per chunk)
- **Throughput:** Depends on LLM backend
- **Memory:** ~100-200MB per active agent instance

### Concurrent Users
- **In-process:** Limited by single Streamlit process
- **Scaling:** Deploy multiple Streamlit instances behind load balancer
- **Alternative:** Use LangGraph Server deployment (requires custom integration)

## Future Enhancements

Potential improvements for the integration:

1. **LangGraph Server Support** - Optional remote agent execution
2. **Custom Middleware** - GenAI Blueprint-specific middlewares
3. **Profile Templates** - Shareable agent configurations
4. **Skill Library** - Pre-built skills for common tasks
5. **Multi-Agent Coordination** - Cross-runtime agent collaboration
6. **Persistent Memory** - PostgreSQL/Redis checkpointing
7. **Usage Analytics** - Token tracking and cost monitoring
8. **A/B Testing** - Profile comparison tools

## Contributing

To extend the integration:

1. **Add profiles:** Edit `config/agents/deerflow.yaml`
2. **Create tools:** Add to GenAI Blueprint tool factories
3. **Custom middlewares:** Modify `agent.py` wrapper
4. **UI improvements:** Edit `deer_flow_agent.py` Streamlit page

## References

- **Deer-flow Repository:** https://github.com/bytedance/deer-flow
- **LangGraph Documentation:** https://langchain-ai.github.io/langgraph/
- **GenAI Blueprint Agents:** See [`Agents.md`](../Agents.md)
- **MCP Protocol:** https://modelcontextprotocol.io/

## License

This integration code follows GenAI Blueprint's license. Deer-flow backend is subject to ByteDance's original license.

---

**Last Updated:** February 2026  
**Version:** 1.0.0  
**Maintainer:** GenAI Blueprint Team
