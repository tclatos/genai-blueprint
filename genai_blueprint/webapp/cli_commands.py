"""CLI commands for basic authentication management.

This module provides command-line interface commands for:
- Hashing passwords for authentication

"""

from typing import Annotated

import typer


def register_commands(cli_app: typer.Typer) -> None:
    # Create auth sub-app
    auth_app = typer.Typer(no_args_is_help=True, help="Authentication commands.")

    @auth_app.command("hash-password")
    def hash_password_cmd(
        password: Annotated[str, typer.Argument(help="Password to hash")],
    ) -> None:
        """
        Hash a password for use in the authentication config.

        The hashed password can be added to the auth.yaml file.
        """
        from genai_tk.utils.basic_auth import hash_password

        hashed = hash_password(password)
        print(f"Hashed password: {hashed}")

    # Mount auth app on root app
    cli_app.add_typer(auth_app, name="auth")
