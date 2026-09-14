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

"""Shared helpers for CLI commands that need an authenticated org/hub session.

This module centralizes the wiring that `instance` and `workspace` commands both need:
loading/validating stored credentials, resolving which org/hub to target, and building an
`APIConnector` against it.
"""

from __future__ import annotations

from uuid import UUID

import typer

from evo.aio.transport import AioTransport
from evo.common import APIConnector
from evo.discovery import Hub, Organization
from evo.oauth import AccessTokenAuthorizer

from . import output
from .auth.token_store import StoredCredentials, load_credentials
from .state import CurrentSelection, load_selection

_USER_AGENT = "evo-cli/0.1.0"

__all__ = ["select_org_and_hub", "require_login", "resolve_org_and_hub", "build_connector"]


def select_org_and_hub(orgs: list[Organization]) -> tuple[Organization, Hub]:
    """Prompt the user to choose an org/hub pair from the given list of organizations.

    If there is only one org/hub pair available, it is selected automatically without prompting.
    """
    if not orgs:
        output.emit_error("no Evo organizations found for your account")

    flat: list[tuple[Organization, Hub]] = [(org, hub) for org in orgs for hub in org.hubs]

    if len(flat) == 1:
        return flat[0]

    if not output.is_interactive():
        output.emit_error(
            "multiple_orgs",
            orgs=[
                {
                    "org_id": str(org.id),
                    "org_name": org.display_name,
                    "hubs": [
                        {"hub_code": hub.code, "hub_name": hub.display_name, "hub_url": hub.url} for hub in org.hubs
                    ],
                }
                for org in orgs
            ],
        )

    typer.echo("\nAvailable organizations and hubs:")
    for i, (org, hub) in enumerate(flat, start=1):
        typer.echo(f"  [{i}] {org.display_name} — {hub.display_name} ({hub.url})")

    choice = typer.prompt("\nSelect", type=int, default=1)
    if choice < 1 or choice > len(flat):
        output.emit_error("invalid selection")

    return flat[choice - 1]


def require_login() -> StoredCredentials:
    """Load stored credentials, exiting with an error if the user isn't logged in or has expired."""
    creds = load_credentials()
    if creds is None:
        typer.echo("Not logged in. Run 'evo auth login' to authenticate.", err=True)
        raise typer.Exit(1)
    if creds.token.is_expired:
        typer.echo("Session expired. Run 'evo auth login' to re-authenticate.", err=True)
        raise typer.Exit(1)
    return creds


def resolve_org_and_hub(
    org_id: UUID | None,
    hub_code: str | None,
    creds: StoredCredentials,
    selection: CurrentSelection | None = None,
) -> tuple[UUID, str, str]:
    """Resolve the org/hub to target for a command.

    Precedence: explicit --org-id/--hub-code flags > persisted current selection > login-time
    org/hub from stored credentials.

    :returns: a tuple of (org_id, hub_code, hub_url).
    """
    if selection is None:
        selection = load_selection()

    if org_id is not None and hub_code is not None:
        if selection.org_id == org_id and selection.hub_code == hub_code and selection.hub_url:
            return org_id, hub_code, selection.hub_url
        if creds.org_id == org_id and creds.hub_code == hub_code and creds.hub_url:
            return org_id, hub_code, creds.hub_url
        typer.echo(
            "Error: organization/hub not found or not accessible. Run 'evo instance list' to see available options.",
            err=True,
        )
        raise typer.Exit(1)

    if org_id is not None or hub_code is not None:
        typer.echo("Error: --org-id and --hub-code must be provided together.", err=True)
        raise typer.Exit(1)

    if selection.org_id is not None and selection.hub_code is not None and selection.hub_url:
        return selection.org_id, selection.hub_code, selection.hub_url

    if creds.hub_url:
        return creds.org_id, creds.hub_code, creds.hub_url

    typer.echo(
        "Error: no organization/hub selected. Run 'evo instance select' or pass --org-id/--hub-code.",
        err=True,
    )
    raise typer.Exit(1)


def build_connector(base_url: str, creds: StoredCredentials) -> APIConnector:
    """Build an APIConnector against the given base URL, authorized with the stored access token."""
    transport = AioTransport(user_agent=_USER_AGENT)
    authorizer = AccessTokenAuthorizer(creds.token.access_token)
    return APIConnector(base_url, transport, authorizer)
