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

import os
from dataclasses import dataclass
from uuid import UUID

__all__ = ["EvoEnvironment", "get_environment", "get_workspace_id"]


@dataclass(frozen=True)
class EvoEnvironment:
    name: str
    ims_url: str
    discovery_url: str


# Known environment presets. EVO_ENV selects one of these by name.
_ENVIRONMENTS: dict[str, EvoEnvironment] = {
    "prod": EvoEnvironment(
        name="prod",
        ims_url="https://ims.bentley.com",
        discovery_url="https://discover.api.seequent.com",
    ),
    "qa": EvoEnvironment(
        name="qa",
        ims_url="https://qa-ims.bentley.com",
        discovery_url="https://discover.dev.evo.seequent.dev",  # TODO: confirm exact URL
    ),
}

_DEFAULT_ENV = "prod"


def get_environment() -> EvoEnvironment:
    """Resolve the active Evo environment from environment variables.

    Resolution order (most specific wins):
    1. EVO_IMS_URL / EVO_DISCOVERY_URL — override individual URLs
    2. EVO_ENV=<name> — select a named preset (qa, prod)
    3. Default: prod
    """
    env_name = os.environ.get("EVO_ENV", _DEFAULT_ENV).lower()
    preset = _ENVIRONMENTS.get(env_name)
    if preset is None:
        known = ", ".join(_ENVIRONMENTS)
        raise ValueError(f"Unknown EVO_ENV={env_name!r}. Known environments: {known}")

    ims_url = os.environ.get("EVO_IMS_URL") or preset.ims_url
    discovery_url = os.environ.get("EVO_DISCOVERY_URL") or preset.discovery_url

    return EvoEnvironment(name=env_name, ims_url=ims_url, discovery_url=discovery_url)


def get_workspace_id(override: str | UUID | None = None) -> UUID | None:
    """Resolve the active workspace ID.

    Resolution priority:
      1. --workspace CLI argument (override)
      2. EVO_WORKSPACE_ID env var
      3. None — workspace commands will error at runtime

    TODO: replace env var fallback with user settings once workspace selection is implemented.
    """
    value: str | UUID | None = override or os.environ.get("EVO_WORKSPACE_ID")
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        raise ValueError(f"Invalid workspace ID: {value!r}. Must be a valid UUID.")
