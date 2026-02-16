"""Deer-flow agent wrapper for GenAI Blueprint.

Creates and configures Deer-flow agents using GenAI Blueprint's LLM factory
and tool system, while leveraging Deer-flow's advanced middleware chain
(summarization, memory, subagents, sandboxing, etc.).

The agent is a standard LangGraph CompiledStateGraph, compatible with
the same streaming patterns used in reAct_agent.py.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from langchain.tools import BaseTool
from loguru import logger

# Type alias for the compiled graph (avoid requiring deer-flow import at module level)
type DeerFlowAgent = Any  # Actually CompiledStateGraph


@dataclass
class DeerFlowAgentConfig:
    """Configuration for a Deer-flow agent profile.

    Loaded from config/agents/deerflow.yaml.
    """

    name: str
    description: str = ""
    tool_groups: list[str] = field(default_factory=lambda: ["web"])
    subagent_enabled: bool = False
    thinking_enabled: bool = True
    is_plan_mode: bool = False
    mode: str = "flash"  # flash, thinking, pro, ultra
    mcp_servers: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)  # List of "category/skill-name" or "skill-name"
    tools: list[BaseTool] = field(default_factory=list)
    tool_configs: list[dict[str, Any]] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    example_queries: list[str] = field(default_factory=list)
    system_prompt: str | None = None
    examples: list[str] = field(default_factory=list)


def load_deer_flow_profiles(
    config_path: str = "config/agents/deerflow.yaml",
) -> list[DeerFlowAgentConfig]:
    """Load Deer-flow agent profiles from YAML config.

    Args:
        config_path: Path to the deerflow.yaml config file

    Returns:
        List of DeerFlowAgentConfig instances
    """
    path = Path(config_path)
    if not path.exists():
        logger.warning(f"Deer-flow config not found at {path}")
        return []

    with open(path) as f:
        raw = yaml.safe_load(f)

    profiles = []
    for entry in raw.get("deerflow_agents", []):
        # Separate raw tool configs from resolved tools
        raw_tools = entry.pop("tools", [])

        profile = DeerFlowAgentConfig(
            name=entry.get("name", "Unnamed"),
            description=entry.get("description", ""),
            tool_groups=entry.get("tool_groups", ["web"]),
            subagent_enabled=entry.get("subagent_enabled", False),
            thinking_enabled=entry.get("thinking_enabled", True),
            is_plan_mode=entry.get("is_plan_mode", False),
            mode=entry.get("mode", "flash"),
            mcp_servers=entry.get("mcp_servers", []),
            skills=entry.get("skills", []),
            tool_configs=raw_tools,
            features=entry.get("features", []),
            example_queries=entry.get("examples", []),  # Map 'examples' to 'example_queries'
            system_prompt=entry.get("system_prompt"),
            examples=entry.get("examples", []),
        )
        profiles.append(profile)

    logger.info(f"Loaded {len(profiles)} Deer-flow profiles from {config_path}")
    return profiles


def resolve_tools_from_config(tool_configs: list[dict[str, Any]]) -> list[BaseTool]:
    """Resolve tool specifications into BaseTool instances.

    Supports the same patterns as GenAI Blueprint's langchain tool loading:
      - factory: module.path:function_name  (with config: block)
      - class: module.path:ClassName  (with extra kwargs)
      - function: module.path:function_name

    Args:
        tool_configs: List of raw tool config dicts from YAML

    Returns:
        List of resolved BaseTool instances
    """
    # We reuse genai_tk's tool loading by constructing a temporary config
    # that the shared loader can parse
    if not tool_configs:
        return []

    # Use the shared config loader's tool resolution
    tools = []
    for tool_spec in tool_configs:
        try:
            tool = _resolve_single_tool(tool_spec)
            if tool is not None:
                tools.append(tool)
        except Exception as e:
            logger.error(f"Failed to resolve tool {tool_spec}: {e}")

    return tools


def _resolve_single_tool(tool_spec: dict[str, Any]) -> BaseTool | None:
    """Resolve a single tool specification."""
    import importlib

    if "factory" in tool_spec:
        # factory: module.path:function_name
        module_path, func_name = tool_spec["factory"].rsplit(":", 1)
        module = importlib.import_module(module_path)
        factory_fn = getattr(module, func_name)
        config = tool_spec.get("config", {})
        return factory_fn(config)

    elif "class" in tool_spec:
        # class: module.path:ClassName
        module_path, class_name = tool_spec["class"].rsplit(":", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        kwargs = {k: v for k, v in tool_spec.items() if k != "class"}
        return cls(**kwargs)

    elif "function" in tool_spec:
        # function: module.path:function_name
        module_path, func_name = tool_spec["function"].rsplit(":", 1)
        module = importlib.import_module(module_path)
        return getattr(module, func_name)

    else:
        logger.warning(f"Unknown tool spec format: {tool_spec}")
        return None


def create_deer_flow_agent(
    profile: DeerFlowAgentConfig,
    model_name: str | None = None,
    extra_tools: list[BaseTool] | None = None,
    checkpointer: Any | None = None,
) -> DeerFlowAgent:
    """Create a Deer-flow agent graph from a profile configuration.

    This is the main entry point. It:
    1. Sets up deer-flow path and config
    2. Creates the agent via deer-flow's make_lead_agent()
    3. Injects additional GenAI Blueprint tools

    Args:
        profile: DeerFlowAgentConfig with profile settings
        model_name: LLM model name override (uses GenAI Blueprint's current LLM if None)
        extra_tools: Additional BaseTool instances to inject
        checkpointer: LangGraph checkpointer for conversation memory

    Returns:
        A CompiledStateGraph (LangGraph agent) ready for .astream()
    """
    from genai_bp.deer_flow._path_setup import setup_deer_flow_path
    from genai_bp.deer_flow.config_bridge import setup_deer_flow_config

    # Step 1: Setup deer-flow path and config
    setup_deer_flow_path()
    setup_deer_flow_config(
        mcp_server_names=profile.mcp_servers or None,
        enabled_skills=profile.skills or None,
    )

    # Step 2: Resolve extra tools from profile config
    profile_tools = resolve_tools_from_config(profile.tool_configs)
    all_extra_tools = profile_tools + (extra_tools or [])

    # Step 3: Create the agent using deer-flow internals
    return _create_agent_internal(
        profile=profile,
        model_name=model_name,
        extra_tools=all_extra_tools,
        checkpointer=checkpointer,
    )


def _create_agent_internal(
    profile: DeerFlowAgentConfig,
    model_name: str | None,
    extra_tools: list[BaseTool],
    checkpointer: Any | None,
) -> DeerFlowAgent:
    """Internal: create deer-flow agent with proper imports.

    Separated from create_deer_flow_agent to isolate deer-flow imports
    (which require sys.path to be set up first).
    """
    # Now we can import deer-flow modules (path was set up by caller)
    from src.agents import make_lead_agent
    from src.config import get_app_config
    from src.config.app_config import reload_app_config

    # Reload config to pick up our generated files
    reload_app_config()

    # Determine model name
    if model_name is None:
        # Use genai-blueprint's currently selected model
        try:
            from genai_tk.core.llm_factory import get_llm

            llm = get_llm()
            model_name = _get_model_name_for_deer_flow(llm)
        except Exception:
            # Fall back to first available model in deer-flow config
            app_config = get_app_config()
            if app_config.models:
                model_name = app_config.models[0].name
            else:
                model_name = "default"

    # Apply mode settings (overrides profile defaults)
    thinking_enabled = profile.thinking_enabled
    is_plan_mode = profile.is_plan_mode
    subagent_enabled = profile.subagent_enabled

    # Mode-based configuration (matches deer-flow frontend logic)
    if profile.mode:
        mode = profile.mode.lower()
        if mode == "flash":
            thinking_enabled = False
            is_plan_mode = False
            subagent_enabled = False
        elif mode == "thinking":
            thinking_enabled = True
            is_plan_mode = False
            subagent_enabled = False
        elif mode == "pro":
            thinking_enabled = True
            is_plan_mode = True
            subagent_enabled = False
        elif mode == "ultra":
            thinking_enabled = True
            is_plan_mode = True
            subagent_enabled = True

    # Build RunnableConfig
    config = {
        "configurable": {
            "model_name": model_name,
            "thinking_enabled": thinking_enabled,
            "subagent_enabled": subagent_enabled,
            "is_plan_mode": is_plan_mode,
            "max_concurrent_subagents": 3,
        }
    }

    # Create the agent graph
    agent = make_lead_agent(config)

    # If we have extra tools, we need to recreate with the additional tools
    if extra_tools:
        agent = _create_agent_with_extra_tools(
            profile=profile,
            model_name=model_name,
            extra_tools=extra_tools,
            checkpointer=checkpointer,
            config=config,
        )

    return agent


def _get_model_name_for_deer_flow(llm: Any) -> str:
    """Extract a model name string from a GenAI Blueprint LLM instance.

    Tries to match the LLM's model name to one available in deer-flow's config.
    Falls back to the raw model name.
    """
    try:
        from src.config import get_app_config

        app_config = get_app_config()
        available = {m.name for m in app_config.models}

        # Try the model's name attribute
        model_name = getattr(llm, "model_name", None) or getattr(llm, "model", "default")

        # Check if it's directly available
        if model_name in available:
            return model_name

        # Return first available model as fallback
        if app_config.models:
            return app_config.models[0].name

    except Exception:
        pass

    return "default"


def _create_agent_with_extra_tools(
    profile: DeerFlowAgentConfig,
    model_name: str,
    extra_tools: list[BaseTool],
    checkpointer: Any | None,
    config: dict[str, Any],
) -> DeerFlowAgent:
    """Create a deer-flow agent with additional tools injected.

    Instead of using make_lead_agent (which has a fixed tool list), we replicate
    its logic but add our extra tools to the tool list.
    """
    from langchain.agents import create_agent
    from src.agents.lead_agent.prompt import apply_prompt_template
    from src.agents.thread_state import ThreadState
    from src.models import create_chat_model
    from src.tools import get_available_tools

    thinking_enabled = profile.thinking_enabled
    subagent_enabled = profile.subagent_enabled

    # Create model
    model = create_chat_model(name=model_name, thinking_enabled=thinking_enabled)

    # Get deer-flow tools + our extras
    try:
        deer_flow_tools = get_available_tools(
            model_name=model_name,
            subagent_enabled=subagent_enabled,
            groups=profile.tool_groups,
        )
    except ImportError as e:
        # Handle missing dependencies gracefully
        error_msg = str(e)
        logger.warning(f"Some deer-flow tools could not be loaded: {error_msg}")

        # Try to load tools individually, skipping ones that fail
        deer_flow_tools = []
        from langchain.tools import BaseTool
        from src.reflection.resolvers import resolve_variable
        from src.tools.tools import get_app_config

        config = get_app_config()
        for tool in config.tools:
            if profile.tool_groups is None or tool.group in profile.tool_groups:
                try:
                    resolved_tool = resolve_variable(tool.use, BaseTool)
                    deer_flow_tools.append(resolved_tool)
                except ImportError as tool_err:
                    logger.warning(f"Skipping tool {tool.name} ({tool.group}): {tool_err}")
                    continue

        logger.info(f"Loaded {len(deer_flow_tools)} deer-flow tools (some skipped)")

    all_tools = deer_flow_tools + extra_tools

    logger.info(
        f"Creating Deer-flow agent with {len(deer_flow_tools)} built-in tools "
        f"+ {len(extra_tools)} extra tools = {len(all_tools)} total"
    )

    # Build system prompt
    system_prompt = apply_prompt_template(
        subagent_enabled=subagent_enabled,
        max_concurrent_subagents=3,
    )
    if profile.system_prompt:
        system_prompt = system_prompt + "\n\n" + profile.system_prompt

    # Build middlewares (replicating make_lead_agent logic)
    from src.agents.lead_agent.agent import _build_middlewares

    middlewares = _build_middlewares(config)

    # Create the agent
    agent = create_agent(
        model=model,
        tools=all_tools,
        system_prompt=system_prompt,
        middleware=middlewares,
        state_schema=ThreadState,
        checkpointer=checkpointer,
    )

    return agent


def create_deer_flow_agent_simple(
    profile: DeerFlowAgentConfig,
    llm: Any | None = None,
    extra_tools: list[BaseTool] | None = None,
    checkpointer: Any | None = None,
    trace_middleware: Any | None = None,
) -> DeerFlowAgent:
    """Simplified agent creation using GenAI Blueprint's LLM directly.

    This bypasses Deer-flow's model factory entirely and uses the LLM
    instance from GenAI Blueprint. Useful when you want the Deer-flow
    agent architecture but with GenAI Blueprint's model management.

    Args:
        profile: Agent profile configuration
        llm: LangChain BaseChatModel instance (from get_llm()). Auto-creates if None.
        extra_tools: Additional tools to include
        checkpointer: LangGraph checkpointer
        trace_middleware: TraceMiddleware instance for Streamlit trace display

    Returns:
        A CompiledStateGraph ready for .astream()
    """
    from genai_blueprint.deer_flow._path_setup import setup_deer_flow_path
    from genai_blueprint.deer_flow.config_bridge import setup_deer_flow_config

    # Setup
    setup_deer_flow_path()
    setup_deer_flow_config(mcp_server_names=profile.mcp_servers or None)

    # Import deer-flow after path setup
    from langchain.agents import create_agent
    from src.config.app_config import reload_app_config
    from src.tools import get_available_tools

    reload_app_config()

    # Get LLM
    if llm is None:
        from genai_tk.core.llm_factory import get_llm

        llm = get_llm()

    # Resolve extra tools from profile config
    profile_tools = resolve_tools_from_config(profile.tool_configs)
    all_extra_tools = profile_tools + (extra_tools or [])

    # Get deer-flow's built-in tools (web_search, web_fetch, etc.)
    # Filter by tool_groups to avoid loading tools with missing dependencies
    try:
        deer_flow_tools = get_available_tools(
            subagent_enabled=profile.subagent_enabled,
            groups=profile.tool_groups,
        )
    except ImportError as e:
        # Handle missing dependencies gracefully
        error_msg = str(e)
        logger.warning(f"Some deer-flow tools could not be loaded: {error_msg}")

        if "readabilipy" in error_msg:
            logger.info("To enable web_fetch tool with jina_ai, install: pip install readabilipy")

        # Retry without any tool groups to get at least the basic tools that work
        logger.info("Retrying with fallback tool loading...")
        try:
            # Try to get tools without group filtering - deer-flow will load what it can
            deer_flow_tools = []
            from src.tools.tools import get_app_config

            config = get_app_config()
            # Manually load only tools that don't fail
            from langchain.tools import BaseTool
            from src.reflection.resolvers import resolve_variable

            for tool in config.tools:
                if profile.tool_groups is None or tool.group in profile.tool_groups:
                    try:
                        resolved_tool = resolve_variable(tool.use, BaseTool)
                        deer_flow_tools.append(resolved_tool)
                    except ImportError as tool_err:
                        logger.warning(f"Skipping tool {tool.name} ({tool.group}): {tool_err}")
                        continue

            logger.info(f"Loaded {len(deer_flow_tools)} deer-flow tools (some skipped due to missing dependencies)")
        except Exception as retry_err:
            logger.error(f"Could not load deer-flow tools: {retry_err}")
            deer_flow_tools = []

    all_tools = deer_flow_tools + all_extra_tools
    logger.info(f"Deer-flow agent tools: {len(deer_flow_tools)} built-in + {len(all_extra_tools)} extra")

    # Build system prompt
    try:
        from src.agents.lead_agent.prompt import apply_prompt_template

        system_prompt = apply_prompt_template(
            subagent_enabled=profile.subagent_enabled,
            max_concurrent_subagents=3,
        )
    except Exception:
        system_prompt = "You are a helpful AI assistant. Use available tools to answer questions."

    if profile.system_prompt:
        system_prompt = system_prompt + "\n\n" + profile.system_prompt

    # Build middleware list
    middlewares = []
    if trace_middleware is not None:
        middlewares.append(trace_middleware)

    # Create agent
    agent = create_agent(
        model=llm,
        tools=all_tools,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        middleware=middlewares,
    )

    return agent


async def run_deer_flow_agent(
    agent: DeerFlowAgent,
    user_input: str,
    thread_id: str,
    on_node: Callable[[str], None] | None = None,
    on_content: Callable[[str, str], None] | None = None,
) -> str:
    """Run a Deer-flow agent with streaming support.

    Reusable async function for executing Deer-flow agents with optional callbacks
    for streaming progress updates. Used by both CLI and Streamlit interfaces.

    Args:
        agent: Compiled Deer-flow agent graph
        user_input: User's query or message
        thread_id: Thread ID for conversation memory
        on_node: Optional callback called when entering a new node (receives node_name)
        on_content: Optional callback called when agent generates content (receives node_name, content)

    Returns:
        The final agent response as a string

    Example:
        >>> async def node_handler(node):
        ...     print(f"Processing: {node}")
        >>> response = await run_deer_flow_agent(agent, "Hello", "thread-1", on_node=node_handler)
    """
    from langchain_core.messages import AIMessage, HumanMessage

    config = {"configurable": {"thread_id": thread_id}}
    inputs = {"messages": [HumanMessage(content=user_input)]}
    response_content = ""
    final_response = None

    async for step in agent.astream(inputs, config):
        # Handle tuple steps
        if isinstance(step, tuple):
            step = step[1]

        if isinstance(step, dict):
            for node, update in step.items():
                # Notify caller of node transition
                if on_node:
                    on_node(node)

                if "messages" in update and update["messages"]:
                    latest = update["messages"][-1]
                    if isinstance(latest, AIMessage) and latest.content:
                        response_content = latest.content
                        final_response = latest

                        # Notify caller of new content
                        if on_content:
                            on_content(node, str(latest.content))

    # Return final content
    if final_response and final_response.content:
        return str(final_response.content)
    elif response_content:
        return response_content
    else:
        return "I couldn't generate a response. Please try again."
