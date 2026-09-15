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

# Windows Credential Manager caps a single generic credential's blob at
# CRED_MAX_CREDENTIAL_BLOB_SIZE (2560 bytes), and keyring's Windows backend encodes it as
# UTF-16 (2 bytes/char) - i.e. ~1280 characters. A JWT access token plus a refresh token can
# easily exceed that on its own, so credentials are split across multiple keyring entries,
# with a small header entry recording how many chunks to reassemble.
_CHUNK_SIZE = 800

__all__ = ["StoredCredentials", "save_credentials", "load_credentials", "delete_credentials"]


@dataclass
class StoredCredentials:
    token: AccessToken
    org_id: UUID
    org_name: str
    hub_url: str
    hub_code: str = ""
    schema_version: int = 2
    client_id: str = ""
    ims_url: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "token": json.loads(self.token.model_dump_json(by_alias=True, exclude_unset=True)),
                "org_id": str(self.org_id),
                "org_name": self.org_name,
                "hub_url": self.hub_url,
                "hub_code": self.hub_code,
                "schema_version": self.schema_version,
                "client_id": self.client_id,
                "ims_url": self.ims_url,
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
            # hub_code/schema_version were added in schema v2 — fall back gracefully for credentials
            # stored by an earlier CLI version instead of treating them as corrupt.
            hub_code=d.get("hub_code", ""),
            schema_version=d.get("schema_version", 1),
            client_id=d.get("client_id", ""),
            ims_url=d.get("ims_url", ""),
        )


def _chunk_key(index: int) -> str:
    return f"{_KEY}/chunk/{index}"


def save_credentials(creds: StoredCredentials) -> None:
    # Clear out any previously stored chunks first, in case the new payload needs fewer of
    # them than the old one did.
    delete_credentials()

    data = creds.to_json()
    chunks = [data[i : i + _CHUNK_SIZE] for i in range(0, len(data), _CHUNK_SIZE)]
    for i, chunk in enumerate(chunks):
        keyring.set_password(_SERVICE, _chunk_key(i), chunk)
    # Write the header last so a load never sees a chunk count with missing chunks.
    keyring.set_password(_SERVICE, _KEY, str(len(chunks)))


def load_credentials() -> StoredCredentials | None:
    header = keyring.get_password(_SERVICE, _KEY)
    if header is None:
        return None

    try:
        num_chunks = int(header)
    except ValueError:
        # Legacy (pre-chunking) storage: the header key held the full JSON payload directly.
        data = header
    else:
        parts = []
        for i in range(num_chunks):
            part = keyring.get_password(_SERVICE, _chunk_key(i))
            if part is None:
                return None
            parts.append(part)
        data = "".join(parts)

    try:
        return StoredCredentials.from_json(data)
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def delete_credentials() -> None:
    header = keyring.get_password(_SERVICE, _KEY)
    if header is not None:
        try:
            num_chunks = int(header)
        except ValueError:
            num_chunks = 0
        for i in range(num_chunks):
            try:
                keyring.delete_password(_SERVICE, _chunk_key(i))
            except keyring.errors.PasswordDeleteError:
                pass

    try:
        keyring.delete_password(_SERVICE, _KEY)
    except keyring.errors.PasswordDeleteError:
        pass
