"""Streamlit DeerFlow demo — DeerFlow-inspired 2-panel UI.

Layout mirrors DeerFlow's native workspace:
  - Left panel  : Execution trace — structured phase cards with tool rows.
                  Click 📄 on any tool to load its output in the Artifact tab.
  - Right panel : Two tabs — "💬 Chat" (conversation) and "📄 Artifact" (code /
                  files / search results / Mermaid diagrams).

Uses ``EmbeddedDeerFlowClient`` (in-process, no LangGraph server required).
Set the ``DEER_FLOW_PATH`` environment variable to your deer-flow clone.
"""

import asyncio
import os
import re
import traceback
import uuid
from time import monotonic
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from genai_tk.agents.deer_flow import (
    ClarificationEvent,
    DeerFlowProfile,
    EmbeddedDeerFlowClient,
    ErrorEvent,
    NodeEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    load_deer_flow_profiles,
)
from genai_tk.agents.deer_flow.cli_commands import _NODE_LABELS, _prepare_profile
from loguru import logger
from pydantic import BaseModel, Field
from streamlit import session_state as sss

from genai_blueprint.webapp.ui_components.agent_layout import render_agent_sidebar, render_sidebar_demo_section
from genai_blueprint.webapp.ui_components.message_renderer import render_message_with_mermaid

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_FILE = "config/agents/deerflow.yaml"
PAGE_TITLE = "🦌 DeerFlow Agent"
CHAT_HEIGHT = 600
TRACE_HEIGHT = 680

MODE_LABELS: dict[str, str] = {
    "flash": "⚡ Flash",
    "thinking": "💡 Thinking",
    "pro": "🎓 Pro",
    "ultra": "🚀 Ultra",
}

# Icons shown next to each known graph node label
_NODE_ICONS: dict[str, str] = {
    "planner": "🗺️",
    "reporter": "✍️",
    "researcher": "🔍",
    "coder": "💻",
    "model": "🤔",
    "tools": "🛠️",
    "search_tool": "🌐",
    "web_search": "🌐",
    "tavily_search": "🌐",
    "python_repl": "🐍",
    "bash": "⚡",
    "file_read": "📂",
    "file_write": "📝",
    "browser": "🌍",
    "subagent": "🤖",
    "reflection": "🪞",
}

# DeerFlow uses a flat lead-agent that calls tools directly (stream_mode="values"
# yields no node-name events). We infer the logical phase from the tool name.
_TOOL_TO_NODE: dict[str, str] = {
    # Web research
    "web_search_tool": "researcher",
    "web_fetch_tool": "researcher",
    "image_search_tool": "researcher",
    "view_image": "researcher",
    "web_search": "researcher",
    "tavily_search": "researcher",
    "search_tool": "researcher",
    # Code / sandbox
    "run_python_code": "coder",
    "python_repl": "coder",
    "bash": "coder",
    "execute_code": "coder",
    # File I/O
    "file_read": "coder",
    "file_write": "coder",
    # Sub-agent delegation
    "task": "subagent",
    "invoke_acp_agent": "subagent",
    # Utility
    "present_files": "reporter",
    "tool_search": "tools",
}

# ---------------------------------------------------------------------------
# Data models for trace + artifacts
# ---------------------------------------------------------------------------


class Artifact(BaseModel):
    """A single extractable output produced during an agent run."""

    type: str  # "code" | "file" | "search" | "web" | "mermaid" | "text"
    title: str
    content: str
    language: str = ""


class ToolDetail(BaseModel):
    """One tool call + result captured from the event stream."""

    name: str
    args: dict = Field(default_factory=dict)
    result: str = ""
    artifact: Artifact | None = None


class TraceStep(BaseModel):
    """One active graph phase (Planner, Researcher, Coder, Reporter …)."""

    node: str
    label: str
    icon: str = "→"
    elapsed: float = 0.0
    tools: list[ToolDetail] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Artifact extraction helpers
# ---------------------------------------------------------------------------

_FENCED_CODE_RE = re.compile(r"```(\w*)\n(.*?)\n```", re.DOTALL)
_MERMAID_STARTS = (
    "graph ",
    "flowchart ",
    "sequenceDiagram",
    "classDiagram",
    "erDiagram",
    "gantt",
    "mindmap",
)


