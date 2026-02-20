"""Streamlit page for Deer-flow Agent demo.

Provides an interactive interface to run Deer-flow agents via HTTP API.
Uses a two-column layout: execution trace (left) and conversation (right)
with real-time token streaming.

Profile configuration comes from ``config/agents/deerflow.yaml``.
The LangGraph server and Gateway are auto-started via DeerFlowServerManager
if not already running.
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from loguru import logger
from streamlit import session_state as sss

from genai_blueprint.webapp.ui_components.config_editor import edit_config_dialog
from genai_blueprint.webapp.ui_components.llm_selector import llm_selector_widget
from genai_blueprint.webapp.ui_components.message_renderer import render_message_with_mermaid
from genai_tk.extra.agents.deer_flow import (
    DeerFlowClient,
    DeerFlowProfile,
    DeerFlowServerManager,
    load_deer_flow_profiles,
    setup_deer_flow_config,
)

load_dotenv()

CONFIG_FILE = "config/agents/deerflow.yaml"
PAGE_TITLE = "🦌 Deer-flow Agent"
HEIGHT = 700

DEER_FLOW_MODES: dict[str, str] = {
    "flash":    "⚡ Flash — fast, no overhead",
    "thinking": "🧠 Thinking — reasoning enabled",
    "pro":      "🎯 Pro — planning + thinking",
    "ultra":    "🚀 Ultra — all features",
}


# ============================================================================
# Session state
# ============================================================================


def _init_session() -> None:
    """Initialise Streamlit session-state keys."""
    defaults: dict[str, Any] = {
        "df_messages": [],       # list[dict]  {role, content}
        "df_thread_id": None,    # str | None
        "df_client": None,       # DeerFlowClient | None
        "df_profile_name": None,
        "df_mode": "pro",
        "df_server_ready": False,
        "df_trace_nodes": [],    # list[str] — nodes seen in last run
        "df_show_help": False,
        "df_show_info": False,
        "df_error": None,
        "df_example_input": None,
    }
    for key, val in defaults.items():
        if key not in sss:
            sss[key] = val


def _clear_chat() -> None:
    """Drop conversation and create a new thread on the next send."""
    sss.df_messages = []
    sss.df_thread_id = None
    sss.df_trace_nodes = []


def _clear_all() -> None:
    """Drop everything including server-ready flag (forces re-init on next send)."""
    _clear_chat()
    sss.df_server_ready = False
    sss.df_client = None
    sss.df_error = None


# ============================================================================
# Profile loading
# ============================================================================


@st.cache_data(ttl=60)
def _load_profiles() -> list[DeerFlowProfile]:
    """Load DeerFlowProfiles from YAML (cached 60 s)."""
    try:
        return load_deer_flow_profiles(CONFIG_FILE)
    except Exception as e:
        logger.error(f"Failed to load Deer-flow profiles: {e}")
        return []


def _profile_by_name(profiles: list[DeerFlowProfile], name: str) -> DeerFlowProfile | None:
    return next((p for p in profiles if p.name == name), None)


# ============================================================================
# Server startup
# ============================================================================


def _ensure_server(profile: DeerFlowProfile) -> DeerFlowClient:
    """Write config, start servers, return a ready DeerFlowClient.

    Skips heavy work if server is already marked ready and client exists.
    """
    if sss.df_server_ready and sss.df_client is not None:
        return sss.df_client

    # Write config.yaml / extensions_config.json before starting
    try:
        setup_deer_flow_config(
            mcp_server_names=profile.mcp_servers,
            enabled_skills=profile.skills,
            skill_directories=profile.skill_directories,
        )
    except Exception as e:
        logger.warning(f"Deer-flow config setup warning: {e}")

    # Start servers if needed
    if profile.auto_start:
        mgr = DeerFlowServerManager(
            deer_flow_path=profile.deer_flow_path,
            langgraph_url=profile.langgraph_url,
            gateway_url=profile.gateway_url,
        )
        asyncio.run(mgr.start())

    client = DeerFlowClient(
        langgraph_url=profile.langgraph_url,
        gateway_url=profile.gateway_url,
    )

    # Apply profile skills via API
    if profile.skills:
        asyncio.run(_apply_skills(client, profile.skills))

    sss.df_client = client
    sss.df_server_ready = True
    return client


async def _apply_skills(client: DeerFlowClient, skills: list[str]) -> None:
    """Enable the profile's skills on the running gateway."""
    for skill in skills:
        try:
            await client.set_skill(skill, enabled=True)
        except Exception as e:
            logger.warning(f"Could not enable skill '{skill}': {e}")


# ============================================================================
# Streaming helper
# ============================================================================

_MODE_FLAGS: dict[str, dict[str, bool]] = {
    "flash":    {"thinking_enabled": False, "is_plan_mode": False},
    "thinking": {"thinking_enabled": True,  "is_plan_mode": False},
    "pro":      {"thinking_enabled": True,  "is_plan_mode": True},
    "ultra":    {"thinking_enabled": True,  "is_plan_mode": True},
}


