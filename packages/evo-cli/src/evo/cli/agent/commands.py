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

"""AI agent utilities — machine-readable schema and discovery."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import click
import typer
from typer.core import TyperArgument, TyperOption

from evo.cli import __version__
from evo.cli import useragent
from evo.cli.auth.token_store import load_credentials
from evo.cli.state import load_selection

app = typer.Typer(help="AI agent utilities — machine-readable schema and discovery.")


def _agent_source() -> str:
    """Return the source that enabled agent mode (for diagnostics)."""
    if os.environ.get("EVO_FORCE_AGENT_MODE", "").lower() in ("1", "true", "yes"):
        return "EVO_FORCE_AGENT_MODE"
    if os.environ.get("EVO_NO_AGENT_MODE", "").lower() in ("1", "true", "yes"):
        return "EVO_NO_AGENT_MODE"
    if os.environ.get("EVO_CLI_AGENT_MODE", "").lower() in ("1", "true", "yes"):
        return "EVO_CLI_AGENT_MODE"
    info = useragent.detect_agent_info()
    if info.detected:
        return "auto-detected"
    return "none"


@app.command()
def info() -> None:
    """Output current agent context as JSON: detected agent, auth status, and active selection.

    Run this at the start of a session to orient yourself before issuing other commands.
    """
    agent_info = useragent.detect_agent_info()
    source = _agent_source()
    active = useragent.is_agent_mode()

    result: dict[str, Any] = {
        "agent_mode": active,
        "agent": agent_info.name or None,
        "agent_source": source,
    }

    creds = load_credentials()
    if creds is None:
        result["auth"] = {"logged_in": False}
    else:
        result["auth"] = {
            "logged_in": True,
            "token_expired": creds.token.is_expired,
            "org_id": str(creds.org_id),
            "org_name": creds.org_name,
            "hub_url": creds.hub_url,
            "hub_code": creds.hub_code,
        }

    sel = load_selection()
    if sel.org_id is not None or sel.workspace_id is not None:
        result["selection"] = {
            "org_id": str(sel.org_id) if sel.org_id else None,
            "org_name": sel.org_name,
            "hub_code": sel.hub_code,
            "hub_url": sel.hub_url,
            "hub_display_name": sel.hub_display_name,
            "workspace_id": str(sel.workspace_id) if sel.workspace_id else None,
            "workspace_name": sel.workspace_name,
        }
    else:
        result["selection"] = None

    typer.echo(json.dumps(result, indent=2))

# Params injected by the root callback or Click itself; exclude from per-command schema.
_SKIP_PARAMS = {"help", "format"}


def _type_info(param: click.Parameter) -> dict[str, Any]:
    """Extract type information from a Click parameter."""
    t = param.type
    if isinstance(t, click.Choice):
        return {"type": "string", "choices": list(t.choices)}
    if isinstance(t, click.types.IntParamType):
        return {"type": "integer"}
    if isinstance(t, click.types.FloatParamType):
        return {"type": "float"}
    if isinstance(t, click.types.BoolParamType):
        return {"type": "boolean"}
    if isinstance(t, click.types.UUIDParameterType):
        return {"type": "uuid"}
    return {"type": t.name or "string"}


def _option_schema(opt: click.Option, *, compact: bool) -> dict[str, Any]:
    node: dict[str, Any] = {"flags": list(opt.opts)}
    if opt.is_flag:
        node["type"] = "boolean"
    else:
        node.update(_type_info(opt))
    if not compact:
        node["required"] = opt.required
        node["multiple"] = bool(opt.multiple)
        if opt.default is not None and not opt.is_flag:
            node["default"] = opt.default
        if opt.help:
            node["description"] = opt.help.strip()
    return node


def _argument_schema(arg: click.Argument, *, compact: bool) -> dict[str, Any]:
    node: dict[str, Any] = {"name": arg.name}
    node.update(_type_info(arg))
    if not compact:
        node["required"] = arg.required
    return node


def _is_group(cmd: click.BaseCommand) -> bool:
    """True if the command is a group/multi-command (has subcommands)."""
    return hasattr(cmd, "list_commands") and hasattr(cmd, "get_command")


def _resolve_command(root: click.BaseCommand, path: str) -> tuple[click.BaseCommand, str] | None:
    """Walk a dot-separated command path (e.g. 'blockmodels.versions') from root.

    Returns (command, final_name) or None if any segment is not found.
    """
    parts = path.strip().split(".")
    cmd: click.BaseCommand = root
    name = parts[-1]
    for part in parts:
        if not _is_group(cmd):
            return None
        ctx = click.Context(cmd, info_name=part)
        child = cmd.get_command(ctx, part)  # type: ignore[attr-defined]
        if child is None or child.hidden:
            return None
        cmd = child
        name = part
    return cmd, name


def _walk_command(cmd: click.BaseCommand, name: str, *, compact: bool) -> dict[str, Any]:
    """Recursively build schema for a command and all its subcommands."""
    node: dict[str, Any] = {"name": name}

    if not compact and cmd.help:
        node["description"] = cmd.help.strip()

    if _is_group(cmd):
        ctx = click.Context(cmd, info_name=name)
        children = []
        for sub_name in cmd.list_commands(ctx):  # type: ignore[attr-defined]
            sub = cmd.get_command(ctx, sub_name)  # type: ignore[attr-defined]
            if sub and not sub.hidden:
                children.append(_walk_command(sub, sub_name, compact=compact))
        if children:
            node["commands"] = children
    else:
        visible = [
            p for p in (cmd.params or [])
            if p.name not in _SKIP_PARAMS and not getattr(p, "hidden", False)
        ]
        options = [_option_schema(p, compact=compact) for p in visible if isinstance(p, (click.Option, TyperOption))]
        arguments = [_argument_schema(p, compact=compact) for p in visible if isinstance(p, (click.Argument, TyperArgument))]
        if options:
            node["options"] = options
        if arguments:
            node["arguments"] = arguments

    return node


@app.command()
def schema(
    ctx: typer.Context,
    compact: bool = typer.Option(
        False,
        "--compact",
        help="Compact output: command tree with flag names only, fewer tokens.",
    ),
    command: Optional[str] = typer.Option(
        None,
        "--command",
        help="Dot-separated path to a specific command (e.g. 'blockmodels' or 'blockmodels.versions').",
    ),
) -> None:
    """Output the complete evo command schema as JSON for AI agents.

    Use this to discover all available commands, flags, and arguments.
    Pass --compact for a smaller schema that uses fewer tokens.
    Pass --command to get schema for a single command and save tokens.
    """
    # typer.Context is click.Context; walk up to the root app
    root_ctx: click.Context = ctx  # type: ignore[assignment]
    while root_ctx.parent:
        root_ctx = root_ctx.parent
    root = root_ctx.command

    if command:
        resolved = _resolve_command(root, command)
        if resolved is None:
            from evo.cli import output
            output.emit_error(f"unknown command path: {command!r}")
        target_cmd, target_name = resolved
        typer.echo(json.dumps(_walk_command(target_cmd, target_name, compact=compact), indent=None if compact else 2))
        return

    result: dict[str, Any] = {
        "cli": "evo",
        "version": __version__,
    }
    if not compact and root.help:
        result["description"] = root.help.strip()

    if _is_group(root):
        walk_ctx = click.Context(root, info_name="evo")
        commands = []
        for name in root.list_commands(walk_ctx):  # type: ignore[attr-defined]
            cmd = root.get_command(walk_ctx, name)  # type: ignore[attr-defined]
            if cmd and not cmd.hidden:
                commands.append(_walk_command(cmd, name, compact=compact))
        result["commands"] = commands

    typer.echo(json.dumps(result, indent=None if compact else 2))
