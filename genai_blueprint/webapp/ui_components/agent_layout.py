"""Shared UI layout constants and helpers used across agent demo pages.

Each agent page follows this structure:

- **Sidebar**: LLM selector, Edit Config button, demo / profile selector,
  demo metadata (description, tools, MCP servers), example list (read-only,
  copy-paste), and page-specific widgets (mode selector, clear buttons, …).
- **Main area**: page title, then a two-panel layout — execution trace on the
  left, chat / results on the right.

Usage
-----
1. Call :func:`render_agent_sidebar` to render the LLM selector + Edit Config
   block at the top of the sidebar.
2. Open a ``with st.sidebar:`` block and call :func:`render_sidebar_demo_section`
   to add the demo selector, metadata, and example list.  It returns the
   selected demo object.
3. Add any page-specific sidebar controls (mode selector, clear buttons, …)
   in the same block.
"""

from typing import Any

import streamlit as st

from genai_blueprint.webapp.ui_components.config_editor import edit_config_dialog
from genai_blueprint.webapp.ui_components.llm_selector import llm_selector_widget

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

PANEL_HEIGHT: int = 640  # px — consistent height for trace / chat containers

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def render_agent_sidebar(config_file: str) -> None:
    """Render the standard sidebar block: LLM selector + Edit Config button.

    Call once near the top of the page's ``main()`` function.  Page-specific
    controls (clear buttons, mode selector …) can be added afterwards with
    additional ``with st.sidebar:`` blocks.

    Args:
        config_file: Path to the YAML config file opened by the Edit Config dialog.
    """
    with st.sidebar:
        llm_selector_widget(st.sidebar)
        st.divider()
        if st.button(":material/edit: Edit Config", help="Edit YAML configuration"):
            edit_config_dialog(config_file)


# ---------------------------------------------------------------------------
# Demo / profile selector
# ---------------------------------------------------------------------------


def render_sidebar_demo_section(
    demos: list[Any],
    *,
    current_name: str | None = None,
    info_fn: Any = None,
) -> Any | None:
    """Render the demo / profile block inside the sidebar.

    Displays a selectbox to choose the active demo, optional metadata rendered
    by *info_fn* (description, tools, MCP servers, …), and an expandable example
    list where each item is a copyable code block.

    Must be called inside a ``with st.sidebar:`` context.

    Args:
        demos: Demo / profile objects.  Must expose ``.name`` and optionally
            ``.examples`` (``list[str]``).
        current_name: Currently active demo name — keeps the selectbox stable
            across reruns.
        info_fn: Optional ``fn(demo) -> None`` rendered below the selectbox.
            Use it to show description, tools, MCP servers, etc.

    Returns:
        The selected demo object, or ``None`` when *demos* is empty.
    """
    if not demos:
        st.warning("No demos configured.")
        return None

    names = [d.name for d in demos]
    default_idx = names.index(current_name) if current_name in names else 0

    selected_name = st.selectbox(
        "Demo",
        options=names,
        index=default_idx,
        key="sidebar_demo_sel",
        label_visibility="collapsed",
    )
    selected = next((d for d in demos if d.name == selected_name), None)

    if selected is None:
        return None

    if info_fn is not None:
        info_fn(selected)

    examples: list[str] = getattr(selected, "examples", None) or []
    if examples:
        with st.expander("💡 Examples", expanded=False):
            for ex in examples:
                st.code(ex, language="")

    return selected
