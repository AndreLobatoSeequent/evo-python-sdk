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
from uuid import UUID

from evo.aio.transport import AioTransport
from evo.common import APIConnector
from evo.common.data import Environment
from evo.oauth import AccessTokenAuthorizer, OAuthConnector
from evo.oauth.data import AccessToken

from evo.cli import output
from evo.cli.auth.token_store import StoredCredentials, load_credentials, save_credentials
from evo.cli.config import get_workspace_id

_USER_AGENT = "evo-cli/0.1.0"

__all__ = ["require_credentials", "make_environment", "make_connector", "make_transport"]


async def _try_refresh(creds: StoredCredentials) -> StoredCredentials | None:
    """Attempt a silent token refresh using the stored refresh token. Returns None on any failure."""
    if not (creds.client_id and creds.ims_url and creds.token.refresh_token):
        return None
    try:
        transport = make_transport()
        oauth_connector = OAuthConnector(transport, client_id=creds.client_id, base_uri=creds.ims_url)
        async with oauth_connector:
            new_token = await oauth_connector.fetch_token(
                {"grant_type": "refresh_token", "refresh_token": creds.token.refresh_token},
                AccessToken,
            )
        new_creds = StoredCredentials(
            token=new_token,
            org_id=creds.org_id,
            org_name=creds.org_name,
            hub_url=creds.hub_url,
            client_id=creds.client_id,
            ims_url=creds.ims_url,
        )
        save_credentials(new_creds)
        return new_creds
    except Exception:
        return None


async def require_credentials() -> StoredCredentials:
    """Load stored credentials, silently refreshing if expired, or exit with a structured error."""
    creds = load_credentials()
    if creds is None:
        output.emit_error("not_logged_in", hint="Run 'evo auth login' first")
    if creds.token.is_expired:
        refreshed = await _try_refresh(creds)
        if refreshed is not None:
            return refreshed
        output.emit_error("session_expired", hint="Run 'evo auth login' to re-authenticate")
    return creds


def make_environment(creds: StoredCredentials, workspace_id_override: str | UUID | None = None) -> Environment:
    """Build an SDK Environment from credentials + workspace context.

    The hub URL comes from credentials (set at login time via the Discovery API).
    Override it at runtime with EVO_HUB_URL for all services (objects, files, etc.).
    """
    workspace_id = get_workspace_id(workspace_id_override)
    if workspace_id is None:
        output.emit_error(
            "no_workspace",
            hint="Set EVO_WORKSPACE_ID or pass --workspace <uuid>",
        )
    hub_url = os.environ.get("EVO_HUB_URL") or creds.hub_url
    return Environment(hub_url=hub_url, org_id=creds.org_id, workspace_id=workspace_id)


def make_transport() -> AioTransport:
    return AioTransport(user_agent=_USER_AGENT)


def make_connector(creds: StoredCredentials) -> APIConnector:
    """Create an APIConnector authenticated with the stored token.

    The base URL comes from credentials (set at login time via the Discovery API).
    Override it at runtime with EVO_HUB_URL for all services (objects, files, etc.).
    """
    transport = AioTransport(user_agent=_USER_AGENT)
    authorizer = AccessTokenAuthorizer(creds.token.access_token)
    base_url = os.environ.get("EVO_HUB_URL") or creds.hub_url
    return APIConnector(base_url, transport, authorizer)
