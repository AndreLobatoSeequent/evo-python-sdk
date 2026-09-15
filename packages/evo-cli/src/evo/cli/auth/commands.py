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

import asyncio
import os

import typer

from evo.aio.transport import AioTransport
from evo.common import APIConnector
from evo.discovery import DiscoveryAPIClient
from evo.oauth import AuthorizationCodeAuthorizer, OAuthConnector
from evo.oauth.data import AccessToken, EvoScopes, Scopes

from evo.cli import output
from evo.cli.config import get_environment
from evo.cli.state import CurrentSelection, clear_selection, load_selection, save_selection

from .token_store import StoredCredentials, delete_credentials, load_credentials, save_credentials

app = typer.Typer(help="Authenticate with Seequent Evo.")

_USER_AGENT = "evo-cli/0.1.0"

_CLI_SCOPES: Scopes = (
    EvoScopes.all_evo          # evo.discovery | evo.workspace | evo.blocksync | evo.object | evo.file
    | EvoScopes.evo_audit
    | "itwin-platform"
    | "evo.users:read"
    | "evo.lineage:read"
)


class _CapturingAuthorizer(AuthorizationCodeAuthorizer):
    """Subclass that exposes the token after login so it can be persisted."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._captured_token: AccessToken | None = None

    def _update_token(self, new_token: AccessToken) -> None:
        self._captured_token = new_token
        super()._update_token(new_token)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        output.emit_error(f"environment variable {name} is not set")
    return value


async def _do_login() -> None:
    existing = load_credentials()
    if existing is not None and not existing.token.is_expired:
        output.emit(
            {"org_name": existing.org_name, "hub_url": existing.hub_url, "status": "already_logged_in"},
            plain=f"Already logged in — Org: {existing.org_name}, Hub: {existing.hub_url}",
        )
        return

    client_id = _require_env("EVO_CLIENT_ID")
    redirect_uri = _require_env("EVO_REDIRECT_URI")

    try:
        env = get_environment()
    except ValueError as e:
        output.emit_error(str(e))

    transport = AioTransport(user_agent=_USER_AGENT)

    oauth_connector = OAuthConnector(transport, client_id=client_id, base_uri=env.ims_url)
    authorizer = _CapturingAuthorizer(oauth_connector=oauth_connector, redirect_url=redirect_uri, scopes=_CLI_SCOPES)

    if output.is_interactive():
        typer.echo(f"Opening browser for authentication… (env: {env.name})")
    await authorizer.login(timeout_seconds=180)

    if authorizer._captured_token is None:
        output.emit_error("authentication did not produce a token")

    token = authorizer._captured_token

    async with APIConnector(env.discovery_url, transport, authorizer) as connector:
        discovery = DiscoveryAPIClient(connector)
        orgs = await discovery.list_organizations(service_codes=["evo"])

    # Imported lazily to avoid a circular import: _session imports from evo.cli.auth.token_store,
    # which (as a submodule of this package) forces auth/__init__.py - and therefore this module -
    # to load first.
    from .._session import select_org_and_hub as _select_org_and_hub

    org, hub = _select_org_and_hub(orgs)

    creds = StoredCredentials(
        token=token, org_id=org.id, org_name=org.display_name, hub_url=hub.url, hub_code=hub.code
    )
    save_credentials(creds)

    if load_selection().org_id is None:
        save_selection(
            CurrentSelection(
                org_id=org.id,
                org_name=org.display_name,
                hub_code=hub.code,
                hub_url=hub.url,
                hub_display_name=hub.display_name,
            )
        )

    output.emit(
        {"org_name": org.display_name, "hub_url": hub.url, "status": "logged_in"},
        plain=f"Logged in — Org: {org.display_name}, Hub: {hub.url}",
    )


async def _do_status() -> None:
    creds = load_credentials()
    if creds is None:
        output.emit(
            {"status": "not_logged_in"},
            plain="Not logged in. Run 'evo auth login' to authenticate.",
        )
        return
    if creds.token.is_expired:
        output.emit(
            {"status": "expired"},
            plain="Session expired. Run 'evo auth login' to re-authenticate.",
        )
        return
    expires_at = creds.token.expires_at.strftime("%Y-%m-%d %H:%M UTC")
    output.emit(
        {"status": "logged_in", "org_name": creds.org_name, "hub_url": creds.hub_url, "expires_at": expires_at},
        plain=f"Logged in — Org: {creds.org_name}, Hub: {creds.hub_url}, Token expires: {expires_at}",
    )


@app.command()
def login() -> None:
    """Authenticate with Seequent Evo (opens browser)."""
    asyncio.run(_do_login())


@app.command()
def logout() -> None:
    """Remove stored credentials."""
    delete_credentials()
    clear_selection()
    output.emit({"status": "logged_out"}, plain="Logged out.")


@app.command()
def status() -> None:
    """Show current authentication state."""
    asyncio.run(_do_status())
