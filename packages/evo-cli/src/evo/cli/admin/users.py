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

from evo.cli import output
from evo.cli._session import build_connector, handle_api_error, require_login, resolve_org_and_hub

app = typer.Typer(help="Manage users at the instance level.")


async def _do_list(fetch_all: bool, limit: int, offset: int, org_id: UUID | None, hub_code: str | None) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            if fetch_all:
                users = await client.list_all_instance_users(limit=limit, offset=offset)
            else:
                page = await client.list_instance_users(limit=limit, offset=offset)
                users = page.items()
        except Exception as e:
            handle_api_error(e, not_found_message="No instance users found.")

    items = [
        {
            "user_id": str(u.user_id),
            "email": u.email,
            "full_name": u.full_name,
            "roles": [{"role_id": str(r.role_id), "name": r.name} for r in u.roles],
        }
        for u in users
    ]

    if not items:
        output.emit({"users": []}, plain="No instance users found.")
        return

    lines = [f"Instance users — showing {len(items)}:"]
    for u in users:
        role_names = ", ".join(r.name for r in u.roles) or "-"
        lines.append(f"  {u.user_id}  {(u.email or '-').ljust(30)}  {(u.full_name or '-').ljust(20)}  {role_names}")

    output.emit({"users": items}, plain="\n".join(lines))


async def _do_remove(user_id: UUID, org_id: UUID | None, hub_code: str | None) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            await client.remove_instance_user(user_id)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Instance user {user_id} not found.")

    output.emit({"user_id": str(user_id), "status": "removed"}, plain=f"Removed user {user_id} from the instance.")


async def _do_set_roles(user_id: UUID, role_ids: list[UUID], org_id: UUID | None, hub_code: str | None) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            updated = await client.update_instance_user_roles(user_id, role_ids)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Instance user {user_id} not found.")

    role_names = [r.name for r in updated.roles]
    output.emit(
        {
            "user_id": str(updated.user_id),
            "roles": [{"role_id": str(r.role_id), "name": r.name} for r in updated.roles],
        },
        plain=f"Updated roles for user {user_id}: {', '.join(role_names) or '-'}",
    )


async def _do_invite(users: dict[str, list[UUID]], org_id: UUID | None, hub_code: str | None) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            result = await client.add_users_to_instance(users)
        except Exception as e:
            handle_api_error(e, not_found_message="Could not add users to the instance.")

    data = {
        "members": [{"user_id": str(m.user_id), "email": m.email, "full_name": m.full_name} for m in result.members],
        "invitations": [
            {"email": i.email, "invitation_id": str(i.invitation_id), "status": i.status} for i in result.invitations
        ],
    }
    lines = []
    if result.members:
        lines.append(f"Added {len(result.members)} existing user(s): " + ", ".join(m.email for m in result.members))
    if result.invitations:
        lines.append(f"Sent {len(result.invitations)} invitation(s): " + ", ".join(i.email for i in result.invitations))
    if not lines:
        lines.append("No users added or invited.")

    output.emit(data, plain="\n".join(lines))


def _parse_users_option(entries: list[str]) -> dict[str, list[UUID]]:
    users: dict[str, list[UUID]] = {}
    for entry in entries:
        if ":" not in entry:
            output.emit_error(f"Invalid --user {entry!r}. Expected 'email:role_id[,role_id...]'.")
        email, roles_str = entry.split(":", 1)
        email = email.strip()
        try:
            role_ids = [UUID(r.strip()) for r in roles_str.split(",") if r.strip()]
        except ValueError:
            output.emit_error(f"Invalid role ID in --user {entry!r}.")
        if not email or not role_ids:
            output.emit_error(f"--user {entry!r} must include an email and at least one role ID.")
        users[email] = role_ids
    return users


@app.command("list")
def list_users(
    all: bool = typer.Option(False, "--all", help="Fetch every page of results."),  # noqa: A002
    limit: int = typer.Option(50, "--limit", help="Page size when not using --all."),
    offset: int = typer.Option(0, "--offset", help="Pagination offset."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """List users who have access to the Evo instance."""
    asyncio.run(_do_list(all, limit, offset, org_id, hub_code))


@app.command()
def remove(
    user_id: UUID = typer.Argument(..., help="The user ID to remove from the instance."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Remove a user from the Evo instance entirely."""
    asyncio.run(_do_remove(user_id, org_id, hub_code))


@app.command("set-roles")
def set_roles(
    user_id: UUID = typer.Argument(..., help="The user ID to update."),
    roles: str = typer.Argument(..., help="Comma-separated role IDs (see 'evo admin roles list')."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Replace a user's instance-level roles."""
    role_ids = [UUID(r.strip()) for r in roles.split(",") if r.strip()]
    asyncio.run(_do_set_roles(user_id, role_ids, org_id, hub_code))


@app.command()
def invite(
    user: list[str] = typer.Option(
        ..., "--user", help="'email:role_id[,role_id...]' - repeat --user for multiple people."
    ),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Invite or add users to the Evo instance, assigning them instance-level roles."""
    users_map = _parse_users_option(user)
    asyncio.run(_do_invite(users_map, org_id, hub_code))
