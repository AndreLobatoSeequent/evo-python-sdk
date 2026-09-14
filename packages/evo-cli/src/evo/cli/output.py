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
import os
import sys
from enum import Enum
from typing import Any

import typer

__all__ = [
    "OutputFormat",
    "init",
    "emit",
    "emit_error",
    "is_interactive",
    "current_format",
]


class OutputFormat(str, Enum):
    plain = "plain"
    json = "json"


def _agent_mode_enabled() -> bool:
    return os.environ.get("EVO_CLI_AGENT_MODE", "").lower() in ("1", "true", "yes")


# Module-level state, set once by init() at the start of each CLI invocation.
_format: OutputFormat = OutputFormat.plain
_interactive: bool = True


def init(format_override: OutputFormat | None = None) -> None:
    """Initialise output state. Call once from the root app callback.

    Resolution priority:
      1. --format CLI argument (format_override)
      2. EVO_CLI_AGENT_MODE env var  →  json + non-interactive
      3. Default: plain + interactive
    """
    global _format, _interactive
    agent = _agent_mode_enabled()
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
    """False when EVO_CLI_AGENT_MODE is set — no prompts, fail fast."""
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


def emit_error(message: str, exit_code: int = 1, **extra: Any) -> None:
    """Emit an error then exit.

    In json mode:  {"error": message, ...extra}  →  stderr
    In plain mode: "Error: message"               →  stderr

    Always exits with exit_code (default 1).
    """
    if _format == OutputFormat.json:
        payload = {"error": message, **extra}
        typer.echo(_serialize(payload), file=sys.stderr)
    else:
        typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(exit_code)
