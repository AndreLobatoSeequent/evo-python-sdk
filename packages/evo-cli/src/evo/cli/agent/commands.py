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
from typing import Any

import click
import typer

from evo.cli import __version__

app = typer.Typer(help="AI agent utilities — machine-readable schema and discovery.")

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
        options = [_option_schema(p, compact=compact) for p in visible if isinstance(p, click.Option)]
        arguments = [_argument_schema(p, compact=compact) for p in visible if isinstance(p, click.Argument)]
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
) -> None:
    """Output the complete evo command schema as JSON for AI agents.

    Use this to discover all available commands, flags, and arguments.
    Pass --compact for a smaller schema that uses fewer tokens.
    """
    # typer.Context is click.Context; walk up to the root app
    root_ctx: click.Context = ctx  # type: ignore[assignment]
    while root_ctx.parent:
        root_ctx = root_ctx.parent
    root = root_ctx.command

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
