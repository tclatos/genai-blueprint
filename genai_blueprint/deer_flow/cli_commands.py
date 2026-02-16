"""CLI commands for Deer-flow agents.

Provides command-line interface for running Deer-flow agents with profile-based
configuration, chat mode, streaming, and LLM/MCP customization.
"""

import asyncio
import sys
import uuid
import webbrowser
from pathlib import Path
from typing import Annotated, Optional

import typer
from genai_tk.core.llm_factory import LlmFactory, get_llm
from genai_tk.main.cli import CliTopCommand
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from pydantic import BaseModel
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


class DeerFlowCommands(CliTopCommand, BaseModel):
    """CLI commands for Deer-flow agents."""

    description: str = "Deer-flow agent commands for interactive AI with advanced reasoning"

    def get_description(self) -> tuple[str, str]:
        """Return command name and description for CLI registration."""
        return "deerflow", self.description

    def register_sub_commands(self, cli_app: typer.Typer) -> None:
        """Register Deer-flow CLI subcommands."""

        @cli_app.callback(invoke_without_command=True)
        def main(
            ctx: typer.Context,
            input_text: Annotated[
                Optional[str],
                typer.Argument(help="User query text (positional). If omitted, reads from stdin or uses --chat mode."),
            ] = None,
            profile: Annotated[
                Optional[str],
                typer.Option(
                    "--profile",
                    "-p",
                    help="Profile name from deerflow.yaml (required unless --list)",
                ),
            ] = None,
            chat: Annotated[
                bool,
                typer.Option(
                    "--chat",
                    "-s",
                    help="Interactive multi-turn chat mode (REPL). Use /quit to exit.",
                ),
            ] = False,
            llm: Annotated[
                Optional[str],
                typer.Option(
                    "--llm",
                    "-m",
                    help="LLM model override (e.g., 'gpt_41_openrouter', 'ollama/llama3.2')",
                ),
            ] = None,
            mcp: Annotated[
                list[str],
                typer.Option(
                    "--mcp",
                    help="Additional MCP server names to enable (merged with profile's list)",
                ),
            ] = [],
            mode: Annotated[
                Optional[str],
                typer.Option(
                    "--mode",
                    help="Override agent mode: flash|thinking|pro|ultra",
                ),
            ] = None,
            stream: Annotated[
                bool,
                typer.Option(
                    "--stream",
                    help="Stream intermediate agent steps in real-time",
                ),
            ] = False,
            list_profiles: Annotated[
                bool,
                typer.Option(
                    "--list",
                    help="List available profiles from deerflow.yaml and exit",
                ),
            ] = False,
            config: Annotated[
                Optional[str],
                typer.Option(
                    "--config",
                    "-c",
                    help="Path to deerflow.yaml config file",
                ),
            ] = None,
        ) -> None:
            """Run Deer-flow agents with advanced reasoning capabilities.

            Examples:
                # List available profiles
                cli deerflow --list

                # Run with a profile
                cli deerflow -p "Research Assistant" "Explain quantum computing"

                # Interactive chat mode
                cli deerflow -p "Research Assistant" --chat

                # With LLM override
                cli deerflow -p "Coder" --llm gpt_41_openrouter "Write a sorting algorithm"

                # Stream intermediate steps
                cli deerflow -p "Research Assistant" --stream "What are AI trends?"

                # Add extra MCP servers
                cli deerflow -p "Coder" --mcp math --mcp weather "Calculate weather patterns"

                # Override mode
                cli deerflow -p "Web Browser" --mode ultra "Research topic"

                # Read from stdin
                echo "What is RAG?" | cli deerflow -p "Research Assistant"
            """
            config_path = config or "config/agents/deerflow.yaml"

            # Handle --list flag
            if list_profiles:
                _list_profiles(config_path)
                return

            # Validate profile requirement
            if not profile:
                console.print(
                    "[red]Error:[/red] --profile/-p is required (or use --list to see available profiles)",
                    style="bold",
                )
                raise typer.Exit(1)

            # Get input from stdin if not provided
            if not input_text and not chat:
                if not sys.stdin.isatty():
                    input_text = sys.stdin.read().strip()
                    if not input_text:
                        console.print("[red]Error:[/red] No input provided", style="bold")
                        raise typer.Exit(1)
                else:
                    console.print(
                        "[yellow]Warning:[/yellow] No input provided. Use positional argument, stdin, or --chat mode.",
                        style="bold",
                    )
                    raise typer.Exit(1)

            # Run agent
            try:
                if chat:
                    asyncio.run(
                        _run_chat_mode(
                            profile_name=profile,
                            config_path=config_path,
                            llm_override=llm,
                            extra_mcp=mcp,
                            mode_override=mode,
                            stream_enabled=stream,
                        )
                    )
                else:
                    asyncio.run(
                        _run_single_shot(
                            profile_name=profile,
                            user_input=input_text,
                            config_path=config_path,
                            llm_override=llm,
                            extra_mcp=mcp,
                            mode_override=mode,
                            stream_enabled=stream,
                        )
                    )
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted by user[/yellow]")
                raise typer.Exit(0) from None
            except Exception as e:
                console.print(f"\n[red]Error:[/red] {e}", style="bold")
                logger.exception("Deer-flow agent error")
                raise typer.Exit(1) from e