def _stream_tokens(
    client: DeerFlowClient,
    thread_id: str,
    user_input: str,
    model_name: str | None,
    mode: str,
    trace_placeholder: Any,
) -> str:
    """Run stream_run, update the trace column, return full response text."""
    from genai_tk.extra.agents.deer_flow.client import ErrorEvent, NodeEvent, TokenEvent

    flags = _MODE_FLAGS.get(mode, _MODE_FLAGS["pro"])
    token_parts: list[str] = []
    seen_nodes: list[str] = []

    async def _collect() -> None:
        async for event in client.stream_run(
            thread_id=thread_id,
            user_input=user_input,
            model_name=model_name,
            thinking_enabled=flags["thinking_enabled"],
            is_plan_mode=flags["is_plan_mode"],
        ):
            if isinstance(event, TokenEvent):
                token_parts.append(event.data)
            elif isinstance(event, NodeEvent):
                if event.node not in seen_nodes:
                    seen_nodes.append(event.node)
                    _refresh_trace(trace_placeholder, seen_nodes)
            elif isinstance(event, ErrorEvent):
                logger.error(f"Deer-flow stream error: {event.message}")
                token_parts.append(f"\n\n⚠️ *{event.message}*")

    asyncio.run(_collect())
    sss.df_trace_nodes = seen_nodes
    return "".join(token_parts)


def _refresh_trace(placeholder: Any, nodes: list[str]) -> None:
    """Redraw the trace panel from the node list."""
    with placeholder.container():
        for node in nodes:
            st.markdown(f"→ `{node}`")


# ============================================================================
# Sidebar
# ============================================================================


def _display_sidebar(profiles: list[DeerFlowProfile]) -> tuple[str | None, str]:
    """Render sidebar controls.

    Returns:
        (selected_profile_name, selected_mode)
    """
    with st.sidebar:
        llm_selector_widget(st.sidebar)

        if st.button(":material/edit: Edit Config", help="Edit deerflow.yaml"):
            edit_config_dialog(CONFIG_FILE)

        st.divider()

        if not profiles:
            st.error("No profiles found in config/agents/deerflow.yaml")
            return None, "pro"

        # Profile selector
        names = [p.name for p in profiles]
        cur_idx = names.index(sss.df_profile_name) if sss.df_profile_name in names else 0
        selected_name = st.selectbox("🦌 Profile:", names, index=cur_idx, key="df_profile_sel")

        if sss.df_profile_name and sss.df_profile_name != selected_name:
            _clear_chat()
            sss.df_server_ready = False
            sss.df_client = None

        # Mode selector
        profile = _profile_by_name(profiles, selected_name)
        default_mode = profile.mode if profile else "pro"
        mode_keys = list(DEER_FLOW_MODES.keys())
        mode_idx = mode_keys.index(sss.df_mode) if sss.df_mode in mode_keys else mode_keys.index(default_mode)
        selected_mode = st.selectbox(
            "⚙️ Mode:",
            mode_keys,
            format_func=lambda x: DEER_FLOW_MODES[x],
            index=mode_idx,
            key="df_mode_sel",
        )

        if sss.df_mode != selected_mode:
            sss.df_mode = selected_mode
            sss.df_thread_id = None   # new thread on mode change

        # Profile metadata
        if profile:
            if profile.description:
                st.caption(profile.description)
            if profile.tool_groups:
                st.markdown("**Tools:** " + ", ".join(f"`{g}`" for g in profile.tool_groups))
            if profile.mcp_servers:
                st.markdown("**MCP:** " + ", ".join(f"`{m}`" for m in profile.mcp_servers))
            if profile.skills:
                st.markdown(f"**Skills:** {len(profile.skills)} configured")
            if profile.examples:
                with st.expander("💡 Examples", expanded=False):
                    for ex in profile.examples:
                        if st.button(ex, key=f"ex_{hash(ex)}", use_container_width=True):
                            sss.df_example_input = ex
                            st.rerun()

        st.divider()

        with st.expander("📖 Commands", expanded=False):
            st.markdown("- `/clear` — clear conversation\n- `/info` — show config\n- `/help` — help")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🗑️ Chat", help="Clear chat"):
                _clear_chat()
                st.rerun()
        with c2:
            if st.button("🗑️ All", help="Clear everything"):
                _clear_all()
                st.rerun()

        st.divider()
        st.caption("Powered by [Deer-flow](https://github.com/bytedance/deer-flow)")

    return selected_name, selected_mode


# ============================================================================
# Main
# ============================================================================


