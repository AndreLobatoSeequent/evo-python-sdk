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
from uuid import UUID

import typer

from evo.workspaces import WorkspaceAPIClient

from evo.cli import output
from evo.cli._session import build_connector, handle_api_error, require_login, resolve_org_and_hub

app = typer.Typer(help="Manage pending instance invitations.")


async def _do_list(limit: int, offset: int, org_id: UUID | None, hub_code: str | None) -> None:
    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            page = await client.list_instance_user_invitations(limit=limit, offset=offset)
            invitations = page.items()
        except Exception as e:
            handle_api_error(e, not_found_message="No instance invitations found.")

    items = [
        {
            "email": i.email,
            "invitation_id": str(i.invitation_id),
            "status": i.status,
            "invited_by": i.invited_by,
            "invited_at": i.invited_at.isoformat(),
            "expiration_date": i.expiration_date.isoformat(),
            "roles": [r.name for r in i.roles],
        }
        for i in invitations
    ]

    if not items:
        output.emit({"invitations": []}, plain="No pending invitations found.")
        return

    lines = [f"Pending invitations — showing {len(items)}:"]
    for i in invitations:
        role_names = ", ".join(r.name for r in i.roles) or "-"
        lines.append(f"  {i.invitation_id}  {i.email.ljust(30)}  {i.status.ljust(10)}  {role_names}")

    output.emit({"invitations": items}, plain="\n".join(lines))


async def _do_remove(invitation_id: UUID, org_id: UUID | None, hub_code: str | None) -> None:
    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            await client.delete_instance_user_invitation(invitation_id)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Invitation {invitation_id} not found.")

    output.emit(
        {"invitation_id": str(invitation_id), "status": "removed"},
        plain=f"Removed invitation {invitation_id}.",
    )


@app.command("list")
def list_invitations(
    limit: int = typer.Option(50, "--limit", help="Page size."),
    offset: int = typer.Option(0, "--offset", help="Pagination offset."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """List pending invitations to the Evo instance."""
    asyncio.run(_do_list(limit, offset, org_id, hub_code))


@app.command()
def remove(
    invitation_id: UUID = typer.Argument(..., help="The invitation ID to cancel."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Cancel a pending instance invitation."""
    asyncio.run(_do_remove(invitation_id, org_id, hub_code))
