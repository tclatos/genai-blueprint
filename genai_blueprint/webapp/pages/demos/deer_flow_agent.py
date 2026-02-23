"""Streamlit Deer-flow demo page backed by GenAI Toolkit's Deer-flow runtime logic.

This page reuses the same core startup and mode logic as ``cli deerflow --chat``
to keep Streamlit and CLI behavior aligned.
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from genai_tk.extra.agents.deer_flow import DeerFlowClient, DeerFlowProfile, load_deer_flow_profiles
from genai_tk.extra.agents.deer_flow.cli_commands import _NODE_LABELS, _mode_to_configurable, _prepare_profile
from genai_tk.extra.agents.deer_flow.client import ErrorEvent, NodeEvent, TokenEvent, ToolCallEvent, ToolResultEvent
from loguru import logger
from streamlit import session_state as sss

from genai_blueprint.webapp.ui_components.config_editor import edit_config_dialog
from genai_blueprint.webapp.ui_components.llm_selector import llm_selector_widget
from genai_blueprint.webapp.ui_components.message_renderer import render_message_with_mermaid

load_dotenv()

CONFIG_FILE = "config/agents/deerflow.yaml"
PAGE_TITLE = "🦌 Deer-flow Agent"
HEIGHT = 720
_MAX_TRACE_LINES = 200

MODE_LABELS: dict[str, str] = {
    "flash": "⚡ Flash — fast answers",
    "thinking": "💡 Thinking — deeper reasoning",
    "pro": "🎓 Pro — planning + reasoning",
    "ultra": "🚀 Ultra — maximum capability",
}


def _init_session() -> None:
    """Initialise Streamlit session state for Deer-flow UI."""
    defaults: dict[str, Any] = {
        "df_messages": [],
        "df_thread_id": None,
        "df_client": None,
        "df_profile_name": None,
        "df_active_profile": None,
        "df_mode": "pro",
        "df_model_name": None,
        "df_runtime_signature": None,
        "df_server_ready": False,
        "df_trace_events": [],
        "df_trace_verbose": False,
        "df_show_help": False,
        "df_show_info": False,
        "df_error": None,
        "df_example_input": None,
    }
    for key, val in defaults.items():
        if key not in sss:
            sss[key] = val


def _clear_chat() -> None:
    """Clear conversation thread and transient run trace."""
    sss.df_messages = []
    sss.df_thread_id = None
    sss.df_trace_events = []


def _clear_runtime() -> None:
    """Clear prepared runtime so next message re-runs toolkit setup."""
    sss.df_server_ready = False
    sss.df_client = None
    sss.df_active_profile = None
    sss.df_model_name = None
    sss.df_runtime_signature = None


def _clear_all() -> None:
    """Clear chat, runtime and current error."""
    _clear_chat()
    _clear_runtime()
    sss.df_error = None


@st.cache_data(ttl=60)
def _load_profiles() -> list[DeerFlowProfile]:
    """Load Deer-flow profiles from YAML."""
    try:
        return load_deer_flow_profiles(CONFIG_FILE)
    except Exception as exc:
        logger.error(f"Failed to load Deer-flow profiles: {exc}")
        return []


def _profile_by_name(profiles: list[DeerFlowProfile], name: str) -> DeerFlowProfile | None:
    """Return profile matching ``name``."""
    return next((p for p in profiles if p.name == name), None)


def _selected_llm_override() -> str | None:
    """Return active LLM selector value as toolkit llm identifier, if available."""
    from genai_tk.utils.config_mngr import global_config

    try:
        return global_config().get_str("llm.models.default") or None
    except Exception:
        return None


def _runtime_signature(profile_name: str, llm_override: str | None) -> str:
    """Build a cache signature for prepared deer-flow runtime."""
    return f"{profile_name}|{llm_override or ''}"


def _ensure_runtime(profile_name: str) -> tuple[DeerFlowClient, DeerFlowProfile, str | None]:
    """Prepare runtime with toolkit's chat setup logic and return ready client/profile/model."""
    llm_override = _selected_llm_override()
    signature = _runtime_signature(profile_name, llm_override)

    if sss.df_server_ready and sss.df_client and sss.df_runtime_signature == signature and sss.df_active_profile:
        return sss.df_client, sss.df_active_profile, sss.df_model_name

    prepared_profile, model_name = asyncio.run(
        _prepare_profile(
            profile_name=profile_name,
            llm_override=llm_override,
            extra_mcp=[],
            mode_override=None,
            verbose=False,
        )
    )
    client = DeerFlowClient(
        langgraph_url=prepared_profile.langgraph_url,
        gateway_url=prepared_profile.gateway_url,
    )

    sss.df_server_ready = True
    sss.df_client = client
    sss.df_active_profile = prepared_profile
    sss.df_model_name = model_name
    sss.df_runtime_signature = signature
    return client, prepared_profile, model_name


