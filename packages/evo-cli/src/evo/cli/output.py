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
from enum import Enum
from typing import Any

# Matches machine-readable error codes: lowercase letters, digits, underscores, no spaces.
_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Maps known error codes to standard exit codes so agents can branch without parsing text.
#   0  success (never here)
#   1  general / unexpected error  (default)
#   2  usage / argument error      (Click raises this itself for bad flags)
#   3  auth / permission error
#   4  not found
#   5  conflict (resource already exists)
_CODE_EXIT: dict[str, int] = {
    "not_logged_in": 3,
    "session_expired": 3,
    "access_denied": 3,
    "forbidden": 3,
    "not_found": 4,
    "file_exists": 5,
}

import typer

from evo.cli import useragent

__all__ = [
    "OutputFormat",
    "init",
    "emit",
    "emit_error",
    "emit_panel",
    "is_interactive",
    "current_format",
]


class OutputFormat(str, Enum):
    plain = "plain"
    json = "json"


# Module-level state, set once by init() at the start of each CLI invocation.
_format: OutputFormat = OutputFormat.plain
_interactive: bool = True


def init(format_override: OutputFormat | None = None) -> None:
    """Initialise output state. Call once from the root app callback.

    Resolution priority:
      1. --format CLI argument (format_override)
      2. Agent mode (auto-detected or EVO_CLI_AGENT_MODE)  →  json + non-interactive
      3. Default: plain + interactive

    Agent mode is determined by useragent.is_agent_mode(), which checks:
      - EVO_FORCE_AGENT_MODE=1 (force on)
      - EVO_NO_AGENT_MODE=1 (force off, overrides everything)
      - EVO_CLI_AGENT_MODE=1 (legacy, for backward compat)
      - Auto-detection of AI agents (Claude Code, Cursor, etc.)
    """
    global _format, _interactive
    agent = useragent.is_agent_mode()
    _interactive = not agent
    if format_override is not None:
        _format = format_override
    elif agent:
        _format = OutputFormat.json
    else:
        _format = OutputFormat.plain


def current_format() -> OutputFormat:
    return _format


def is_interactive() -> bool:
    """False when agent mode is enabled (auto-detected or explicit) — no prompts, fail fast."""
    return _interactive


def _serialize(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def emit(data: Any = None, *, plain: str | None = None) -> None:
    """Emit a successful result.

    In json mode:  data is serialised as JSON (required).
    In plain mode: plain text is printed; falls back to str(data) if plain is None.
    """
    if _format == OutputFormat.json:
        if data is None:
            data = {}
        typer.echo(_serialize(data))
    else:
        typer.echo(plain if plain is not None else str(data))


def emit_panel(title: str, body_lines: list[str], *, width: int = 70) -> None:
    """Print a Rich-bordered panel to stdout. No-op in JSON mode."""
    if _format == OutputFormat.json:
        return
    from rich.console import Console
    from rich.panel import Panel

    body = "\n".join(body_lines)
    Console().print(Panel(body, title=f"[bold]{title}[/bold]", width=width, title_align="left"))


def emit_error(message: str, exit_code: int = 1, *, code: str | None = None, **extra: Any) -> None:
    """Emit an error then exit.

    In json mode:  {"error": message, "code": code, ...extra}  →  stderr
    In plain mode: "Error: message"                             →  stderr

    The "code" field is a stable machine-readable identifier agents can branch on without
    string parsing. When omitted, it is auto-derived from the message if the message is
    already a slug (e.g. "not_logged_in"). Pass code= explicitly for human-readable
    messages that still need a stable code.

    The exit code is auto-resolved from _CODE_EXIT when a known code is present,
    overriding the default exit_code=1. Explicit exit_code= always wins.
    """
    if _format == OutputFormat.json:
        resolved_code = code or (message if _CODE_RE.match(message) else None)
        payload: dict[str, Any] = {"error": message}
        if resolved_code:
            payload["code"] = resolved_code
        payload.update(extra)
        typer.echo(_serialize(payload), file=sys.stderr)
    else:
        typer.echo(f"Error: {message}", err=True)
    resolved_code = code or (message if _CODE_RE.match(message) else None)
    resolved_exit = _CODE_EXIT.get(resolved_code, exit_code) if resolved_code else exit_code
    raise typer.Exit(resolved_exit)
