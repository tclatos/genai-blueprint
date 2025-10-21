# Dependency Management Strategy

## Overview

This document explains how dependencies are managed between `genai-tk` (the core toolkit) and `genai-blueprint` (the application framework).

## Dependency Organization

### **genai-tk (Core Toolkit)**

#### **Main Dependencies** (Always Installed)
Located in `[project.dependencies]` - these are **transitive** and automatically installed when genai-tk is imported:

- **Core Framework**: pydantic, loguru, typer, omegaconf, rich, etc.
- **AI/ML Core** (moved from ai-core group):
  - langchain, langchain-core, langchain-community
  - langgraph, langserve, deepagents
  - Provider integrations: openai, ollama, deepseek, mistralai, groq
  - litellm, smolagents, mcp
- **Extra Features** (moved from extra group):
  - chromadb, langchain-chroma
  - gpt-researcher, tavily, duckduckgo-search
  - markitdown, markpickle, openpyxl
- **Knowledge Graphs** (moved from kg group):
  - baml-cli, langchain-kuzu, kuzu
- **NLP & Search** (moved from nlp group):
  - spacy, spacy models (en_core_web_sm, en_core_web_lg)
  - rank-bm25, bm25s, abbreviations

#### **Optional Dependencies** (Dependency Groups)
Located in `[dependency-groups]` - these are **NOT transitive** and must be explicitly requested:

- **browser-control**: playwright, browser-use-sdk
- **transformers**: accelerate, langchain-huggingface, sentence-transformers (⚠️ ~5GB)
- **autogen**: autogen-agentchat, autogen-ext
- **postgres**: langchain-postgres, psycopg
- **dev**: ruff, pytest, ipykernel, ipywidgets

### **genai-blueprint (Application Framework)**

#### **Main Dependencies**
- genai-tk (pulls all its main dependencies transitively)
- Application-specific: fastapi, modal, baml-py
- Framework utilities: pydantic, typer, omegaconf, rich

#### **Optional Dependencies** (Dependency Groups)
These mirror genai-tk's optional groups and add application-specific dependencies:

- **browser_control**: Mirrors genai-tk's browser-control + helium
- **transformers**: Mirrors genai-tk's transformers group
- **autogen**: Mirrors genai-tk's autogen group
- **ui**: Streamlit and web UI components
- **demos**: Demo-specific packages (plotly, presidio, matplotlib, etc.)
- **extra**: Additional AI capabilities (gpt-researcher, tavily)
- **dev**: Development tools (ruff, pytest, ipykernel)

## Migration Summary

### **What Changed**

**Option 3** - Moved to main dependencies (now transitive):
- ✅ `ai-core` → main dependencies in genai-tk
- ✅ `extra` → main dependencies in genai-tk
- ✅ `kg` → main dependencies in genai-tk
- ✅ `nlp` → main dependencies in genai-tk

**Option 2** - Kept as optional dependency groups (duplicated in both projects):
- ✅ `browser-control` → optional in both projects
- ✅ `transformers` → optional in both projects  
- ✅ `autogen` → optional in both projects

### **Rationale**

**Main Dependencies (Option 3):**
- These are **required for core CLI functionality** to work
- Moving them to main dependencies makes them **transitive**
- genai-blueprint automatically gets them when importing genai-tk
- No manual synchronization needed

**Optional Groups (Option 2):**
- These are **truly optional** features not always needed
- Large dependencies (transformers ~5GB)
- Specialized use cases (browser automation, multi-agent systems)
- Each project can independently choose to include them

## Usage

### **Installing genai-blueprint**

**Basic installation** (gets all core features):
```bash
cd genai-blueprint
uv sync
```

**With optional groups**:
```bash
# Add browser automation
uv sync --group browser_control

# Add transformers (large!)
uv sync --group transformers

# Add AutoGen multi-agent
uv sync --group autogen

# Add multiple groups
uv sync --group browser_control --group autogen
```

### **Installing genai-tk standalone**

**Basic installation**:
```bash
cd genai-tk
uv sync
```

**With optional groups**:
```bash
uv sync --group browser-control --group postgres
```

## Benefits

### ✅ **Clean Separation**
- Core functionality is always available
- Optional features are clearly identified
- No hidden dependencies

### ✅ **Transitive Dependencies**
- Main dependencies propagate through Git imports
- No need to duplicate core dependencies
- Automatic version synchronization

### ✅ **Flexibility**
- Users can choose which optional features to install
- Reduced installation size for minimal setups
- Clear distinction between required and optional

### ✅ **Maintainability**
- Single source of truth for core dependencies (genai-tk)
- Explicit duplication only for optional groups
- Easy to identify what needs updating

## Technical Details

### **Why Dependency Groups Don't Work with Git Imports**

Dependency groups (`[dependency-groups]`) are:
- Defined in PEP 735
- Local to the project
- **NOT transitive** - don't propagate to consumers
- Only resolved when explicitly requested with `--group`

When you import a package via Git:
```toml
"genai_tk @ git+https://github.com/user/genai-tk@main"
```

Only the `[project.dependencies]` are installed, not the `[dependency-groups]`.

### **Solution: Use Main Dependencies**

For truly required dependencies, put them in `[project.dependencies]`:
```toml
[project]
dependencies = [
    "langchain>=1.0",
    "litellm>=1.74",
    # ... these are transitive
]
```

### **Alternative: Optional Dependencies (Extras)**

For optional but transitive dependencies, use `[project.optional-dependencies]`:
```toml
[project.optional-dependencies]
browser = [
    "playwright>=1.51.0",
]
```

Then import with:
```toml
"genai_tk[browser] @ git+https://github.com/user/genai-tk@main"
```

⚠️ We didn't use this approach because our optional dependencies are truly optional and not needed by most users.

## Troubleshooting

### **Missing Dependencies**

**Problem**: Import errors when using genai-tk features

**Solution**: Check if you need an optional group:
```bash
uv sync --group browser_control --group transformers
```

### **Large Installation Size**

**Problem**: Installation is too large

**Solution**: Don't install optional groups you don't need:
```bash
# Minimal installation (no optional groups)
uv sync

# Just what you need
uv sync --group browser_control
```

### **Dependency Version Conflicts**

**Problem**: Version conflicts between projects

**Solution**: Update genai-tk to latest:
```bash
cd genai-blueprint
uv cache clean genai-tk
uv sync --upgrade-package genai-tk
```

## Reference

- [PEP 735 - Dependency Groups](https://peps.python.org/pep-0735/)
- [UV Documentation - Dependency Groups](https://docs.astral.sh/uv/)
- genai-tk pyproject.toml
- genai-blueprint pyproject.toml