def _refresh_trace(trace_placeholder: Any, events: list[str]) -> None:
    """Render execution timeline in the trace panel."""
    with trace_placeholder.container():
        if not events:
            st.info("Send a message to view execution trace.")
            return
        for line in events[-40:]:
            st.markdown(line)


def _push_trace(trace_placeholder: Any, line: str) -> None:
    """Append one line to trace timeline and refresh panel."""
    sss.df_trace_events.append(line)
    if len(sss.df_trace_events) > _MAX_TRACE_LINES:
        sss.df_trace_events = sss.df_trace_events[-_MAX_TRACE_LINES:]
    _refresh_trace(trace_placeholder, sss.df_trace_events)


def _stream_response(
    *,
    client: DeerFlowClient,
    thread_id: str,
    user_input: str,
    model_name: str | None,
    mode: str,
    trace_placeholder: Any,
    response_placeholder: Any,
) -> str:
    """Stream one turn, update trace and incremental text, then return full response."""
    flags = _mode_to_configurable(mode)
    token_parts: list[str] = []
    current_node = ""

    async def _collect() -> None:
        nonlocal current_node
        async for event in client.stream_run(
            thread_id=thread_id,
            user_input=user_input,
            model_name=model_name,
            thinking_enabled=flags["thinking_enabled"],
            is_plan_mode=flags["is_plan_mode"],
        ):
            if isinstance(event, TokenEvent):
                token_parts.append(event.data)
                response_placeholder.markdown("".join(token_parts) + "▌")
            elif isinstance(event, NodeEvent):
                if event.node == current_node:
                    continue
                current_node = event.node
                label = _NODE_LABELS.get(event.node)
                if label:
                    _push_trace(trace_placeholder, f"→ **{label}**")
                elif sss.df_trace_verbose:
                    _push_trace(trace_placeholder, f"→ `{event.node}`")
            elif isinstance(event, ToolCallEvent):
                if event.tool_name:
                    args_preview = str(event.args)[:120].replace("\n", " ") if event.args else ""
                    _push_trace(
                        trace_placeholder,
                        f"⚙️ `{event.tool_name}` <span style='opacity:.75'>{args_preview}</span>",
                    )
            elif isinstance(event, ToolResultEvent):
                if sss.df_trace_verbose and event.tool_name:
                    result_preview = (event.content or "")[:180].replace("\n", " ")
                    _push_trace(
                        trace_placeholder,
                        f"✅ `{event.tool_name}` <span style='opacity:.75'>{result_preview}</span>",
                    )
            elif isinstance(event, ErrorEvent):
                _push_trace(trace_placeholder, f"❌ **Error:** {event.message}")
                token_parts.append(f"\n\n⚠️ *{event.message}*")

    asyncio.run(_collect())
    return "".join(token_parts)


