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

import json
import re
import sys
from typing import Any, Optional

import click
import typer
from typer.core import TyperGroup

from evo.cli import useragent
from evo.cli._lazy import lazy_commands
from evo.cli.output import OutputFormat
from evo.cli.output import init as init_output

# (name, dotted module path exposing `app`, short help, hidden). Short help text is
# duplicated from each module's `typer.Typer(help=...)` declaration so that `evo --help`
# never has to import subcommand modules just to render the top-level command list.
_LAZY_SUBCOMMANDS: list[tuple[str, str, str, bool]] = [
    (
        "admin",
        "evo.cli.admin",
        "Manage instance-level users, invitations, roles, and cross-workspace admin views.",
        False,
    ),
    ("agent", "evo.cli.agent", "AI agent utilities — machine-readable schema and discovery.", False),
    ("auth", "evo.cli.auth", "Authenticate with Seequent Evo.", False),
    ("blockmodels", "evo.cli.blockmodels", "Manage block models.", False),
    ("blockmodel", "evo.cli.blockmodels", "Manage block models.", True),
    ("compute", "evo.cli.compute", "Submit and manage compute tasks (jobs).", False),
    ("files", "evo.cli.files", "Manage files.", False),
    ("file", "evo.cli.files", "Manage files.", True),
    ("instances", "evo.cli.instance", "Discover and select the Evo organization/hub to work with.", False),
    ("instance", "evo.cli.instance", "Discover and select the Evo organization/hub to work with.", True),
    ("objects", "evo.cli.objects", "Manage geoscience objects.", False),
    ("object", "evo.cli.objects", "Manage geoscience objects.", True),
    ("workspaces", "evo.cli.workspace", "List and inspect Evo workspaces.", False),
    ("workspace", "evo.cli.workspace", "List and inspect Evo workspaces.", True),
]


class LazyTyperGroup(TyperGroup):
    """Root command group that registers all subcommands as `LazySubcommand` stubs."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.commands.update(lazy_commands(_LAZY_SUBCOMMANDS))


app = typer.Typer(
    name="evo",
    cls=LazyTyperGroup,
    help=(
        "Seequent Evo CLI — LLM-first interface to the Evo platform.\n\n"
        "AI agents: run `evo agent schema` for a machine-readable JSON command reference."
    ),
    no_args_is_help=True,
)


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


def _emit_agent_usage_error(e: Any) -> None:
    """Emit a Click/Typer UsageError as JSON to stderr for agent mode consumers."""
    message = e.format_message()
    suggestions: list[str] = []
    m = re.search(r"Did you mean ['\"](.+?)['\"]", message)
    if m:
        suggestions.append(m.group(1))
    clean_message = re.sub(r"[.!]?\s*Did you mean ['\"].+?['\"][.!?]?\s*$", "", message).strip()
    payload: dict[str, Any] = {"error": clean_message}
    if suggestions:
        payload["suggestions"] = suggestions
    typer.echo(json.dumps(payload, indent=2), file=sys.stderr)
    sys.exit(e.exit_code)


def _is_usage_error(e: BaseException) -> bool:
    """True for Click/Typer UsageError regardless of which vendored Click module raised it."""
    return type(e).__name__ == "UsageError" and hasattr(e, "format_message") and hasattr(e, "exit_code")


def main() -> None:
    # Intercept --help in agent mode before Typer processes it
    _handle_agent_help()

    if not useragent.is_agent_mode():
        app()
        return

    # Agent mode: use standalone_mode=False so Click re-raises UsageError instead of
    # rendering it as a Rich panel, letting us emit structured JSON to stderr.
    # NOTE: Typer vendors its own Click copy in typer._click, so we duck-type check
    # rather than isinstance-check against click.exceptions.UsageError.
    try:
        result = app(standalone_mode=False)
        if result:
            sys.exit(result)
    except (KeyboardInterrupt, click.exceptions.Abort):
        sys.exit(1)
    except BaseException as e:
        if _is_usage_error(e):
            _emit_agent_usage_error(e)
        raise


if __name__ == "__main__":
    main()
