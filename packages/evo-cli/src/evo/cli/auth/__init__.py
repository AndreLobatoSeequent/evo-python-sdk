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

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    # `evo.cli.auth.token_store` is imported directly by several other packages (e.g.
    # `evo.cli._connector`, `evo.cli.agent.commands`) just for credential storage — that
    # import always runs this `__init__.py` first (Python initializes a package before
    # any of its submodules). If `commands` (which pulls in aiohttp, oauth, discovery)
    # were imported eagerly above, every one of those unrelated consumers would pay for
    # it too. Deferring `app` here means it's only imported when actually accessed —
    # i.e. when `evo auth ...` is the command actually being run.
    if name == "app":
        from .commands import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