def _display_sidebar(profiles: list[DeerFlowProfile]) -> tuple[str | None, str]:
    """Render sidebar controls and return selected profile/mode."""
    with st.sidebar:
        llm_selector_widget(st.sidebar)

        if st.button(":material/edit: Edit Config", help="Edit deerflow profile config"):
            edit_config_dialog(CONFIG_FILE)

        st.divider()

        if not profiles:
            st.error("No profiles found in config/agents/deerflow.yaml")
            return None, "pro"

        names = [p.name for p in profiles]
        cur_idx = names.index(sss.df_profile_name) if sss.df_profile_name in names else 0
        selected_name = st.selectbox("🦌 Profile", names, index=cur_idx, key="df_profile_sel")

        if sss.df_profile_name and sss.df_profile_name != selected_name:
            _clear_all()

        profile = _profile_by_name(profiles, selected_name)
        mode_keys = list(MODE_LABELS.keys())
        default_mode = profile.mode if profile else "pro"
        mode_idx = mode_keys.index(sss.df_mode) if sss.df_mode in mode_keys else mode_keys.index(default_mode)
        selected_mode = st.selectbox(
            "⚙️ Mode",
            mode_keys,
            format_func=lambda x: MODE_LABELS[x],
            index=mode_idx,
            key="df_mode_sel",
        )
        sss.df_trace_verbose = st.toggle(
            "Show detailed trace",
            value=sss.df_trace_verbose,
            help="Show tool result previews and unlabelled node names.",
        )

        if profile:
            if profile.description:
                st.caption(profile.description)
            if profile.tool_groups:
                st.markdown("**Tools:** " + ", ".join(f"`{g}`" for g in profile.tool_groups))
            if profile.mcp_servers:
                st.markdown("**MCP:** " + ", ".join(f"`{m}`" for m in profile.mcp_servers))
            if profile.skills or profile.skill_directories:
                st.markdown("**Skills:** enabled from profile")
            if profile.examples:
                with st.expander("💡 Examples", expanded=False):
                    for i, ex in enumerate(profile.examples):
                        if st.button(ex, key=f"df_ex_{selected_name}_{i}", use_container_width=True):
                            sss.df_example_input = ex
                            st.rerun()

        st.divider()
        with st.expander("📖 Commands", expanded=False):
            st.markdown(
                "- `/help` — show help\n"
                "- `/info` — show current runtime/profile info\n"
                "- `/mode flash|thinking|pro|ultra` — switch mode\n"
                "- `/trace` — toggle detailed trace\n"
                "- `/clear` — start new conversation\n"
                "- `/quit` — clear chat (web equivalent)"
            )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🗑️ Chat", help="Clear conversation"):
                _clear_chat()
                st.rerun()
        with c2:
            if st.button("🗑️ All", help="Clear runtime + chat"):
                _clear_all()
                st.rerun()

        st.divider()
        st.caption("Native UI available via `cli deerflow --web`")

    return selected_name, selected_mode


