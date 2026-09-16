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

import sys
from typing import Optional

import click
import typer

from evo.cli import output, suggestions, useragent
from evo.cli.admin import app as admin_app
from evo.cli.agent import app as agent_app
from evo.cli.auth import app as auth_app
from evo.cli.blockmodels import app as blockmodels_app
from evo.cli.compute import app as compute_app
from evo.cli.files import app as files_app
from evo.cli.instance import app as instance_app
from evo.cli.objects import app as objects_app
from evo.cli.output import OutputFormat
from evo.cli.output import init as init_output
from evo.cli.workspace import app as workspace_app

app = typer.Typer(
    name="evo",
    help=(
        "Seequent Evo CLI — LLM-first interface to the Evo platform.\n\n"
        "AI agents: run `evo agent schema` for a machine-readable JSON command reference."
    ),
    no_args_is_help=True,
)

app.add_typer(admin_app, name="admin")
app.add_typer(agent_app, name="agent")
app.add_typer(auth_app, name="auth")
app.add_typer(blockmodels_app, name="blockmodels")
app.add_typer(blockmodels_app, name="blockmodel", hidden=True)
app.add_typer(compute_app, name="compute")
app.add_typer(files_app, name="files")
app.add_typer(files_app, name="file", hidden=True)
app.add_typer(instance_app, name="instances")
app.add_typer(instance_app, name="instance", hidden=True)
app.add_typer(objects_app, name="objects")
app.add_typer(objects_app, name="object", hidden=True)
app.add_typer(workspace_app, name="workspaces")
app.add_typer(workspace_app, name="workspace", hidden=True)


@app.callback()
def callback(
    format: Optional[OutputFormat] = typer.Option(
        None,
        "--format",
        help="Output format. Overrides EVO_CLI_AGENT_MODE. [plain, json]",
        show_default=False,
    ),
) -> None:
    init_output(format)


def _get_available_commands() -> list[str]:
    """Get all top-level command names for suggestion matching."""
    return [
        "admin",
        "agent",
        "auth",
        "blockmodels",
        "blockmodel",
        "compute",
        "files",
        "file",
        "instances",
        "instance",
        "objects",
        "object",
        "workspaces",
        "workspace",
    ]


def _handle_unknown_command(error: click.exceptions.NoSuchCommand) -> None:
    """Handle unknown command with suggestion."""
    invalid_cmd = error.cmd_name
    available_commands = _get_available_commands()
    suggestion = suggestions.suggest_command(invalid_cmd, available_commands)

    output.emit_error(
        f"Unknown command: {invalid_cmd!r}",
        code="unknown_command",
        suggestions=[suggestion] if suggestion else None,
    )


def _handle_unknown_option(error: click.exceptions.NoSuchOption) -> None:
    """Handle unknown option with suggestion."""
    invalid_opt = error.option_name
    # For now, we don't have context-aware flag suggestions without a complex Click traversal
    # This is a simple fallback that could be enhanced with more sophisticated introspection
    common_flags = ["--format", "--help", "--workspace", "--org"]
    suggestion = suggestions.suggest_flag(invalid_opt, common_flags)

    output.emit_error(
        f"Unknown option: {invalid_opt!r}",
        code="unknown_option",
        suggestions=[suggestion] if suggestion else None,
    )


def _handle_agent_help() -> None:
    """If agent mode and --help requested, substitute schema for help (pup-style).

    In agent mode, --help should return JSON schema, not text help. Intercept before
    Typer processes args so agents can naturally discover the CLI via --help.

    Examples:
      evo --help (agent mode) → full schema
      evo blockmodels --help (agent mode) → blockmodels schema only
    """
    # Check if --help or -h is in args AND we're in agent mode
    help_requested = "--help" in sys.argv or "-h" in sys.argv
    if not help_requested or not useragent.is_agent_mode():
        return

    # Build equivalent `evo agent schema` command by substituting --help with schema args
    # e.g. "evo blockmodels --help" becomes "evo agent schema --command blockmodels"
    args_without_help = [arg for arg in sys.argv[1:] if arg not in ("--help", "-h")]

    # Build new args for schema command
    new_args = ["agent", "schema"]
    if args_without_help:
        command_path = ".".join(args_without_help)
        new_args.extend(["--command", command_path])

    # Replace sys.argv and let Typer run normally (which will execute `evo agent schema ...`)
    sys.argv = ["evo"] + new_args


def main() -> None:
    # Intercept --help in agent mode before Typer processes it
    _handle_agent_help()
    try:
        app()
    except click.exceptions.NoSuchCommand as e:
        _handle_unknown_command(e)
    except click.exceptions.NoSuchOption as e:
        _handle_unknown_option(e)


if __name__ == "__main__":
    main()
