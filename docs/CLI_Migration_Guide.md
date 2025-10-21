# CLI Migration Guide

## Overview

The GenAI Blueprint CLI has been restructured to use a more organized command/subcommand pattern, following the same structure as `genai-tk`. This guide shows the mapping from old commands to new ones.

## ✅ New Command Structure

### **Command Groups:**

| **Group** | **Description** | **Source** |
|-----------|----------------|-----------|
| `core` | Core AI model operations | genai-tk |
| `info` | Information and listing commands | genai-tk |
| `tools` | Utilities and extra tools | genai-tk |
| `agents` | Agent-based commands | genai-tk |
| `rag` | Vector store RAG operations | genai-tk |
| `kg` | Knowledge Graph operations | genai-blueprint |
| `structured` | Document processing & generation | genai-blueprint |

## 🔄 Command Migration Map

### **Knowledge Graph Commands (kg group)**
| **Old Command** | **New Command** | **Description** |
|-----------------|----------------|----------------|
| `kg-add` | `kg add` | Add data to knowledge graph |
| `kg-delete` | `kg delete` | Delete knowledge graph database |
| `kg-query` | `kg query` | Execute Cypher queries |
| `kg-info` | `kg info` | Display database information |
| `kg-export-html` | `kg export-html` | Export HTML visualization |
| `ekg-agent-shell` | `kg agent` | Interactive KG agent |

### **Document Processing Commands (structured group)**
| **Old Command** | **New Command** | **Description** |
|-----------------|----------------|----------------|
| `structured_extract` | `structured extract` | Extract structured data from documents |
| `structured-extract-baml` | `structured extract-baml` | Extract using BAML |
| `rainbow_generate_fake` | `structured gen-fake` | Generate fake data |

### **Core AI Commands (core group)**
| **Old Command** | **New Command** | **Description** |
|-----------------|----------------|----------------|
| `llm` | `core llm` | Direct LLM interaction |
| `run` | `core run` | Run registered chains |
| `embedd` | `core embedd` | Generate embeddings |
| `similarity` | `core similarity` | Calculate semantic similarity |

### **Information Commands (info group)**
| **Old Command** | **New Command** | **Description** |
|-----------------|----------------|----------------|
| `config-info` | `info config` | Show configuration |
| `list-models` | `info models` | List available models |
| `list-mcp-tools` | `info mcp-tools` | List MCP server tools |
| `list-mcp-prompts` | `info mcp-prompts` | List MCP prompts |

### **Agent Commands (agents group)**
| **Old Command** | **New Command** | **Description** |
|-----------------|----------------|----------------|
| `react-agent` | `agents react` | ReAct agent with tools |
| `mcp-agent` | `agents mcp` | MCP-enabled agent |
| `smolagents` | `agents smolagents` | CodeAct agent |
| `deep-agent` | `agents deep` | Deep reasoning agents |

### **Utility Commands (tools group)**
| **Old Command** | **New Command** | **Description** |
|-----------------|----------------|----------------|
| `markdownize` | `tools markdownize` | Convert documents to markdown |
| `gpt-researcher` | `tools gpt-researcher` | Run GPT Researcher |

## 📝 Usage Examples

### **Basic LLM Operations**
```bash
# Old way
uv run cli llm --input "Hello world"
uv run cli run joke --input "bears"

# New way ✅
uv run cli core llm "Hello world"
uv run cli core run joke --input "bears"
```

### **Knowledge Graph Operations**
```bash
# Old way
uv run cli kg-add --key project-alpha
uv run cli ekg-agent-shell --input "Find Python projects"

# New way ✅
uv run cli kg add --key project-alpha
uv run cli kg agent --input "Find Python projects"
```

### **Document Processing**
```bash
# Old way
uv run cli structured_extract "*.md" --schema "project"
uv run cli structured-extract-baml "*.md" --class ReviewedOpportunity

# New way ✅
uv run cli structured extract "*.md" --schema "project"
uv run cli structured extract-baml "*.md" --class ReviewedOpportunity
```

### **Agent Operations**
```bash
# Old way
uv run cli deep-agent research --input "AI developments"
uv run cli mcp-agent --server filesystem --shell

# New way ✅
uv run cli agents deep research --input "AI developments"
uv run cli agents mcp --server filesystem --chat
```

### **Information & Configuration**
```bash
# Old way
uv run cli config-info
uv run cli list-models

# New way ✅
uv run cli info config
uv run cli info models
```

## 🛠 Quick Migration Tips

### **Find Your Command**
```bash
# List all available commands
uv run cli --help

# List commands in specific group
uv run cli kg --help
uv run cli structured --help
uv run cli agents --help
```

### **Common Patterns**
1. **Single commands** → Moved to appropriate group:
   - `llm` → `core llm`
   - `config-info` → `info config`

2. **Hyphenated commands** → Became subcommands:
   - `kg-add` → `kg add`
   - `deep-agent` → `agents deep`

3. **Related commands** → Grouped together:
   - All KG operations under `kg`
   - All document processing under `structured`
   - All agent commands under `agents`

### **Parameter Changes**
Most parameters remain the same, but note these changes:
- `--llm-id` → `--llm` (shorter form)
- `--shell` → `--chat` (for interactive mode)

## 🔧 Troubleshooting

### **Command Not Found**
```bash
# If you get: command not found
uv run cli old-command

# Try: Check the migration table above, then:
uv run cli [group] [subcommand]
```

### **Help & Discovery**
```bash
# General help
uv run cli --help

# Group-specific help
uv run cli [group] --help

# Command-specific help
uv run cli [group] [subcommand] --help
```

## 📚 Related Documentation

- **Main README**: [README.md](../README.md) - Updated examples
- **Deep Agent Guide**: [deep_agent_cli_examples.md](deep_agent_cli_examples.md) - Agent-specific examples
- **Configuration**: [../config/](../config/) - CLI command configuration

## ✅ Migration Checklist

- [ ] Update any scripts using old CLI commands
- [ ] Update documentation referencing old commands
- [ ] Test new command structure in your workflows
- [ ] Update any automation or CI/CD using CLI commands
- [ ] Verify all functionality works with new structure

---

**Need Help?** Run `uv run cli --help` to explore the new command structure, or check the specific group help with `uv run cli [group] --help`.