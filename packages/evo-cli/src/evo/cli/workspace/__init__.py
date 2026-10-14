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

from typer.core import TyperGroup

from evo.cli._lazy import lazy_commands

from .commands import app

# `members`/`thumbnail` are nested groups only — neither is needed just to list
# "list, get, select, ..., members, thumbnail" for `evo workspace --help`.
_LAZY_SUBCOMMANDS: list[tuple[str, str, str, bool]] = [
    ("members", "evo.cli.workspace.members", "Manage who has access to a workspace.", False),
    ("thumbnail", "evo.cli.workspace.thumbnail", "Manage a workspace's thumbnail image.", False),
]


class _WorkspaceGroup(TyperGroup):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.commands.update(lazy_commands(_LAZY_SUBCOMMANDS))


app.info.cls = _WorkspaceGroup

__all__ = ["app"]
