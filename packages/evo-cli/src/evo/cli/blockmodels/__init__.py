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

# `versions`/`columns`/`reports` are nested groups only — none of them are needed just to
# list "list, get, create, ..., versions, columns, reports" for `evo blockmodels --help`.
_LAZY_SUBCOMMANDS: list[tuple[str, str, str, bool]] = [
    ("versions", "evo.cli.blockmodels.versions", "Manage block model versions.", False),
    ("columns", "evo.cli.blockmodels.columns", "Manage block model columns.", False),
    ("reports", "evo.cli.blockmodels.reports", "Manage block model report specifications.", False),
]


class _BlockModelsGroup(TyperGroup):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.commands.update(lazy_commands(_LAZY_SUBCOMMANDS))


app.info.cls = _BlockModelsGroup

__all__ = ["app"]