def _extract_tool_artifact(name: str, args: dict, result: str) -> Artifact | None:
    """Convert a tool call + result into a displayable Artifact, or None."""
    n = (name or "").lower()

    if n in ("python_repl", "coder"):
        code = args.get("code") or args.get("script") or ""
        if not code and result:
            code = result
        if code:
            return Artifact(type="code", title=f"🐍 Python — {n}", content=code, language="python")

    if n == "bash":
        cmd = args.get("command") or args.get("cmd") or ""
        output = result or ""
        content = f"# command\n{cmd}\n\n# output\n{output}" if cmd else output
        if content.strip():
            return Artifact(type="code", title="⚡ Shell", content=content, language="bash")

    if n == "file_write":
        path = args.get("path") or args.get("file_path") or "file"
        content = args.get("content") or args.get("text") or result or ""
        if content:
            lang = _lang_from_path(path)
            return Artifact(type="file", title=f"📝 {path}", content=content, language=lang)

    if n in ("web_search", "tavily_search", "search_tool"):
        if result:
            return Artifact(type="search", title="🌐 Search results", content=result, language="")

    if n == "browser":
        if result:
            return Artifact(type="web", title="🌍 Browser output", content=result, language="")

    return None


def _lang_from_path(path: str) -> str:
    """Infer syntax-highlighting language from a file path extension."""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "py": "python",
        "sh": "bash",
        "bash": "bash",
        "js": "javascript",
        "ts": "typescript",
        "json": "json",
        "yaml": "yaml",
        "yml": "yaml",
        "md": "markdown",
        "sql": "sql",
        "html": "html",
        "css": "css",
    }.get(ext, "text")


def _extract_final_artifacts(text: str) -> list[Artifact]:
    """Extract code blocks and Mermaid diagrams from the final assistant message."""
    artifacts: list[Artifact] = []
    for match in _FENCED_CODE_RE.finditer(text):
        lang, code = match.group(1).strip(), match.group(2).strip()
        if not code:
            continue
        if lang == "mermaid" or any(code.lstrip().startswith(s) for s in _MERMAID_STARTS):
            artifacts.append(Artifact(type="mermaid", title="📊 Diagram", content=code, language="mermaid"))
        else:
            label = lang.capitalize() if lang else "Code"
            artifacts.append(Artifact(type="code", title=f"💻 {label}", content=code, language=lang or "text"))
    return artifacts


def _init_session() -> None:
    defaults: dict[str, Any] = {
        "df_messages": [],
        "df_thread_id": None,
        "df_client": None,
        "df_profile_name": None,
        "df_active_profile": None,
        "df_mode": "pro",
        "df_model_name": None,
        "df_runtime_signature": None,
        "df_config_path": None,
        "df_server_ready": False,
        "df_trace_steps": [],  # list[TraceStep]
        "df_all_artifacts": [],  # list[Artifact] from completed run
        "df_selected_artifact": None,  # Artifact | None
        "df_trace_verbose": True,
        "df_error": None,
    }
    for key, val in defaults.items():
        if key not in sss:
            sss[key] = val


def _clear_chat() -> None:
    sss.df_messages = []
    sss.df_thread_id = None
    sss.df_trace_steps = []
    sss.df_all_artifacts = []
    sss.df_selected_artifact = None


def _clear_runtime() -> None:
    sss.df_server_ready = False
    sss.df_client = None
    sss.df_active_profile = None
    sss.df_model_name = None
    sss.df_config_path = None
    sss.df_runtime_signature = None


def _clear_all() -> None:
    _clear_chat()
    _clear_runtime()
    sss.df_error = None


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------


@st.cache_data(ttl=60)
def _load_profiles() -> list[DeerFlowProfile]:
    try:
        return load_deer_flow_profiles(CONFIG_FILE)
    except Exception as exc:
        logger.error(f"Failed to load DeerFlow profiles: {exc}")
        return []


def _profile_by_name(profiles: list[DeerFlowProfile], name: str) -> DeerFlowProfile | None:
    return next((p for p in profiles if p.name == name), None)


# ---------------------------------------------------------------------------
# Runtime lifecycle
# ---------------------------------------------------------------------------


def _selected_llm_override() -> str | None:
    try:
        from genai_tk.utils.config_mngr import global_config

        return global_config().get_str("llm.models.default") or None
    except Exception:
        return None


def _runtime_signature(profile_name: str, llm: str | None) -> str:
    return f"{profile_name}|{llm or ''}"