def main() -> None:
    """Entry point for the Deer-flow agent Streamlit page."""
    _init_session()

    profiles = _load_profiles()
    st.title(PAGE_TITLE)

    selected_name, selected_mode = _display_sidebar(profiles)
    if selected_name is None:
        st.stop()

    sss.df_profile_name = selected_name
    sss.df_mode = selected_mode

    profile = _profile_by_name(profiles, selected_name)
    if profile is None:
        st.error(f"Profile '{selected_name}' not found.")
        st.stop()

    # Two-column layout
    col_trace, col_chat = st.columns([1, 1], gap="medium")

    with col_trace:
        st.subheader("🔍 Execution Trace")
        trace_container = st.container(height=HEIGHT, border=True)
        with trace_container:
            trace_placeholder = st.empty()
            if sss.df_trace_nodes:
                _refresh_trace(trace_placeholder, sss.df_trace_nodes)
            else:
                trace_placeholder.info("Send a message to see the execution trace")

    with col_chat:
        st.subheader("💬 Conversation")
        chat_container = st.container(height=HEIGHT, border=True)
        with chat_container:
            if not sss.df_messages:
                st.info("Hello! I'm a Deer-flow agent. How can I help you today?")
            for msg in sss.df_messages:
                if msg["role"] == "user":
                    st.chat_message("human").write(msg["content"])
                else:
                    with st.chat_message("ai"):
                        render_message_with_mermaid(msg["content"], st)

    # Errors
    if sss.df_error:
        st.error(sss.df_error)
        if st.button("Clear Error"):
            sss.df_error = None
            st.rerun()

    # Help / info panels
    if sss.df_show_help:
        st.info(
            "**Commands:** `/clear` · `/info` · `/help`\n\n"
            "Use the sidebar to switch profiles and modes.",
            icon="📖",
        )
        sss.df_show_help = False

    if sss.df_show_info:
        with st.container(border=True):
            st.markdown(
                f"**Profile:** `{selected_name}` — **Mode:** `{selected_mode}` {DEER_FLOW_MODES[selected_mode]}"
            )
            if profile.mcp_servers:
                st.markdown(f"**MCP servers:** {', '.join(profile.mcp_servers)}")
            if sss.df_thread_id:
                st.markdown(f"**Thread:** `{sss.df_thread_id}`")
        sss.df_show_info = False

    # Example prefill
    prefill = None
    if sss.df_example_input:
        st.info(f"💡 {sss.df_example_input}")
        prefill = sss.df_example_input
        sss.df_example_input = None

    # Chat input
    user_input = st.chat_input("Type a message or a command (/help, /info, /clear)…", key="df_input")
    if prefill and not user_input:
        user_input = prefill

    if not user_input or not user_input.strip():
        return

    user_input = user_input.strip()

    # Built-in commands
    if user_input.startswith("/"):
        cmd = user_input.lower()
        if cmd in ("/clear", "/reset"):
            _clear_chat()
        elif cmd == "/help":
            sss.df_show_help = True
        elif cmd == "/info":
            sss.df_show_info = True
        else:
            st.warning(f"Unknown command `{user_input}`. Try `/help`.")
        st.rerun()
        return

    # Append user message
    sss.df_messages.append({"role": "user", "content": user_input})
    with chat_container:
        st.chat_message("human").write(user_input)

    # Ensure servers running
    with st.spinner("🦌 Starting Deer-flow servers…"):
        try:
            client = _ensure_server(profile)
        except Exception as e:
            sss.df_error = f"Failed to start Deer-flow: {e}"
            logger.error(f"{sss.df_error}\n{traceback.format_exc()}")
            st.rerun()
            return

    # Create thread if needed
    if not sss.df_thread_id:
        try:
            sss.df_thread_id = asyncio.run(client.create_thread())
        except Exception as e:
            sss.df_error = f"Failed to create thread: {e}"
            st.rerun()
            return

    # Model override from LLM selector
    from genai_tk.utils.config_mngr import global_config
    model_name: str | None = None
    try:
        model_name = global_config().get_str("llm.models.default") or None
    except Exception:
        pass

    # Stream response
    with chat_container:
        with st.chat_message("ai"):
            response_placeholder = st.empty()
            accumulated = ""
            with st.status("🦌 Thinking…", expanded=False) as status_widget:
                try:
                    accumulated = _stream_tokens(
                        client=client,
                        thread_id=sss.df_thread_id,
                        user_input=user_input,
                        model_name=model_name,
                        mode=selected_mode,
                        trace_placeholder=trace_placeholder,
                    )
                    status_widget.update(label="✅ Done", state="complete", expanded=False)
                except Exception as e:
                    sss.df_error = f"Agent error: {e}"
                    logger.error(f"{sss.df_error}\n{traceback.format_exc()}")
                    status_widget.update(label="❌ Error", state="error")
                    st.rerun()
                    return

            if accumulated:
                response_placeholder.empty()
                render_message_with_mermaid(accumulated, st)
            else:
                response_placeholder.warning("No response received.")

    sss.df_messages.append({"role": "assistant", "content": accumulated})
    st.rerun()


# ============================================================================
# Entry point
# ============================================================================

try:
    _ = st.session_state  # verify Streamlit context
    main()
except (AttributeError, RuntimeError):
    pass  # not running in Streamlit (e.g. imported)
