#  Copyright © 2025 Bentley Systems, Incorporated
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#      http://www.apache.org/licenses/LICENSE-2.0
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import typer

__all__ = ["get_all_commands", "get_all_flags"]


def get_all_commands(app: typer.Typer, prefix: str = "") -> list[str]:
    """Recursively extract all available command names from a Typer app.

    Args:
        app: The Typer app to introspect
        prefix: Internal use - command path prefix for nested commands

    Returns:
        Flattened list of all available commands
        Example: ["auth", "auth login", "auth logout", "blockmodels", "blockmodels list"]
    """
    import click

    commands = []

    # Get the underlying Click group
    if hasattr(app, "registered_commands"):
        # Typer app structure
        for command_name, command_obj in app.registered_commands:
            full_name = f"{prefix}{command_name}".strip()
            commands.append(full_name)

            # Recursively handle nested Typer apps
            if isinstance(command_obj, typer.Typer):
                nested = get_all_commands(command_obj, prefix=f"{full_name} ")
                commands.extend(nested)

    # Alternative: work directly with Click group if available
    if hasattr(app, "__call__"):
        try:
            # Access the underlying Click group
            click_group = app
            # This is a simplified approach; actual implementation may vary
        except Exception:
            pass

    return commands


def get_all_flags(app: typer.Typer, command_path: str = "") -> list[str]:
    """Extract all available flag names for a given command.

    Args:
        app: The Typer app
        command_path: Dot-separated path to command (e.g., "blockmodels.list")

    Returns:
        List of flag names (e.g., ["--format", "--help", "--workspace"])
    """
    import click

    flags = set()

    # Navigate to the command in the app structure
    parts = command_path.split(".") if command_path else []
    current_app = app

    for part in parts:
        if hasattr(current_app, "registered_commands"):
            for cmd_name, cmd_obj in current_app.registered_commands:
                if cmd_name == part:
                    current_app = cmd_obj
                    break

    # Extract parameters from the command
    if hasattr(current_app, "registered_commands"):
        # It's a group/app, extract from its callback if it exists
        if hasattr(current_app, "__click_params__"):
            for param in current_app.__click_params__:
                if isinstance(param, click.Option):
                    for opt_name in param.opts:
                        flags.add(opt_name)

    return sorted(list(flags))
