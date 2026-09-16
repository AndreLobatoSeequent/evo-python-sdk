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

"""Admin-scoped, cross-workspace views: list every workspace in the org (not just your own), and
inspect membership of any workspace. Requires organization admin permissions.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

import typer

from evo.cli import output
from evo.cli._session import build_connector, handle_api_error, require_login, resolve_org_and_hub

if TYPE_CHECKING:
    from evo.workspaces import WorkspaceAPIClient

app = typer.Typer(help="Admin-scoped views across all workspaces in the organization.")


async def _fetch_all(client: WorkspaceAPIClient, name: str | None, deleted: bool, limit: int) -> list:
    items = []
    offset = 0
    while True:
        page = await client.list_workspaces_admin(limit=limit, offset=offset, name=name, deleted=deleted)
        items.extend(page.items())
        if page.is_last:
            return items
        offset = page.next_offset


async def _do_list(
    org_id: UUID | None,
    hub_code: str | None,
    name: str | None,
    limit: int,
    fetch_all: bool,
    deleted: bool,
) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            if fetch_all:
                workspaces = await _fetch_all(client, name, deleted, limit)
            else:
                page = await client.list_workspaces_admin(limit=limit, name=name, deleted=deleted)
                workspaces = page.items()
        except Exception as e:
            handle_api_error(e, not_found_message="No workspaces found.")

    items = [
        {
            "id": str(ws.id),
            "display_name": ws.display_name,
            "role": ws.user_role.name if ws.user_role else None,
            "updated_at": ws.updated_at.isoformat(),
        }
        for ws in workspaces
    ]

    if not items:
        output.emit({"workspaces": []}, plain="No workspaces found.")
        return

    lines = [f"All workspaces in org (admin view) — showing {len(items)}:"]
    for ws in workspaces:
        role = ws.user_role.name if ws.user_role else "-"
        lines.append(f"  {ws.id}  {ws.display_name.ljust(30)}  {role.ljust(8)}  {ws.updated_at:%Y-%m-%d}")

    output.emit({"workspaces": items}, plain="\n".join(lines))


async def _do_members(workspace_id: UUID, user_id: UUID | None, org_id: UUID | None, hub_code: str | None) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            users = await client.list_user_roles_admin(workspace_id, filter_user_id=user_id)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

    items = [
        {"user_id": str(u.user_id), "email": u.email, "full_name": u.full_name, "role": u.role.name} for u in users
    ]

    if not items:
        output.emit({"members": []}, plain="No members found.")
        return

    lines = [f"Members of workspace {workspace_id} (admin view):"]
    for u in users:
        lines.append(f"  {u.user_id}  {(u.email or '-').ljust(30)}  {(u.full_name or '-').ljust(20)}  {u.role.name}")

    output.emit({"members": items}, plain="\n".join(lines))


@app.command("list")
def list_workspaces(
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
    name: str | None = typer.Option(None, "--name", help="Filter by workspace name."),
    limit: int = typer.Option(50, "--limit", help="Page size when not using --all."),
    all: bool = typer.Option(False, "--all", help="Fetch every page of results."),  # noqa: A002
    deleted: bool = typer.Option(False, "--deleted", help="Include soft-deleted workspaces."),
) -> None:
    """List every workspace in the organization, regardless of your own membership."""
    asyncio.run(_do_list(org_id, hub_code, name, limit, all, deleted))


@app.command()
def members(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID."),
    user_id: UUID | None = typer.Option(None, "--user-id", help="Filter to a single user."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """List the members of any workspace, regardless of your own membership."""
    asyncio.run(_do_members(workspace_id, user_id, org_id, hub_code))
