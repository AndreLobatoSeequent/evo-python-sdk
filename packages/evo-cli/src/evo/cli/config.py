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

__all__ = [
    "DEFAULT_REDIRECT_URI",
    "CliConfig",
    "EvoEnvironment",
    "get_client_id",
    "get_environment",
    "get_redirect_uri",
    "get_workspace_id",
    "load_config",
    "save_config",
]

_CONFIG_FILE = Path.home() / ".evo" / "config.json"

DEFAULT_REDIRECT_URI = "http://localhost:3000/signin-callback"


@dataclass(frozen=True)
class EvoEnvironment:
    name: str
    ims_url: str
    discovery_url: str
    docs_url: str


# Known environment presets, selected by the persisted "env" config value.
_ENVIRONMENTS: dict[str, EvoEnvironment] = {
    "prod": EvoEnvironment(
        name="prod",
        ims_url="https://ims.bentley.com",
        discovery_url="https://discover.api.seequent.com",
        docs_url="https://developer.seequent.com/docs/guides/getting-started/apps-and-tokens",
    ),
    "qa": EvoEnvironment(
        name="qa",
        ims_url="https://qa-ims.bentley.com",
        discovery_url="https://discover.dev.evo.seequent.dev",  # TODO: confirm exact URL
        docs_url="https://developer.int.seequent.com/docs/guides/getting-started/apps-and-tokens",
    ),
}

_DEFAULT_ENV = "prod"


@dataclass
class CliConfig:
    """User-level CLI setup: Evo app credentials and target environment.

    Persisted as plain JSON (not the OS keyring) since none of it is secret - it's the same
    kind of information an app's source code would otherwise hardcode.
    """

    schema_version: int = 1
    client_id: str | None = None
    redirect_uri: str = DEFAULT_REDIRECT_URI
    env: str = _DEFAULT_ENV

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> CliConfig:
        d = json.loads(data)
        return cls(
            schema_version=d.get("schema_version", 1),
            client_id=d.get("client_id"),
            redirect_uri=d.get("redirect_uri") or DEFAULT_REDIRECT_URI,
            env=d.get("env", _DEFAULT_ENV),
        )


def load_config() -> CliConfig:
    if not _CONFIG_FILE.exists():
        return CliConfig()
    try:
        return CliConfig.from_json(_CONFIG_FILE.read_text())
    except (KeyError, ValueError, json.JSONDecodeError):
        return CliConfig()


def save_config(config: CliConfig) -> None:
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(config.to_json())


def get_environment(name: str | None = None) -> EvoEnvironment:
    """Resolve an Evo environment preset.

    :param name: an explicit environment name to resolve (used to validate a value before it's
        persisted). Defaults to the persisted "env" config value ("prod" if never configured).
    """
    env_name = (name or load_config().env).lower()
    preset = _ENVIRONMENTS.get(env_name)
    if preset is None:
        known = ", ".join(_ENVIRONMENTS)
        raise ValueError(f"Unknown environment {env_name!r}. Known environments: {known}")
    return preset


def get_client_id() -> str | None:
    return load_config().client_id


def get_redirect_uri() -> str:
    return load_config().redirect_uri


def get_workspace_id(override: str | UUID | None = None) -> UUID | None:
    """Resolve the active workspace ID.

    Resolution priority:
      1. --workspace CLI argument (override)
      2. Persisted selection from 'evo workspace select'
      3. None — caller will error
    """
    from evo.cli.state import load_selection  # local import to avoid circular deps

    value: str | UUID | None = override or load_selection().workspace_id
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        raise ValueError(f"Invalid workspace ID: {value!r}. Must be a valid UUID.")
