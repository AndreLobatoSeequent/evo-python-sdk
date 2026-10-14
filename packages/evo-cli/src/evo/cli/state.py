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
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import UUID

_STATE_DIR = Path.home() / ".evo"
_STATE_FILE = _STATE_DIR / "cli-state.json"

__all__ = ["CurrentSelection", "clear_selection", "load_selection", "save_selection"]


@dataclass
class CurrentSelection:
    """The currently-selected org/hub/workspace, persisted between CLI invocations.

    This is not secret data (unlike StoredCredentials) so it's kept in a plain JSON file
    rather than the OS credential store.
    """

    schema_version: int = 1
    org_id: UUID | None = None
    org_name: str | None = None
    hub_code: str | None = None
    hub_url: str | None = None
    hub_display_name: str | None = None
    workspace_id: UUID | None = None
    workspace_name: str | None = None

    def to_json(self) -> str:
        data = asdict(self)
        data["org_id"] = str(self.org_id) if self.org_id else None
        data["workspace_id"] = str(self.workspace_id) if self.workspace_id else None
        return json.dumps(data)

    @classmethod
    def from_json(cls, data: str) -> CurrentSelection:
        d = json.loads(data)
        return cls(
            schema_version=d.get("schema_version", 1),
            org_id=UUID(d["org_id"]) if d.get("org_id") else None,
            org_name=d.get("org_name"),
            hub_code=d.get("hub_code"),
            hub_url=d.get("hub_url"),
            hub_display_name=d.get("hub_display_name"),
            workspace_id=UUID(d["workspace_id"]) if d.get("workspace_id") else None,
            workspace_name=d.get("workspace_name"),
        )


def load_selection() -> CurrentSelection:
    if not _STATE_FILE.exists():
        return CurrentSelection()
    try:
        return CurrentSelection.from_json(_STATE_FILE.read_text())
    except (KeyError, ValueError, json.JSONDecodeError):
        return CurrentSelection()


def save_selection(selection: CurrentSelection) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(selection.to_json())


def clear_selection() -> None:
    _STATE_FILE.unlink(missing_ok=True)
