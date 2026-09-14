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
from dataclasses import dataclass
from uuid import UUID

import keyring
import keyring.errors

from evo.oauth.data import AccessToken

_SERVICE = "seequent-evo-cli"
_KEY = "credentials"

__all__ = ["StoredCredentials", "save_credentials", "load_credentials", "delete_credentials"]


@dataclass
class StoredCredentials:
    token: AccessToken
    org_id: UUID
    org_name: str
    hub_url: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "token": json.loads(self.token.model_dump_json(by_alias=True, exclude_unset=True)),
                "org_id": str(self.org_id),
                "org_name": self.org_name,
                "hub_url": self.hub_url,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> StoredCredentials:
        d = json.loads(data)
        return cls(
            token=AccessToken.model_validate(d["token"]),
            org_id=UUID(d["org_id"]),
            org_name=d["org_name"],
            hub_url=d["hub_url"],
        )


def save_credentials(creds: StoredCredentials) -> None:
    keyring.set_password(_SERVICE, _KEY, creds.to_json())


def load_credentials() -> StoredCredentials | None:
    data = keyring.get_password(_SERVICE, _KEY)
    if data is None:
        return None
    try:
        return StoredCredentials.from_json(data)
    except (KeyError, ValueError):
        return None


def delete_credentials() -> None:
    try:
        keyring.delete_password(_SERVICE, _KEY)
    except keyring.errors.PasswordDeleteError:
        pass
