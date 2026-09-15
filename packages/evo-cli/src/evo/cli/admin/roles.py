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

app = typer.Typer(help="List roles available at the instance level.")


async def _do_list(org_id: UUID | None, hub_code: str | None) -> None:
    creds = require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            roles = await client.list_instance_roles()
        except Exception as e:
            handle_api_error(e, not_found_message="Instance roles not found.")

    items = [
        {"role_id": str(r.role_id), "name": r.name, "description": r.description, "permissions": r.permissions}
        for r in roles
    ]

    if not items:
        output.emit({"roles": []}, plain="No instance roles found.")
        return

    lines = ["Instance roles:"]
    for r in roles:
        lines.append(f"  {r.role_id}  {r.name.ljust(20)}  {r.description}")

    output.emit({"roles": items}, plain="\n".join(lines))


@app.command("list")
def list_roles(
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """List the roles available at the instance level, with their permissions and role IDs."""
    asyncio.run(_do_list(org_id, hub_code))