def _ensure_runtime(profile_name: str) -> tuple[EmbeddedDeerFlowClient, DeerFlowProfile, str | None]:
    """Prepare runtime (once per profile+LLM combination) and cache in session state."""
    llm = _selected_llm_override()
    sig = _runtime_signature(profile_name, llm)

    if sss.df_server_ready and sss.df_client and sss.df_runtime_signature == sig and sss.df_active_profile:
        return sss.df_client, sss.df_active_profile, sss.df_model_name

    prepared_profile, model_name, config_path = asyncio.run(
        _prepare_profile(
            profile_name=profile_name,
            llm_override=llm,
            extra_mcp=[],
            mode_override=None,
            verbose=False,
        )
    )
    client = EmbeddedDeerFlowClient(config_path=config_path, model_name=model_name)

    sss.df_server_ready = True
    sss.df_client = client
    sss.df_active_profile = prepared_profile
    sss.df_model_name = model_name
    sss.df_config_path = str(config_path)
    sss.df_runtime_signature = sig
    return client, prepared_profile, model_name


def _stream_response(
    *,
    client: EmbeddedDeerFlowClient,
    thread_id: str,
    user_input: str,
    model_name: str | None,
    mode: str,
    response_placeholder: Any,
) -> tuple[str, list[TraceStep], list[Artifact], bool]:
    """Stream one turn and return (full_text, trace_steps, final_artifacts, is_clarification).

    ``is_clarification`` is True when DeerFlow paused to ask a question via
    ``ask_clarification``.  In that case ``full_text`` contains the question
    and the caller should show it as an assistant chat bubble without running
    the post-processing pipeline.
    """
    steps: list[TraceStep] = []
    current_step: TraceStep | None = None
    pending_tool: ToolDetail | None = None
    token_parts: list[str] = []
    clarification_text: list[str] = []
    t0 = monotonic()

    def _get_or_create_step(node: str) -> TraceStep:
        nonlocal current_step
        label = _NODE_LABELS.get(node, node)
        icon = _NODE_ICONS.get(node, "→")
        step = TraceStep(node=node, label=label, icon=icon, elapsed=round(monotonic() - t0, 1))
        steps.append(step)
        current_step = step
        return step

    async def _collect() -> None:
        nonlocal current_step, pending_tool
        async for event in client.stream_message(
            thread_id=thread_id,
            user_input=user_input,
            model_name=model_name,
            mode=mode,
        ):
            # NodeEvent would be ideal, but DeerFlow's stream_mode="values" never
            # emits node-name events. We infer phase from tool names instead.
            if isinstance(event, NodeEvent):
                if (not current_step) or (event.node != current_step.node):
                    if current_step and pending_tool:
                        current_step.tools.append(pending_tool)
                        pending_tool = None
                    _get_or_create_step(event.node)

            elif isinstance(event, ToolCallEvent):
                if event.tool_name:
                    # Infer the logical phase from the tool name.
                    node = _TOOL_TO_NODE.get(event.tool_name, "tools")
                    # New tool call in a different phase → create a new step.
                    if not current_step or current_step.node != node:
                        if current_step and pending_tool:
                            current_step.tools.append(pending_tool)
                        _get_or_create_step(node)
                    elif pending_tool:
                        # Same phase but previous tool not yet resolved → flush it.
                        current_step.tools.append(pending_tool)
                    pending_tool = ToolDetail(name=event.tool_name, args=event.args or {})

            elif isinstance(event, ClarificationEvent):
                # Agent paused to ask for user input — show question in chat
                if not current_step:
                    _get_or_create_step("planner")
                clarification_text.append(event.question)
                response_placeholder.markdown(event.question + " ▌")

            elif isinstance(event, ToolResultEvent):
                if pending_tool and event.tool_name == pending_tool.name:
                    pending_tool.result = event.content or ""
                    pending_tool.artifact = _extract_tool_artifact(
                        pending_tool.name, pending_tool.args, pending_tool.result
                    )
                    if current_step:
                        current_step.tools.append(pending_tool)
                    pending_tool = None
                elif event.tool_name:
                    tool = ToolDetail(name=event.tool_name, result=event.content or "")
                    tool.artifact = _extract_tool_artifact(tool.name, {}, tool.result)
                    if current_step:
                        current_step.tools.append(tool)

            elif isinstance(event, TokenEvent):
                # First token: open a "reporter" step to signal the writing phase.
                if not current_step or current_step.node != "reporter":
                    if current_step and pending_tool:
                        current_step.tools.append(pending_tool)
                        pending_tool = None
                    _get_or_create_step("reporter")
                token_parts.append(event.data)
                response_placeholder.markdown(token_parts[-1] + " ▌")

            elif isinstance(event, ErrorEvent):
                token_parts.append(f"\n\n⚠️ *{event.message}*")
                if current_step:
                    current_step.tools.append(ToolDetail(name="❌ Error", result=event.message))

        if pending_tool and current_step:
            current_step.tools.append(pending_tool)

    asyncio.run(_collect())

    if clarification_text:
        full_text = clarification_text[-1]
        return full_text, steps, [], True

    full_text = token_parts[-1] if token_parts else ""
    final_artifacts = _extract_final_artifacts(full_text)
    return full_text, steps, final_artifacts, False


