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
from typing import TYPE_CHECKING
from uuid import UUID

import typer

from evo.cli import output
from evo.cli._session import build_connector, handle_api_error, require_login, select_org_and_hub
from evo.cli.config import get_environment
from evo.cli.state import CurrentSelection, load_selection, save_selection

if TYPE_CHECKING:
    from evo.discovery import Organization

app = typer.Typer(help="Discover and select the Evo organization/hub to work with.")


async def _list_organizations() -> list[Organization]:
    from evo.discovery import DiscoveryAPIClient

    creds = await require_login()
    env = get_environment()
    async with build_connector(env.discovery_url, creds) as connector:
        discovery = DiscoveryAPIClient(connector)
        try:
            return await discovery.list_organizations(service_codes=["evo"])
        except Exception as e:
            handle_api_error(e, not_found_message="No Evo organizations found for your account.")


async def _do_list() -> None:
    orgs = await _list_organizations()
    selection = load_selection()

    data = {
        "organizations": [
            {
                "org_id": str(org.id),
                "org_name": org.display_name,
                "central": (
                    {
                        "id": str(org.central.id),
                        "display_name": org.central.display_name,
                        "host": org.central.host,
                    }
                    if org.central
                    else None
                ),
                "hubs": [
                    {
                        "hub_code": hub.code,
                        "hub_name": hub.display_name,
                        "hub_url": hub.url,
                        "current": org.id == selection.org_id and hub.code == selection.hub_code,
                    }
                    for hub in org.hubs
                ],
            }
            for org in orgs
        ]
    }

    flat = [(org, hub) for org in orgs for hub in org.hubs]
    if not flat:
        output.emit(data, plain="No Evo organizations found for your account.")
        return

    lines = ["Available organizations and hubs:"]
    for i, (org, hub) in enumerate(flat, start=1):
        marker = "  [current]" if org.id == selection.org_id and hub.code == selection.hub_code else ""
        central = f"  [central: {org.central.display_name} @ {org.central.host}]" if org.central else ""
        lines.append(f"  [{i}] {org.display_name} — {hub.display_name} ({hub.url}){marker}{central}")

    output.emit(data, plain="\n".join(lines))


async def _do_select(org_id: UUID | None, hub_code: str | None) -> None:
    orgs = await _list_organizations()

    if org_id is not None or hub_code is not None:
        if org_id is None or hub_code is None:
            output.emit_error("--org-id and --hub-code must be provided together.")
        flat = [(org, hub) for org in orgs for hub in org.hubs]
        match = next(((org, hub) for org, hub in flat if org.id == org_id and hub.code == hub_code), None)
        if match is None:
            output.emit_error(
                "Organization/hub not found or not accessible. Run 'evo instance list' to see options.",
                org_id=str(org_id),
                hub_code=hub_code,
            )
        org, hub = match
    else:
        org, hub = select_org_and_hub(orgs)

    existing = load_selection()
    same_org_and_hub = existing.org_id == org.id and existing.hub_code == hub.code
    save_selection(
        CurrentSelection(
            org_id=org.id,
            org_name=org.display_name,
            hub_code=hub.code,
            hub_url=hub.url,
            hub_display_name=hub.display_name,
            # A workspace selection only makes sense within the org/hub it was made in - carry
            # it forward when re-selecting the same org/hub, but drop it when switching.
            workspace_id=existing.workspace_id if same_org_and_hub else None,
            workspace_name=existing.workspace_name if same_org_and_hub else None,
        )
    )
    output.emit(
        {"org_id": str(org.id), "org_name": org.display_name, "hub_code": hub.code, "hub_url": hub.url},
        plain=f"Selected — Org: {org.display_name}, Hub: {hub.display_name} ({hub.url})",
    )


async def _do_status() -> None:
    selection = load_selection()
    if selection.org_id is None:
        output.emit({"org_id": None}, plain="No organization/hub selected. Run 'evo instance select'.")
        return

    data = {
        "org_id": str(selection.org_id),
        "org_name": selection.org_name,
        "hub_code": selection.hub_code,
        "hub_url": selection.hub_url,
        "workspace_id": str(selection.workspace_id) if selection.workspace_id else None,
        "workspace_name": selection.workspace_name,
    }
    lines = [f"Current selection — Org: {selection.org_name}, Hub: {selection.hub_display_name} ({selection.hub_url})"]
    if selection.workspace_id is None:
        lines.append("No workspace selected. Run 'evo workspace select <id>' or pass --workspace-id explicitly.")
    else:
        lines.append(f"Current workspace — {selection.workspace_name} ({selection.workspace_id})")

    output.emit(data, plain="\n".join(lines))


@app.command("list")
def list_instances() -> None:
    """List the organizations and hubs accessible to your account."""
    asyncio.run(_do_list())


@app.command()
def select(
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID to select."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code to select."),
) -> None:
    """Choose the organization/hub to use for subsequent commands."""
    asyncio.run(_do_select(org_id, hub_code))


@app.command()
def status() -> None:
    """Show the currently selected organization/hub/workspace."""
    asyncio.run(_do_status())
