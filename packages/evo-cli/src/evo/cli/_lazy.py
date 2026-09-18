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

"""Shared support for deferring imports of Typer sub-apps until they're actually used.

Command groups (`evo`, `evo admin`, ...) are composed of several Typer sub-apps, each of
which pulls in its own SDK client (and transitive deps like pandas/pyarrow/pydantic-heavy
generated models). Importing all of them up front — as `add_typer()` requires — makes
even `--help` and unrelated commands pay for every sub-app's dependencies. `LazySubcommand`
stands in for a sub-app until Click actually needs it: to list it in `--help`, static
metadata (name/short_help/hidden) is enough; to parse its args, render its own `--help`,
or dispatch into it, the first call to `_load()` imports the real module once, after
which every method below simply delegates to the resulting Click command/group.
"""

from __future__ import annotations

import importlib
from typing import Any, Optional

import click
import typer

__all__ = ["LazySubcommand", "lazy_commands"]


class LazySubcommand(click.Command):
    def __init__(self, *, name: str, short_help: str, import_path: str, hidden: bool = False) -> None:
        # `help` is set alongside `short_help` (both the same one-liner here) so that
        # introspection consumers like `evo agent schema` — which read `cmd.help` directly
        # rather than through get_short_help_str() — see the description without importing.
        super().__init__(name=name, help=short_help, short_help=short_help, hidden=hidden)
        self._import_path = import_path
        self._real: Optional[click.Command] = None

    def _load(self) -> click.Command:
        if self._real is None:
            module = importlib.import_module(self._import_path)
            sub_app = module.app
            # Use get_group_from_info(), not the public get_command(), for two reasons:
            #  - get_command() collapses a Typer instance with exactly one command and no
            #    callback/groups down to that single bare command, discarding its name. A
            #    sub-app reached via `add_typer()` never gets that treatment (it always goes
            #    through get_group_from_info() during the parent's own conversion), so e.g.
            #    `evo admin roles` — which has just one command — must keep behaving as
            #    `evo admin roles list`, not collapse to `evo admin roles` itself.
            #  - get_command() also unconditionally appends --install-completion/
            #    --show-completion for any Typer instance with `_add_completion` set, which
            #    would duplicate those options on every lazily-loaded sub-app (previously
            #    only the outermost Typer instance in a tree was ever passed to get_command()).
            self._real = typer.main.get_group_from_info(
                typer.main.TyperInfo(sub_app),
                pretty_exceptions_short=sub_app.pretty_exceptions_short,
                rich_markup_mode=sub_app.rich_markup_mode,
                suggest_commands=sub_app.suggest_commands,
            )
        return self._real

    def make_context(
        self, info_name: Optional[str], args: list[str], parent: Optional[click.Context] = None, **extra: Any
    ) -> click.Context:
        # Delegate context creation entirely to the real command so it uses its own
        # (Typer-vendored) Context class. Click's default Command.make_context would build
        # the context using *this* class's context_class, which is the wrong implementation
        # and breaks exception handling (e.g. `--help`'s ctx.exit()) once delegated further.
        return self._load().make_context(info_name, args, parent=parent, **extra)

    def get_params(self, ctx: click.Context) -> list[click.Parameter]:
        return self._load().get_params(ctx)

    def list_commands(self, ctx: click.Context) -> list[str]:
        return self._load().list_commands(ctx)  # type: ignore[attr-defined]

    def get_command(self, ctx: click.Context, name: str) -> Optional[click.Command]:
        return self._load().get_command(ctx, name)  # type: ignore[attr-defined]

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        return self._load().parse_args(ctx, args)

    def invoke(self, ctx: click.Context) -> Any:
        return self._load().invoke(ctx)

    def get_help(self, ctx: click.Context) -> str:
        return self._load().get_help(ctx)

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        self._load().format_help(ctx, formatter)

    def get_usage(self, ctx: click.Context) -> str:
        return self._load().get_usage(ctx)

    def shell_complete(self, ctx: click.Context, incomplete: str) -> list[Any]:
        return self._load().shell_complete(ctx, incomplete)


def lazy_commands(entries: list[tuple[str, str, str, bool]]) -> dict[str, click.Command]:
    """Build a `{name: LazySubcommand}` mapping from `(name, import_path, short_help, hidden)` tuples."""
    return {
        name: LazySubcommand(name=name, short_help=short_help, import_path=import_path, hidden=hidden)
        for name, import_path, short_help, hidden in entries
    }
