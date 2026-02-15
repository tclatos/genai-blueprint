"""Message rendering utilities for Streamlit applications.

Provides utilities for rendering messages with special content types like
Mermaid diagrams, code blocks, and other rich media.
"""

import re
from typing import Any, Union

import streamlit.components.v1 as components
from streamlit.delta_generator import DeltaGenerator


def render_message_with_mermaid(content: Union[str, list, dict], container: Union[DeltaGenerator, Any]) -> None:
    """Render message content with Mermaid diagram support.

    Detects Mermaid code blocks in the content and renders them as interactive
    diagrams using Mermaid.js via Streamlit's HTML component. Handles both fenced
    (```mermaid...```) and bare Mermaid syntax.

    **Auto-fix feature:** Automatically adds quotes around node labels containing
    special characters (colons, parentheses, mathematical symbols) to prevent
    parsing errors. For example:
        A[Attention (Q·K^T)] → A["Attention (Q·K^T)"]

    Supports the following diagram types:
    - graph, flowchart: Node-link diagrams
    - sequenceDiagram: Interaction sequences
    - classDiagram: Class relationships
    - stateDiagram: State machines
    - erDiagram: Entity-relationship diagrams
    - gantt: Project timelines
    - pie: Pie charts
    - journey: User journey maps
    - gitGraph: Git commit history
    - mindmap: Mind maps
    - timeline: Timeline diagrams
    - sankey: Flow diagrams
    - block: Block diagrams

    Args:
        content: Message content (may contain Mermaid blocks and regular text)
        container: Streamlit container to render in

    Example:
        >>> with st.chat_message("ai"):
        >>>     render_message_with_mermaid(response_text, st)
    """
    # Handle non-string content
    if not isinstance(content, str):
        content = str(content)

    # Pattern to match both fenced and bare Mermaid blocks
    fenced_pattern = r"```mermaid\s*\n(.*?)\n```"
    bare_pattern = r"(?:^|\n)((?:graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|journey|gitGraph|mindmap|timeline|sankey|block).*?)(?=\n\n[A-Z]|\n[A-Z][a-z]+\s+[a-z]|$)"

    # First check for fenced blocks
    fenced_matches = list(re.finditer(fenced_pattern, content, flags=re.DOTALL))

    # If no fenced blocks, look for bare syntax
    if not fenced_matches:
        bare_matches = list(re.finditer(bare_pattern, content, flags=re.DOTALL))
        matches = [(m, m.group(1)) for m in bare_matches]
    else:
        matches = [(m, m.group(1)) for m in fenced_matches]

    if not matches:
        # No Mermaid found, render as plain markdown
        container.markdown(content)
        return

    # Process content: render text and mermaid parts separately
    last_end = 0

    for match, mermaid_code in matches:
        # Render text before this diagram
        if match.start() > last_end:
            text_before = content[last_end : match.start()].strip()
            if text_before:
                container.markdown(text_before)

        # Render the Mermaid diagram using HTML component
        _render_mermaid_diagram(mermaid_code.strip(), container)

        last_end = match.end()

    # Render any remaining text
    if last_end < len(content):
        text_after = content[last_end:].strip()
        if text_after:
            container.markdown(text_after)


def _fix_mermaid_labels(mermaid_code: str) -> str:
    """Fix Mermaid labels by adding quotes around labels with special characters.

    Wraps node labels in quotes if they contain special characters that
    may cause parsing issues: colons, parentheses, mathematical symbols, etc.

    Args:
        mermaid_code: Raw Mermaid diagram code

    Returns:
        Fixed Mermaid code with quoted labels

    Example:
        Input:  A[Linear: Query, Key]
        Output: A["Linear: Query, Key"]
    """
    # Special characters that require quoting
    special_chars = r"[:()\ [\]{}·^*+\-/,<>]"

    # Pattern to match node definitions with labels
    # Matches: NodeId[Label], NodeId(Label), NodeId{Label}, etc.
    # Captures: NodeId, bracket type, label content
    label_pattern = r"\b([A-Za-z0-9_]+)([\[\(\{])([^\]\)\}]+)([\]\)\}])"

    def fix_label(match: re.Match[str]) -> str:
        node_id = match.group(1)
        open_bracket = match.group(2)
        label = match.group(3)
        close_bracket = match.group(4)

        # Check if label already has quotes
        if label.startswith('"') and label.endswith('"'):
            return match.group(0)  # Already quoted

        # Check if label contains special characters
        if re.search(special_chars, label):
            # Add quotes around the label
            return f'{node_id}{open_bracket}"{label}"{close_bracket}'

        return match.group(0)  # No special chars, leave as is

    # Apply the fix to all labels
    fixed_code = re.sub(label_pattern, fix_label, mermaid_code)

    return fixed_code


def _render_mermaid_diagram(mermaid_code: str, container: Union[DeltaGenerator, Any]) -> None:
    """Render a single Mermaid diagram using Mermaid.js via HTML component.

    Args:
        mermaid_code: Mermaid diagram code (without fences)
        container: Streamlit container (unused, relies on ambient context)
    """
    # Fix labels with special characters by adding quotes
    fixed_code = _fix_mermaid_labels(mermaid_code)

    # Generate unique ID for this diagram
    import hashlib

    diagram_id = f"mermaid-{hashlib.md5(fixed_code.encode()).hexdigest()[:8]}"

    # Don't escape the mermaid code - Mermaid.js needs the raw syntax
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
            mermaid.initialize({{ 
                startOnLoad: true,
                theme: 'default',
                securityLevel: 'loose',
                fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
            }});
        </script>
    </head>
    <body style="margin: 0; padding: 20px; display: flex; justify-content: center; align-items: center;">
        <div id="{diagram_id}" class="mermaid-container">
            <pre class="mermaid">
{fixed_code}
            </pre>
        </div>
    </body>
    </html>
    """

    # Render using Streamlit's HTML component
    components.html(html_code, height=400, scrolling=True)
