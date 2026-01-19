"""Streamlit trace middleware for LangChain agents.

This module provides reusable middleware and UI components for capturing and displaying
tool execution traces in Streamlit applications. It enables real-time visibility into
agent tool calls, their arguments, results, and timing information.

Key Components:
    - ToolCallRecord: Data class representing a single tool execution
    - TraceMiddleware: Generic middleware for capturing tool execution details
    - display_tool_traces: UI function to render tool traces in Streamlit

Usage Example:
    ```python
from genai_blueprint.webapp.ui_components.trace_middleware import (
    TraceMiddleware,
    display_llm_traces,
    display_tool_traces,
)

    # Create middleware instance (typically stored in session state)
    if "trace_middleware" not in st.session_state:
        st.session_state.trace_middleware = TraceMiddleware()

    # Use middleware when creating agent
    agent = create_agent(
        model=llm,
        tools=tools,
        middleware=[st.session_state.trace_middleware],
    )

    # Display traces in sidebar or column
    with st.sidebar:
        display_tool_traces(st.session_state.trace_middleware)
    ```

Design Notes:
    - The middleware is stateful and accumulates tool calls across agent runs
    - Call `clear()` to reset the trace history when needed
    - Both sync and async tool calls are supported
    - The UI component handles long results with truncation and expandable sections
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

import streamlit as st
from langchain.agents.middleware import AgentMiddleware
from streamlit.delta_generator import DeltaGenerator


@dataclass
class ToolCallRecord:
    """Record of a single tool call execution.

    Captures all relevant information about a tool invocation including
    its arguments, result, timing, and any errors that occurred.

    Attributes:
        name: Name of the tool that was called
        arguments: String representation of the tool arguments/query
        result: String representation of the tool result (None if not completed or errored)
        error: Error message if the tool call failed (None if successful)
        start_time: Timestamp when the tool call started
        end_time: Timestamp when the tool call completed (None if still running)

    Example:
        ```python
        record = ToolCallRecord(
            name="search_documents",
            arguments="{'query': 'machine learning'}",
            start_time=datetime.now(),
        )
        # After execution
        record.result = "Found 5 documents..."
        record.end_time = datetime.now()
        ```
    """

    name: str
    arguments: str
    result: Optional[str] = None
    error: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    @property
    def duration_ms(self) -> Optional[float]:
        """Calculate execution duration in milliseconds.

        Returns:
            Duration in milliseconds, or None if tool is still running
        """
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds() * 1000

    @property
    def is_error(self) -> bool:
        """Check if this tool call resulted in an error."""
        return self.error is not None

    @property
    def is_complete(self) -> bool:
        """Check if this tool call has completed (success or error)."""
        return self.end_time is not None

    @property
    def formatted_time(self) -> str:
        """Get formatted start time string (HH:MM:SS.mmm)."""
        return self.start_time.strftime("%H:%M:%S.%f")[:-3]


@dataclass
class LLMCallRecord:
    """Record of a single LLM message emitted during agent execution.

    This is intentionally lightweight: we focus on which graph node produced
    the message, its content, and when it was observed. Duration is typically
    less meaningful for streamed LLM outputs, so we omit it here.
    """

    node: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def formatted_time(self) -> str:
        """Get formatted timestamp string (HH:MM:SS.mmm)."""
        return self.timestamp.strftime("%H:%M:%S.%f")[:-3]


class TraceMiddleware(AgentMiddleware):
    """Middleware to capture tool and LLM execution details for display in Streamlit.

    This middleware intercepts tool calls made by LangChain agents, recording
    their arguments, results, timing, and any errors. The captured data can
    then be displayed using the `display_tool_traces` function.

    The middleware maintains a list of `ToolCallRecord` objects that persists
    across multiple agent invocations. Use `clear()` to reset the history.

    Attributes:
        tool_calls: List of completed tool call records
        current_call: The tool call currently being executed (None if idle)

    Thread Safety:
        This middleware is NOT thread-safe. Each Streamlit session should have
        its own middleware instance stored in session state.

    Example:
        ```python
        # Initialize in session state
        if "trace_middleware" not in st.session_state:
            st.session_state.trace_middleware = TraceMiddleware()

        middleware = st.session_state.trace_middleware

        # Create agent with middleware
        agent = create_agent(
            model=llm,
            tools=tools,
            middleware=[middleware],
        )

        # After agent run, access captured traces
        for call in middleware.tool_calls:
            print(f"{call.name}: {call.duration_ms}ms")
        ```
    """

    def __init__(self) -> None:
        """Initialize the trace middleware with empty state."""
        self.tool_calls: list[ToolCallRecord] = []
        self.current_call: Optional[ToolCallRecord] = None
        # Lightweight storage for LLM calls, populated explicitly by the UI layer.
        # We keep this generic to avoid coupling to any particular LangChain internals
        # for model tracing while still co-locating traces with tool calls.
        self.llm_calls: list["LLMCallRecord"] = []

    def clear(self) -> None:
        """Clear all captured tool and LLM call records.

        Call this method to reset the trace history, typically when starting
        a new conversation or when the user requests to clear the trace display.
        """
        self.tool_calls = []
        self.current_call = None
        self.llm_calls = []

    def add_llm_call(self, node: str, content: str) -> None:
        """Record a single LLM message associated with a graph node.

        The UI layer is responsible for calling this when it observes new
        `AIMessage` instances emitted from the graph while streaming.
        """
        self.llm_calls.append(
            LLMCallRecord(
                node=node,
                content=content,
            )
        )

    def _extract_tool_info(self, request: Any) -> tuple[str, str]:
        """Extract tool name and arguments from a tool call request.

        Args:
            request: The tool call request object from LangChain

        Returns:
            Tuple of (tool_name, arguments_string)
        """
        tool_call = getattr(request, "tool_call", {})
        tool_name = tool_call.get("name", "<unknown>")
        tool_args = tool_call.get("args", {})
        return tool_name, str(tool_args)

    def _extract_result(self, result: Any) -> str:
        """Extract a string representation from a tool result.

        Args:
            result: The tool execution result

        Returns:
            String representation of the result
        """
        if hasattr(result, "content") and result.content:
            return str(result.content)
        return str(result)

    def _start_call(self, request: Any) -> ToolCallRecord:
        """Create and register a new tool call record.

        Args:
            request: The tool call request object

        Returns:
            The newly created ToolCallRecord
        """
        tool_name, tool_args = self._extract_tool_info(request)
        self.current_call = ToolCallRecord(
            name=tool_name,
            arguments=tool_args,
        )
        return self.current_call

    def _complete_call(self, result: Any) -> None:
        """Mark the current call as successfully completed.

        Args:
            result: The tool execution result
        """
        if self.current_call is not None:
            self.current_call.result = self._extract_result(result)
            self.current_call.end_time = datetime.now()
            self.tool_calls.append(self.current_call)
            self.current_call = None

    def _fail_call(self, error: Exception) -> None:
        """Mark the current call as failed with an error.

        Args:
            error: The exception that occurred during tool execution
        """
        if self.current_call is not None:
            self.current_call.error = str(error)
            self.current_call.end_time = datetime.now()
            self.tool_calls.append(self.current_call)
            self.current_call = None

    def wrap_tool_call(self, request: Any, handler: Callable) -> Any:
        """Wrap a synchronous tool call to capture execution details.

        This method is called by the LangChain agent framework for each
        synchronous tool invocation. It records the tool call details
        before and after execution.

        Args:
            request: The tool call request containing tool name and arguments
            handler: The actual tool execution function to call

        Returns:
            The result from the tool execution

        Raises:
            Any exception raised by the tool is re-raised after being recorded
        """
        self._start_call(request)

        try:
            result = handler(request)
            self._complete_call(result)
            return result
        except Exception as e:
            self._fail_call(e)
            raise

    async def awrap_tool_call(self, request: Any, handler: Callable) -> Any:
        """Wrap an asynchronous tool call to capture execution details.

        This method is called by the LangChain agent framework for each
        asynchronous tool invocation. It records the tool call details
        before and after execution.

        Args:
            request: The tool call request containing tool name and arguments
            handler: The actual async tool execution function to call

        Returns:
            The result from the tool execution

        Raises:
            Any exception raised by the tool is re-raised after being recorded
        """
        self._start_call(request)

        try:
            result = await handler(request)
            self._complete_call(result)
            return result
        except Exception as e:
            self._fail_call(e)
            raise


def display_tool_traces(
    middleware: "TraceMiddleware",
    container: Optional[DeltaGenerator] = None,
    max_result_length: int = 2000,
    show_clear_button: bool = True,
    expand_latest: bool = True,
) -> None:
    """Display tool execution traces in a Streamlit UI.

    Renders a list of tool call records with expandable details including
    tool name, arguments, results, timing, and error information.

    Args:
        middleware: The TraceMiddleware instance containing tool call records
        container: Optional Streamlit container to render into (defaults to current context)
        max_result_length: Maximum characters to display for results before truncating
        show_clear_button: Whether to show a button to clear the trace history
        expand_latest: Whether to auto-expand the most recent tool call

    Example:
        ```python
        # In sidebar
        with st.sidebar:
            display_tool_traces(st.session_state.trace_middleware)

        # In a column with custom settings
        col1, col2 = st.columns(2)
        with col1:
            display_tool_traces(
                middleware,
                max_result_length=500,
                show_clear_button=False,
            )
        ```
    """
    ctx = container or st

    if not middleware.tool_calls:
        ctx.info("No tool calls yet. Send a message to see tool interactions!")
        return

    # Header with optional clear button
    if show_clear_button:
        col1, col2 = ctx.columns([3, 1])
        with col1:
            ctx.subheader("Tool Execution Trace")
        with col2:
            if ctx.button("Clear", key="clear_traces", help="Clear execution traces"):
                middleware.clear()
                st.rerun()
    else:
        ctx.subheader("Tool Execution Trace")

    # Summary count
    count = len(middleware.tool_calls)
    ctx.caption(f"{count} tool call{'s' if count != 1 else ''}")

    # Display each tool call in an expandable section
    for i, call in enumerate(middleware.tool_calls):
        _render_tool_call_expander(
            ctx,
            call,
            index=i,
            total=count,
            expand_latest=expand_latest,
            max_result_length=max_result_length,
        )


def _render_tool_call_expander(
    ctx: DeltaGenerator,
    call: ToolCallRecord,
    index: int,
    total: int,
    expand_latest: bool,
    max_result_length: int,
) -> None:
    """Render a single tool call as an expandable section.

    Args:
        ctx: Streamlit context to render into
        call: The tool call record to display
        index: Index of this call in the list (0-based)
        total: Total number of tool calls
        expand_latest: Whether to auto-expand if this is the latest call
        max_result_length: Maximum characters before truncating results
    """
    status_emoji = "X" if call.is_error else "OK"

    # Build expander title with truncated query
    max_query_len = 30
    truncated_query = call.arguments
    if len(truncated_query) > max_query_len:
        truncated_query = truncated_query[:max_query_len] + "..."

    title = f"{status_emoji} [{call.formatted_time}] {call.name}: {truncated_query}"
    is_latest = index == total - 1

    with ctx.expander(title, expanded=(expand_latest and is_latest)):
        # Tool name
        ctx.markdown(f"**Tool:** `{call.name}`")

        # Timing information
        if call.formatted_time:
            timing_text = f"**Time:** {call.formatted_time}"
            if call.duration_ms is not None:
                timing_text += f" (duration: {call.duration_ms:.1f}ms)"
            ctx.markdown(timing_text)

        # Arguments
        ctx.markdown("**Arguments:**")
        ctx.code(call.arguments, language="text")

        # Result or Error
        if call.is_error:
            ctx.markdown("**Error:**")
            ctx.error(call.error)
        else:
            ctx.markdown("**Result:**")
            result_text = call.result or "No result returned"

            if len(result_text) > max_result_length:
                truncated = result_text[:max_result_length] + "\n\n... (truncated)"
                ctx.code(truncated, language="text")
                ctx.caption(f"Result was {len(result_text)} characters (truncated for display)")
            else:
                ctx.code(result_text, language="text")


def display_llm_traces(
    middleware: "TraceMiddleware",
    container: Optional[DeltaGenerator] = None,
    max_content_length: int = 4000,
    show_clear_button: bool = False,
    expand_latest: bool = True,
) -> None:
    """Display LLM messages observed during agent execution.

    This complements :func:`display_tool_traces` by showing which graph nodes
    produced which LLM outputs, in chronological order.
    """
    ctx = container or st

    if not getattr(middleware, "llm_calls", None):
        ctx.info("No LLM calls yet. Send a message to see model outputs!")
        return

    # Header with optional clear button
    if show_clear_button:
        col1, col2 = ctx.columns([3, 1])
        with col1:
            ctx.subheader("LLM Call Trace")
        with col2:
            if ctx.button("Clear LLM", key="clear_llm_traces", help="Clear LLM call traces"):
                middleware.llm_calls = []
                st.rerun()
    else:
        ctx.subheader("LLM Call Trace")

    count = len(middleware.llm_calls)
    ctx.caption(f"{count} LLM message{'s' if count != 1 else ''}")

    for i, call in enumerate(middleware.llm_calls):
        _render_llm_call_expander(
            ctx,
            call,
            index=i,
            total=count,
            expand_latest=expand_latest,
            max_content_length=max_content_length,
        )


def _render_llm_call_expander(
    ctx: DeltaGenerator,
    call: LLMCallRecord,
    index: int,
    total: int,
    expand_latest: bool,
    max_content_length: int,
) -> None:
    """Render a single LLM call as an expandable section."""
    max_preview_len = 60
    preview = call.content.replace("\n", " ")
    if len(preview) > max_preview_len:
        preview = preview[:max_preview_len] + "..."

    title = f"[{call.formatted_time}] {call.node}: {preview}"
    is_latest = index == total - 1

    with ctx.expander(title, expanded=(expand_latest and is_latest)):
        ctx.markdown(f"**Node:** `{call.node}`")
        ctx.markdown(f"**Time:** {call.formatted_time}")
        ctx.markdown("**Content:**")

        content = call.content
        if len(content) > max_content_length:
            truncated = content[:max_content_length] + "\n\n... (truncated)"
            ctx.code(truncated, language="text")
            ctx.caption(f"Content was {len(content)} characters (truncated for display)")
        else:
            ctx.code(content, language="text")
