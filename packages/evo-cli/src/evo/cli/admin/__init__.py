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

from typing import Any

import typer
from typer.core import TyperGroup

from evo.cli._lazy import lazy_commands

# `evo admin`'s own subcommands all live in `evo.workspaces` (a ~72-model generated
# pydantic schema, the single most expensive import in the CLI) — none of it is needed
# just to list "users, invitations, roles, workspaces" for `evo admin --help`.
_LAZY_SUBCOMMANDS: list[tuple[str, str, str, bool]] = [
    ("users", "evo.cli.admin.users", "Manage users at the instance level.", False),
    ("invitations", "evo.cli.admin.invitations", "Manage pending instance invitations.", False),
    ("roles", "evo.cli.admin.roles", "List roles available at the instance level.", False),
    (
        "workspaces",
        "evo.cli.admin.workspaces",
        "Admin-scoped views across all workspaces in the organization.",
        False,
    ),
]


class _AdminGroup(TyperGroup):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.commands.update(lazy_commands(_LAZY_SUBCOMMANDS))


app = typer.Typer(
    cls=_AdminGroup,
    help="Manage instance-level users, invitations, roles, and cross-workspace admin views.",
)

__all__ = ["app"]