# ---------------------------------------------------------------------------
# UI — trace panel (left)
# ---------------------------------------------------------------------------


def _render_trace_panel(steps: list[TraceStep]) -> None:
    """Render structured execution timeline — called inside a scrollable container."""
    if not steps:
        st.markdown(
            "<div style='color:#888;padding:2rem 1rem;text-align:center'>"
            "Send a message to see the research activity here.</div>",
            unsafe_allow_html=True,
        )
        return

    for step_idx, step in enumerate(steps):
        dim_time = (
            f"<span style='color:#888;font-size:.8em;float:right'>+{step.elapsed:.0f}s</span>" if step.elapsed else ""
        )
        st.markdown(
            f"**{step.icon} {step.label}**{dim_time}",
            unsafe_allow_html=True,
        )

        for tool_idx, tool in enumerate(step.tools):
            args_chip = ""
            if tool.args:
                first_val = str(list(tool.args.values())[0])[:55].replace("\n", " ")
                args_chip = f"<span style='color:#aaa;font-size:.75em;margin-left:6px'>{first_val}</span>"

            has_artifact = tool.artifact is not None
            col_icon, col_name, col_btn = st.columns([0.08, 0.78, 0.14])
            with col_icon:
                st.markdown("⚙️")
            with col_name:
                st.markdown(
                    f"<code style='font-size:.8em'>{tool.name}</code>{args_chip}",
                    unsafe_allow_html=True,
                )
            with col_btn:
                if has_artifact:
                    if st.button("📄", key=f"art_{step_idx}_{tool_idx}", help="View output"):
                        sss.df_selected_artifact = tool.artifact
                        st.rerun()

        if step_idx < len(steps) - 1:
            st.markdown(
                "<hr style='margin:6px 0;border:none;border-top:1px solid #333'>",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# UI — artifact panel (right tab)
# ---------------------------------------------------------------------------


def _render_artifact(artifact: Artifact) -> None:
    """Render one artifact — called inside a container."""
    st.markdown(f"#### {artifact.title}")
    if artifact.type == "mermaid":
        render_message_with_mermaid(f"```mermaid\n{artifact.content}\n```", st)
    elif artifact.type in ("code", "file"):
        st.code(artifact.content, language=artifact.language or "text")
    elif artifact.type == "search":
        st.markdown(artifact.content[:4000])
    elif artifact.type == "web":
        with st.expander("Full browser output", expanded=True):
            st.text(artifact.content[:4000])
    else:
        st.markdown(artifact.content[:5000])


def _render_artifact_gallery(artifacts: list[Artifact]) -> None:
    """Show artifact buttons — called inside a container."""
    if not artifacts:
        st.markdown(
            "<div style='color:#888;padding:2rem 1rem;text-align:center'>"
            "Click 📄 on a trace tool to view its output here.</div>",
            unsafe_allow_html=True,
        )
        return
    st.markdown("**Outputs from this run** — click to open:")
    for idx, art in enumerate(artifacts):
        if st.button(art.title, key=f"gallery_{idx}", use_container_width=True):
            sss.df_selected_artifact = art
            st.rerun()


def _render_sidebar(profiles: list[DeerFlowProfile]) -> tuple[str | None, str]:
    """Render the full DeerFlow sidebar.

    Contains: profile selector + metadata + examples list, mode selectbox,
    verbose trace toggle, and clear buttons.

    Returns:
        ``(selected_profile_name_or_None, selected_mode_key)``
    """
    with st.sidebar:
        st.divider()

        def _profile_info(p: DeerFlowProfile) -> None:
            if p.description:
                st.caption(p.description)
            if p.tool_groups:
                st.markdown("**Tools:** " + ", ".join(f"`{g}`" for g in p.tool_groups))
            if p.mcp_servers:
                st.markdown("**MCP:** " + ", ".join(f"`{m}`" for m in p.mcp_servers))

        selected_profile = render_sidebar_demo_section(
            profiles,
            current_name=sss.df_profile_name,
            info_fn=_profile_info,
        )

        st.divider()

        mode_keys = list(MODE_LABELS.keys())
        mode_idx = mode_keys.index(sss.df_mode) if sss.df_mode in mode_keys else 0
        selected_mode = st.selectbox(
            "⚙️ Mode",
            mode_keys,
            format_func=lambda x: MODE_LABELS[x],
            index=mode_idx,
            key="df_mode_sel",
        )

        sss.df_trace_verbose = st.toggle(
            "Verbose trace",
            value=sss.df_trace_verbose,
            help="Show unlabelled graph nodes.",
        )

        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗑️ Chat", help="Clear conversation"):
                _clear_chat()
                st.rerun()
        with col2:
            if st.button("🗑️ Full", help="Clear runtime + chat"):
                _clear_all()
                st.rerun()

        st.divider()
        st.caption("Full UI: `cli deerflow --web`")

    selected_name = selected_profile.name if selected_profile else None
    return selected_name, selected_mode


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    _init_session()
    profiles = _load_profiles()

    if not os.environ.get("DEER_FLOW_PATH"):
        st.error(
            "**DEER_FLOW_PATH is not set.** "
            "Point it to your deer-flow clone: `export DEER_FLOW_PATH=/path/to/deer-flow`"
        )
        st.stop()

    # Sidebar: LLM selector + Edit Config (shared) + profile/mode/clear (DeerFlow-specific)
    render_agent_sidebar(CONFIG_FILE)
    selected_name, selected_mode = _render_sidebar(profiles)

    if selected_name is None:
        st.stop()

    # ── Title ─────────────────────────────────────────────────────────────
    st.title(PAGE_TITLE)

    # Detect profile change → clear state
    if sss.df_profile_name and sss.df_profile_name != selected_name:
        _clear_all()

    sss.df_profile_name = selected_name
    sss.df_mode = selected_mode

    profile = _profile_by_name(profiles, selected_name)
    if profile is None:
        st.error(f"Profile '{selected_name}' not found.")
        st.stop()

    if sss.df_error:
        st.error(sss.df_error)
        if st.button("Dismiss"):
            sss.df_error = None
            st.rerun()

    # Two-column layout: [2 trace] | [3 chat + artifact]
    col_trace, col_main = st.columns([2, 3], gap="medium")

    with col_trace:
        st.subheader("🔍 Execution Trace")
        with st.container(height=TRACE_HEIGHT, border=True):
            _render_trace_panel(sss.df_trace_steps)

    with col_main:
        tab_chat, tab_artifact = st.tabs(["\U0001f4ac Chat", "\U0001f4c4 Artifact"])

        with tab_chat:
            with st.container(height=CHAT_HEIGHT, border=True):
                if not sss.df_messages:
                    st.info("Hello! I'm DeerFlow. Ask anything or pick an example from the sidebar.")
                for msg in sss.df_messages:
                    if msg["role"] == "user":
                        st.chat_message("human").write(msg["content"])
                    else:
                        with st.chat_message("ai"):
                            render_message_with_mermaid(msg["content"], st)

        with tab_artifact:
            with st.container(height=CHAT_HEIGHT, border=True):
                if sss.df_selected_artifact:
                    if st.button("\u2190 All outputs"):
                        sss.df_selected_artifact = None
                        st.rerun()
                    _render_artifact(sss.df_selected_artifact)
                else:
                    _render_artifact_gallery(sss.df_all_artifacts)

    if sss.get("df_show_info"):
        sss.df_show_info = False
        active = sss.df_active_profile or profile
        with st.container(border=True):
            st.markdown(f"**Profile:** `{selected_name}` \u00b7 **Mode:** `{selected_mode}`")
            st.markdown(f"**Model:** `{sss.df_model_name or '(profile default)'}`")
            if active.mcp_servers:
                st.markdown("**MCP:** " + ", ".join(active.mcp_servers))
            if sss.df_thread_id:
                st.markdown(f"**Thread:** `{sss.df_thread_id}`")
            if sss.df_config_path:
                st.caption(f"Config: {sss.df_config_path}")

    user_input = st.chat_input("Ask DeerFlow… or /help", key="df_input")
    if not user_input or not user_input.strip():
        return

    user_input = user_input.strip()

    # Slash commands
    if user_input.startswith("/"):
        cmd = user_input.lower().strip()
        if cmd in ("/clear", "/reset", "/quit", "/exit", "/q"):
            _clear_chat()
        elif cmd == "/help":
            st.info(
                "**Commands:**\n"
                "- `/mode flash|thinking|pro|ultra` \u2014 switch mode\n"
                "- `/trace` \u2014 toggle verbose trace\n"
                "- `/clear` \u2014 new conversation\n"
                "- `/info` \u2014 show runtime details\n"
                "- `/help` \u2014 this message",
                icon="\U0001f4d6",
            )
        elif cmd == "/info":
            sss.df_show_info = True
        elif cmd == "/trace":
            sss.df_trace_verbose = not sss.df_trace_verbose
            st.info(f"Verbose trace: {'**ON**' if sss.df_trace_verbose else '**OFF**'}")
        elif cmd.startswith("/mode"):
            parts = cmd.split(None, 1)
            if len(parts) < 2:
                st.info(f"Current mode: `{sss.df_mode}`")
            else:
                new_mode = parts[1].strip()
                if new_mode in MODE_LABELS:
                    sss.df_mode = new_mode
                    st.success(f"Mode \u2192 `{new_mode}` ({MODE_LABELS[new_mode]})")
                else:
                    st.warning("Unknown mode. Choose: `flash` | `thinking` | `pro` | `ultra`")
        else:
            st.warning(f"Unknown command `{user_input}`. Try `/help`.")
        st.rerun()
        return

    # Agent call
    sss.df_messages.append({"role": "user", "content": user_input})
    sss.df_selected_artifact = None
    sss.df_all_artifacts = []
    sss.df_trace_steps = []

    with st.spinner("\U0001f98c Preparing DeerFlow runtime\u2026"):
        try:
            client, prepared_profile, model_name = _ensure_runtime(selected_name)
        except Exception as exc:
            sss.df_error = f"Failed to prepare DeerFlow runtime: {exc}"
            logger.error(f"{sss.df_error}\n{traceback.format_exc()}")
            st.rerun()
            return

    if not sss.df_thread_id:
        sss.df_thread_id = uuid.uuid4().hex

    # Status widget + execution live in the left trace panel.
    # response_placeholder is created inside the status so streaming tokens
    # appear there during the run; after st.rerun() the final answer renders
    # properly in the chat history.
    with col_trace:
        with st.status("🦌 Running…", expanded=True) as status_widget:
            response_placeholder = st.empty()
            try:
                full_text, new_steps, final_artifacts, is_clarification = _stream_response(
                    client=client,
                    thread_id=sss.df_thread_id,
                    user_input=user_input,
                    model_name=model_name,
                    mode=sss.df_mode,
                    response_placeholder=response_placeholder,
                )
                if is_clarification:
                    status_widget.update(label="❓ Clarification needed", state="complete", expanded=False)
                else:
                    status_widget.update(label="✅ Done", state="complete", expanded=False)
            except Exception as exc:
                sss.df_error = f"Agent error: {exc}"
                logger.error(f"{sss.df_error}\n{traceback.format_exc()}")
                status_widget.update(label="❌ Error", state="error")
                st.rerun()
                return

    response_placeholder.empty()

    sss.df_active_profile = prepared_profile
    sss.df_model_name = model_name
    sss.df_trace_steps = new_steps

    if not full_text:
        st.rerun()
        return

    sss.df_messages.append({"role": "assistant", "content": full_text})

    if not is_clarification:
        tool_artifacts = [tool.artifact for step in new_steps for tool in step.tools if tool.artifact is not None]
        sss.df_all_artifacts = tool_artifacts + final_artifacts

    st.rerun()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

try:
    _ = st.session_state
    main()
except (AttributeError, RuntimeError):
    pass
