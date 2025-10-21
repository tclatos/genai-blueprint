# Deep Agent CLI - Usage Examples

## Overview

The Deep Agent CLI now features enhanced markdown rendering for beautiful, readable output in the terminal. All agent responses are automatically formatted with proper markdown structure and rendered using Rich's markdown capabilities.

## Features

### 🎨 Beautiful Markdown Rendering
- Headers are displayed with proper formatting
- Lists and bullet points are clearly structured
- Tables are rendered with borders
- Code blocks are highlighted
- Links and sources are properly formatted

### 🚀 Visual Enhancements
- User query is displayed clearly before processing
- Progress indicators with agent-specific emojis
- Colored borders and separators
- Status messages for each stage

## Command Examples

### Research Agent
```bash
# Basic research query
uv run cli agents deep research --input "Latest AI developments" --llm gpt_41_openrouter

# Research with specific focus
uv run cli agents deep research --input "What are the environmental impacts of lithium mining?" --llm claude_sonnet_openrouter

# Save results to file
uv run cli agents deep research --input "Quantum computing breakthroughs 2024" --output-dir ./research --llm gpt_41_openrouter
```

### Coding Agent
```bash
# Generate code
uv run cli agents deep coding --input "Write a Python async web scraper" --llm gpt_41_openrouter

# Debug code
uv run cli agents deep coding --input "Debug this function" --files buggy_code.py --llm gpt_41_openrouter

# Refactor code
uv run cli agents deep coding --input "Refactor for better performance" --files app.py --llm gpt_41_openrouter
```

### Analysis Agent
```bash
# Analyze data
uv run cli agents deep analysis --input "Analyze sales trends" --files sales_data.csv --llm gpt_41_openrouter

# Generate insights
uv run cli agents deep analysis --input "Find patterns in user behavior" --files logs.json --llm gpt_41_openrouter
```

### Custom Agent
```bash
# Custom instructions
uv run cli agents deep custom --input "Plan a project timeline" --instructions "You are a project manager. Create detailed timelines with milestones." --llm gpt_41_openrouter
```

## Output Format

The CLI now displays responses with:

```
👤 User Query:
[Your question displayed here]

🔍 Research agent is thinking...

═══════════════════════════════════════════════════════════════
                        AGENT RESPONSE                         
═══════════════════════════════════════════════════════════════

[Beautifully formatted markdown response]

═══════════════════════════════════════════════════════════════
```

## Agent Emojis

Each agent type has its own emoji indicator:
- 🔍 Research Agent
- 💻 Coding Agent
- 📊 Analysis Agent
- ⚙️ Custom Agent
- 🤖 Default/Unknown Agent

## Markdown Features Supported

The agents now output responses with:

- **Headers**: `#`, `##`, `###` for structure
- **Emphasis**: `**bold**`, `*italic*`, `***bold italic***`
- **Lists**: Bullet points and numbered lists
- **Tables**: Properly formatted data tables
- **Code blocks**: With syntax highlighting
- **Quotes**: Block quotes for important notes
- **Links**: Clickable source links
- **Dividers**: Horizontal rules for sections

## Tips for Best Results

1. **Be specific**: Provide clear, detailed queries for better responses
2. **Use appropriate models**: Choose models that support function calling
3. **Include context**: Use `--files` to provide relevant documents
4. **Save outputs**: Use `--output-dir` to save results for later reference
5. **Stream mode**: Add `--stream` for real-time response streaming

## Example Output

When you run a research query, you'll see:

```markdown
# Topic Title

## Overview
A brief summary of the topic with **key points** highlighted.

## Key Findings
- Finding 1 with supporting details
- Finding 2 with evidence
- Finding 3 with implications

## Detailed Analysis

### Section 1
Comprehensive information organized clearly...

### Section 2
Additional insights and data...

## Sources
- [Source 1](https://example.com)
- [Source 2](https://example.com)
```

All rendered beautifully in your terminal with proper formatting, colors, and structure!
