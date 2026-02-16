"""Deer-flow integration for GenAI Blueprint.

This package provides a bridge between GenAI Blueprint and ByteDance's Deer-flow
agent system, enabling Deer-flow's advanced agent capabilities (subagents, sandboxing,
memory, skills) within the GenAI Blueprint Streamlit interface.

Architecture:
    - config_bridge: Generates Deer-flow config from GenAI Blueprint YAML configs
    - agent: Wrapper to create and run Deer-flow agents with GenAI Blueprint tools
    - The Streamlit page lives in webapp/pages/demos/deer_flow_agent.py

Setup:
    1. make deer-flow-install   (clones deer-flow + installs deps)
    2. Or manually: git clone https://github.com/bytedance/deer-flow ext/deer-flow
       then: uv sync --group deerflow
"""

from genai_bp.deer_flow._path_setup import get_deer_flow_backend_path, setup_deer_flow_path

__all__ = ["get_deer_flow_backend_path", "setup_deer_flow_path"]
