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

from evo.workspaces import WorkspaceAPIClient, WorkspaceRole

from evo.cli import output
from evo.cli._session import build_connector, handle_api_error, require_login, resolve_org_and_hub

app = typer.Typer(help="Manage who has access to a workspace.")


def _parse_role(value: str) -> WorkspaceRole:
    try:
        return WorkspaceRole[value.lower()]
    except KeyError:
        output.emit_error(f"Invalid role {value!r}. Expected one of: viewer, editor, owner.")


async def _do_list(workspace_id: UUID, user_id: UUID | None, org_id: UUID | None, hub_code: str | None) -> None:
    creds = require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            users = await client.list_user_roles(workspace_id, filter_user_id=user_id)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

    items = [
        {
            "user_id": str(u.user_id),
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role.name,
        }
        for u in users
    ]

    if not items:
        output.emit({"members": []}, plain="No members found.")
        return

    lines = [f"Members of workspace {workspace_id}:"]
    for u in users:
        lines.append(f"  {u.user_id}  {(u.email or '-').ljust(30)}  {(u.full_name or '-').ljust(20)}  {u.role.name}")

    output.emit({"members": items}, plain="\n".join(lines))


async def _do_get(workspace_id: UUID, org_id: UUID | None, hub_code: str | None) -> None:
    creds = require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            user_role = await client.get_current_user_role(workspace_id)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

    output.emit(
        {"user_id": str(user_role.user_id), "role": user_role.role.name},
        plain=f"Your role in workspace {workspace_id}: {user_role.role.name}",
    )


async def _do_set(workspace_id: UUID, user_id: UUID, role: WorkspaceRole, org_id: UUID | None, hub_code: str | None) -> None:
    creds = require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            user_role = await client.assign_user_role(workspace_id, user_id, role)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

    output.emit(
        {"user_id": str(user_role.user_id), "role": user_role.role.name},
        plain=f"Assigned {user_id} the role {user_role.role.name} in workspace {workspace_id}.",
    )


async def _do_remove(workspace_id: UUID, user_id: UUID, org_id: UUID | None, hub_code: str | None) -> None:
    creds = require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            await client.delete_user_role(workspace_id, user_id)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

    output.emit(
        {"user_id": str(user_id), "status": "removed"},
        plain=f"Removed {user_id}'s access to workspace {workspace_id}.",
    )


@app.command("list")
def list_members(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID."),
    user_id: UUID | None = typer.Option(None, "--user-id", help="Filter to a single user."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """List the users who have access to a workspace, and their roles."""
    asyncio.run(_do_list(workspace_id, user_id, org_id, hub_code))


@app.command()
def get(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Show your own role in a workspace."""
    asyncio.run(_do_get(workspace_id, org_id, hub_code))


@app.command("set")
def set_role(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID."),
    user_id: UUID = typer.Argument(..., help="The user ID to grant a role to."),
    role: str = typer.Argument(..., help="The role to assign: viewer, editor, or owner."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Grant or change a user's role in a workspace."""
    parsed_role = _parse_role(role)
    asyncio.run(_do_set(workspace_id, user_id, parsed_role, org_id, hub_code))


@app.command()
def remove(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID."),
    user_id: UUID = typer.Argument(..., help="The user ID to remove."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Revoke a user's access to a workspace."""
    asyncio.run(_do_remove(workspace_id, user_id, org_id, hub_code))
