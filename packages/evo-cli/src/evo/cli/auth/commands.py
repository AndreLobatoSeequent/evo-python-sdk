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
import sys

import typer

from evo.aio.transport import AioTransport
from evo.common import APIConnector
from evo.discovery import DiscoveryAPIClient, Hub, Organization
from evo.oauth import AuthorizationCodeAuthorizer, OAuthConnector
from evo.oauth.data import AccessToken

from .token_store import StoredCredentials, delete_credentials, load_credentials, save_credentials

app = typer.Typer(help="Authenticate with Seequent Evo.")

_DISCOVERY_URL = "https://discover.api.seequent.com"
_USER_AGENT = "evo-cli/0.1.0"


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
        typer.echo(f"Error: environment variable {name} is not set.", err=True)
        raise typer.Exit(1)
    return value


def _select_org_and_hub(orgs: list[Organization]) -> tuple[Organization, Hub]:
    if not orgs:
        typer.echo("Error: no Evo organizations found for your account.", err=True)
        raise typer.Exit(1)

    flat: list[tuple[Organization, Hub]] = [
        (org, hub)
        for org in orgs
        for hub in org.hubs
    ]

    if len(flat) == 1:
        return flat[0]

    typer.echo("\nAvailable organizations and hubs:")
    for i, (org, hub) in enumerate(flat, start=1):
        typer.echo(f"  [{i}] {org.display_name} — {hub.display_name} ({hub.url})")

    choice = typer.prompt("\nSelect", type=int, default=1)
    if choice < 1 or choice > len(flat):
        typer.echo("Invalid selection.", err=True)
        raise typer.Exit(1)

    return flat[choice - 1]


async def _do_login() -> None:
    existing = load_credentials()
    if existing is not None and not existing.token.is_expired:
        typer.echo(f"Already logged in — Org: {existing.org_name}, Hub: {existing.hub_url}")
        return

    client_id = _require_env("EVO_CLIENT_ID")
    redirect_uri = _require_env("EVO_REDIRECT_URI")

    transport = AioTransport(user_agent=_USER_AGENT)

    oauth_connector = OAuthConnector(transport, client_id=client_id)
    authorizer = _CapturingAuthorizer(oauth_connector=oauth_connector, redirect_url=redirect_uri)

    typer.echo("Opening browser for authentication…")
    await authorizer.login(timeout_seconds=180)

    if authorizer._captured_token is None:
        typer.echo("Error: authentication did not produce a token.", err=True)
        raise typer.Exit(1)

    token = authorizer._captured_token

    async with APIConnector(_DISCOVERY_URL, transport, authorizer) as connector:
        discovery = DiscoveryAPIClient(connector)
        orgs = await discovery.list_organizations(service_codes=["evo"])

    org, hub = _select_org_and_hub(orgs)

    creds = StoredCredentials(token=token, org_id=org.id, org_name=org.display_name, hub_url=hub.url)
    save_credentials(creds)

    typer.echo(f"Logged in — Org: {org.display_name}, Hub: {hub.url}")


async def _do_status() -> None:
    creds = load_credentials()
    if creds is None:
        typer.echo("Not logged in. Run 'evo auth login' to authenticate.")
        return
    if creds.token.is_expired:
        typer.echo("Session expired. Run 'evo auth login' to re-authenticate.")
        return
    typer.echo(
        f"Logged in — Org: {creds.org_name}, Hub: {creds.hub_url}, "
        f"Token expires: {creds.token.expires_at:%Y-%m-%d %H:%M UTC}"
    )


@app.command()
def login() -> None:
    """Authenticate with Seequent Evo (opens browser)."""
    asyncio.run(_do_login())


@app.command()
def logout() -> None:
    """Remove stored credentials."""
    delete_credentials()
    typer.echo("Logged out.")


@app.command()
def status() -> None:
    """Show current authentication state."""
    asyncio.run(_do_status())
