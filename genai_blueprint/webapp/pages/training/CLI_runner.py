"""Streamlit page to interact with Typer CLI commands.

Provides a simple interface to:
- Select from example CLI commands
- Edit and execute them using Typer's CliRunner
- Display command output
"""

import shlex

import streamlit as st
from genai_tk.main.cli import cli_app, load_and_register_commands
from genai_tk.utils.config_mngr import global_config
from typer.testing import CliRunner


def load_cli_examples() -> list[dict]:
    """Load CLI command examples from YAML config."""
    return global_config().merge_with("config/demos/cli_examples.yaml").get_list("cli_commands")


@st.cache_resource()
def get_cli_runner() -> CliRunner:
    """Create and configure CLI runner with registered commands."""
    runner = CliRunner()
    load_and_register_commands(cli_app)
    return runner


def run_typer_command(command: str) -> str:
    args = shlex.split(command)
    result = get_cli_runner().invoke(cli_app, args)

    if result.exit_code != 0:
        return f"Error: {result.exception}\n{result.output}"
    return result.output


def main() -> None:
    """Main Streamlit page layout and interaction."""
    st.title("Command Line Interface Runner")

    # Load command examples
    examples = load_cli_examples()

    # Command selection UI
    col1, col2 = st.columns([1, 3])

    with col1:
        selected_command = st.selectbox(
            "Example Command",
            options=[cmd["name"] for cmd in examples],
            format_func=lambda x: x,
        )

    with col2:
        # Get the selected command text
        command_text = next(cmd["command"] for cmd in examples if cmd["name"] == selected_command)

        # Command editor
        command = st.text_area(
            "Command to execute",
            value=command_text,
            height=100,
        )

    # Execute button
    if st.button("Run Command"):
        with st.spinner("Executing command..."):
            try:
                output = run_typer_command(command)
                st.code(output, language="text")
            except Exception as e:
                st.error(f"Command failed: {str(e)}")
                logger.error(f"Command execution error: {e}")


if __name__ == "__main__":
    main()