def _list_profiles(config_path: str) -> None:
    """List available Deer-flow profiles in a Rich table."""
    from genai_bp.deer_flow.agent import load_deer_flow_profiles

    try:
        profiles = load_deer_flow_profiles(config_path)
    except Exception as e:
        console.print(f"[red]Error loading profiles:[/red] {e}", style="bold")
        raise typer.Exit(1) from e

    if not profiles:
        console.print(f"[yellow]No profiles found in {config_path}[/yellow]")
        return

    table = Table(title=f"🦌 Deer-flow Profiles ({config_path})")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Mode", style="magenta")
    table.add_column("Tool Groups", style="green")
    table.add_column("MCP Servers", style="blue")
    table.add_column("Skills", style="yellow")

    for profile in profiles:
        tool_groups = ", ".join(profile.tool_groups) if profile.tool_groups else "-"
        mcp_servers = ", ".join(profile.mcp_servers) if profile.mcp_servers else "-"
        skills = ", ".join(profile.skills) if profile.skills else "-"

        table.add_row(
            profile.name,
            profile.mode or "flash",
            tool_groups,
            mcp_servers,
            skills,
        )

    console.print(table)


async def _run_single_shot(
    profile_name: str,
    user_input: str,
    config_path: str,
    llm_override: Optional[str],
    extra_mcp: list[str],
    mode_override: Optional[str],
    stream_enabled: bool,
) -> None:
    """Execute a single query (non-interactive mode)."""
    from genai_bp.deer_flow.agent import (
        create_deer_flow_agent_simple,
        load_deer_flow_profiles,
        run_deer_flow_agent,
    )

    # Load profile
    profiles = load_deer_flow_profiles(config_path)
    profile_dict = next((p for p in profiles if p.name == profile_name), None)

    if not profile_dict:
        console.print(
            f"[red]Error:[/red] Profile '{profile_name}' not found in {config_path}",
            style="bold",
        )
        console.print("[yellow]Available profiles:[/yellow]")
        for p in profiles:
            console.print(f"  - {p.name}")
        raise typer.Exit(1)

    # Apply overrides
    if mode_override:
        profile_dict.mode = mode_override

    if extra_mcp:
        profile_dict.mcp_servers = list(set(profile_dict.mcp_servers + extra_mcp))

    # Get LLM
    if llm_override:
        try:
            llm_id = LlmFactory.resolve_llm_identifier(llm_override)
            llm = LlmFactory.create_llm(llm_id)
        except Exception as e:
            console.print(f"[red]Error resolving LLM '{llm_override}':[/red] {e}", style="bold")
            raise typer.Exit(1)
    else:
        llm = get_llm()

    # Show configuration
    console.print(f"[cyan]Profile:[/cyan] {profile_dict.name}")
    console.print(f"[cyan]Mode:[/cyan] {profile_dict.mode}")
    console.print(f"[cyan]LLM:[/cyan] {getattr(llm, 'model_name', getattr(llm, 'model', 'unknown'))}")
    if profile_dict.mcp_servers:
        console.print(f"[cyan]MCP Servers:[/cyan] {', '.join(profile_dict.mcp_servers)}")
    console.print()

    # Create agent
    with console.status("🦌 Setting up Deer-flow agent...", spinner="dots"):
        checkpointer = MemorySaver()
        agent = create_deer_flow_agent_simple(
            profile=profile_dict,
            llm=llm,
            checkpointer=checkpointer,
        )

    thread_id = str(uuid.uuid4())

    # Execute with streaming or non-streaming
    if stream_enabled:
        current_node = None

        def on_node(node: str) -> None:
            nonlocal current_node
            if node != current_node:
                current_node = node
                console.print(f"[dim]→ {node}[/dim]")

        def on_content(node: str, content: str) -> None:
            # We'll just rely on the final result for now
            pass

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("🦌 Agent thinking...", total=None)
            response = await run_deer_flow_agent(
                agent=agent,
                user_input=user_input,
                thread_id=thread_id,
                on_node=on_node,
                on_content=on_content,
            )
            progress.update(task, description="✅ Complete")
    else:
        with console.status("🦌 Agent thinking...", spinner="dots"):
            response = await run_deer_flow_agent(
                agent=agent,
                user_input=user_input,
                thread_id=thread_id,
            )

    # Display result
    console.print()
    panel = Panel(
        Markdown(response),
        title="🦌 Deer-flow Response",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


async def _run_chat_mode(
    profile_name: str,
    config_path: str,
    llm_override: Optional[str],
    extra_mcp: list[str],
    mode_override: Optional[str],
    stream_enabled: bool,
) -> None:
    """Run interactive chat REPL mode."""
    from genai_bp.deer_flow.agent import (
        create_deer_flow_agent_simple,
        load_deer_flow_profiles,
        run_deer_flow_agent,
    )

    # Load profile
    profiles = load_deer_flow_profiles(config_path)
    profile_dict = next((p for p in profiles if p.name == profile_name), None)

    if not profile_dict:
        console.print(
            f"[red]Error:[/red] Profile '{profile_name}' not found in {config_path}",
            style="bold",
        )
        raise typer.Exit(1)

    # Apply overrides
    if mode_override:
        profile_dict.mode = mode_override

    if extra_mcp:
        profile_dict.mcp_servers = list(set(profile_dict.mcp_servers + extra_mcp))

    # Get LLM
    if llm_override:
        try:
            llm_id = LlmFactory.resolve_llm_identifier(llm_override)
            llm = LlmFactory.create(llm_id)
        except Exception as e:
            console.print(f"[red]Error resolving LLM '{llm_override}':[/red] {e}", style="bold")
            raise typer.Exit(1) from e
    else:
        llm = get_llm()

    # Show configuration
    console.print(Panel.fit("🦌 Deer-flow Interactive Chat", style="bold cyan"))
    console.print(f"[cyan]Profile:[/cyan] {profile_dict.name}")
    console.print(f"[cyan]Mode:[/cyan] {profile_dict.mode}")
    console.print(f"[cyan]LLM:[/cyan] {getattr(llm, 'model_name', getattr(llm, 'model', 'unknown'))}")
    if profile_dict.mcp_servers:
        console.print(f"[cyan]MCP Servers:[/cyan] {', '.join(profile_dict.mcp_servers)}")
    console.print()
    console.print("[dim]Commands: /quit, /exit, /clear, /help, /trace[/dim]")
    console.print("[dim]Use up/down arrows to navigate prompt history[/dim]")
    console.print()

    # Create agent (reused across turns)
    with console.status("🦌 Setting up Deer-flow agent...", spinner="dots"):
        checkpointer = MemorySaver()
        agent = create_deer_flow_agent_simple(
            profile=profile_dict,
            llm=llm,
            checkpointer=checkpointer,
        )

    thread_id = str(uuid.uuid4())

    # Set up prompt history
    history_file = Path(".deerflow.input.history")
    session = PromptSession(history=FileHistory(str(history_file)))

    # Chat loop
    try:
        while True:
            try:
                # Get user input with prompt_toolkit
                with patch_stdout():
                    prompt_style = Style.from_dict({"prompt": "bold green"})
                    user_input = await session.prompt_async(
                        ">>> ", style=prompt_style, auto_suggest=AutoSuggestFromHistory()
                    )

                user_input = user_input.strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.lower() in ["/quit", "/exit", "/q"]:
                    console.print("\n[bold yellow]Goodbye! 👋[/bold yellow]")
                    break
                elif user_input == "/clear":
                    thread_id = str(uuid.uuid4())
                    console.print("[yellow]Conversation cleared[/yellow]")
                    continue
                elif user_input == "/help":
                    console.print(
                        Panel(
                            "/help   – show this help\n"
                            "/quit   – exit chat mode\n"
                            "/clear  – clear conversation history\n"
                            "/trace  – open LangSmith trace in browser",
                            title="[bold cyan]Commands[/bold cyan]",
                            border_style="cyan",
                        )
                    )
                    continue
                elif user_input == "/trace":
                    webbrowser.open("https://smith.langchain.com/")
                    continue
                elif user_input.startswith("/"):
                    console.print(f"[yellow]Unknown command: {user_input}[/yellow]")
                    continue

                # Display user input
                console.print(Panel(user_input, title="[bold blue]User[/bold blue]", border_style="blue"))

                # Display user input
                console.print(Panel(user_input, title="[bold blue]User[/bold blue]", border_style="blue"))

                # Execute agent
                if stream_enabled:
                    current_node = None

                    def on_node(node: str) -> None:
                        nonlocal current_node
                        if node != current_node:
                            current_node = node
                            console.print(f"[dim]→ {node}[/dim]")

                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console,
                    ) as progress:
                        task = progress.add_task("🦌 Agent thinking...", total=None)
                        response = await run_deer_flow_agent(
                            agent=agent,
                            user_input=user_input,
                            thread_id=thread_id,
                            on_node=on_node,
                        )
                        progress.update(task, description="✅ Complete")
                else:
                    with console.status("🦌 Agent thinking...", spinner="dots"):
                        response = await run_deer_flow_agent(
                            agent=agent,
                            user_input=user_input,
                            thread_id=thread_id,
                        )

                # Display response
                console.print()
                console.print(
                    Panel(
                        Markdown(response),
                        title="[bold white on royal_blue1] Assistant [/bold white on royal_blue1]",
                        border_style="royal_blue1",
                    )
                )
                console.print()  # Add spacing

            except KeyboardInterrupt:
                console.print("\n[bold yellow]Received keyboard interrupt. Use /quit to exit.[/bold yellow]")
                continue
            except Exception as e:
                console.print(
                    Panel(
                        f"[red]Error: {e}[/red]",
                        title="[bold red]Error[/bold red]",
                        border_style="red",
                    )
                )
                logger.exception("Agent execution error")

    except KeyboardInterrupt:
        console.print("\n[bold yellow]Goodbye! 👋[/bold yellow]")