def main() -> None:
    """Render and run Deer-flow Streamlit page."""
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

    col_trace, col_chat = st.columns([1, 1], gap="medium")

    with col_trace:
        st.subheader("🔍 Execution Trace")
        trace_container = st.container(height=HEIGHT, border=True)
        with trace_container:
            trace_placeholder = st.empty()
            _refresh_trace(trace_placeholder, sss.df_trace_events)

    with col_chat:
        st.subheader("💬 Conversation")
        chat_container = st.container(height=HEIGHT, border=True)
        with chat_container:
            if not sss.df_messages:
                st.info("Hello! I’m Deer-flow. Ask anything, or use an example from the sidebar.")
            for msg in sss.df_messages:
                if msg["role"] == "user":
                    st.chat_message("human").write(msg["content"])
                else:
                    with st.chat_message("ai"):
                        render_message_with_mermaid(msg["content"], st)

    if sss.df_error:
        st.error(sss.df_error)
        if st.button("Clear Error"):
            sss.df_error = None
            st.rerun()

    if sss.df_show_help:
        st.info(
            "**Commands:** `/help` · `/info` · `/mode <...>` · `/trace` · `/clear`\n\n"
            "Use the sidebar for profile, model, and examples.",
            icon="📖",
        )
        sss.df_show_help = False

    if sss.df_show_info:
        active_profile = sss.df_active_profile if sss.df_active_profile else profile
        with st.container(border=True):
            st.markdown(f"**Profile:** `{selected_name}`  |  **Mode:** `{selected_mode}`")
            st.markdown(f"**Model:** `{sss.df_model_name or '(server default)'}`")
            if active_profile.mcp_servers:
                st.markdown("**MCP:** " + ", ".join(active_profile.mcp_servers))
            if sss.df_thread_id:
                st.markdown(f"**Thread:** `{sss.df_thread_id}`")
            st.caption(f"LangGraph: {active_profile.langgraph_url} · Gateway: {active_profile.gateway_url}")
        sss.df_show_info = False

    prefill = None
    if sss.df_example_input:
        prefill = sss.df_example_input
        st.info(f"💡 {prefill}")
        sss.df_example_input = None

    user_input = st.chat_input("Type message or /help", key="df_input")
    if prefill and not user_input:
        user_input = prefill
    if not user_input or not user_input.strip():
        return

    user_input = user_input.strip()

    if user_input.startswith("/"):
        cmd = user_input.lower()
        if cmd in ("/clear", "/reset", "/quit", "/exit", "/q"):
            _clear_chat()
        elif cmd == "/help":
            sss.df_show_help = True
        elif cmd == "/info":
            sss.df_show_info = True
        elif cmd == "/trace":
            sss.df_trace_verbose = not sss.df_trace_verbose
            st.info(f"Detailed trace: {'ON' if sss.df_trace_verbose else 'OFF'}")
        elif cmd.startswith("/mode"):
            parts = cmd.split(None, 1)
            if len(parts) < 2:
                st.info(f"Current mode: `{sss.df_mode}`")
            else:
                new_mode = parts[1].strip()
                if new_mode in MODE_LABELS:
                    sss.df_mode = new_mode
                    st.info(f"Mode switched to `{new_mode}`")
                else:
                    st.warning("Unknown mode. Choose: flash | thinking | pro | ultra")
        else:
            st.warning(f"Unknown command `{user_input}`. Try `/help`.")
        st.rerun()
        return

    sss.df_messages.append({"role": "user", "content": user_input})
    with chat_container:
        st.chat_message("human").write(user_input)

    with st.spinner("🦌 Preparing Deer-flow runtime…"):
        try:
            client, prepared_profile, model_name = _ensure_runtime(selected_name)
        except Exception as exc:
            sss.df_error = f"Failed to prepare Deer-flow runtime: {exc}"
            logger.error(f"{sss.df_error}\n{traceback.format_exc()}")
            st.rerun()
            return

    if not sss.df_thread_id:
        try:
            sss.df_thread_id = asyncio.run(client.create_thread())
            _push_trace(trace_placeholder, f"🧵 New thread: `{sss.df_thread_id}`")
        except Exception as exc:
            sss.df_error = f"Failed to create thread: {exc}"
            st.rerun()
            return

    with chat_container:
        with st.chat_message("ai"):
            response_placeholder = st.empty()
            accumulated = ""
            with st.status("🦌 Running…", expanded=False) as status_widget:
                try:
                    accumulated = _stream_response(
                        client=client,
                        thread_id=sss.df_thread_id,
                        user_input=user_input,
                        model_name=model_name,
                        mode=sss.df_mode,
                        trace_placeholder=trace_placeholder,
                        response_placeholder=response_placeholder,
                    )
                    status_widget.update(label="✅ Done", state="complete", expanded=False)
                except Exception as exc:
                    sss.df_error = f"Agent error: {exc}"
                    logger.error(f"{sss.df_error}\n{traceback.format_exc()}")
                    status_widget.update(label="❌ Error", state="error")
                    st.rerun()
                    return

            if accumulated:
                response_placeholder.empty()
                render_message_with_mermaid(accumulated, st)
            else:
                response_placeholder.warning("No response received.")

    sss.df_active_profile = prepared_profile
    sss.df_model_name = model_name
    sss.df_messages.append({"role": "assistant", "content": accumulated})
    st.rerun()


try:
    _ = st.session_state
    main()
except (AttributeError, RuntimeError):
    pass
