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
from pathlib import Path
from uuid import UUID

import typer

from evo.cli import output
from evo.cli._session import build_connector, handle_api_error, require_login, resolve_org_and_hub

app = typer.Typer(help="Manage a workspace's thumbnail image.")


async def _do_get(workspace_id: UUID, output_path: Path, org_id: UUID | None, hub_code: str | None) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            thumbnail = await client.get_thumbnail(workspace_id)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Workspace {workspace_id} has no thumbnail.")

    output_path.write_bytes(thumbnail)
    output.emit(
        {"id": str(workspace_id), "path": str(output_path), "bytes": len(thumbnail)},
        plain=f"Saved thumbnail for workspace {workspace_id} to {output_path} ({len(thumbnail)} bytes).",
    )


async def _do_set(workspace_id: UUID, file: Path, org_id: UUID | None, hub_code: str | None) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    thumbnail = bytearray(file.read_bytes())

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            await client.put_thumbnail(workspace_id, thumbnail)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

    output.emit(
        {"id": str(workspace_id), "status": "updated"},
        plain=f"Updated thumbnail for workspace {workspace_id} from {file}.",
    )


async def _do_delete(workspace_id: UUID, org_id: UUID | None, hub_code: str | None) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            await client.delete_thumbnail(workspace_id)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

    output.emit(
        {"id": str(workspace_id), "status": "deleted"},
        plain=f"Deleted thumbnail for workspace {workspace_id}.",
    )


@app.command()
def get(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID."),
    file: Path = typer.Option(..., "--file", help="Path to save the thumbnail image to."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Download a workspace's thumbnail image."""
    asyncio.run(_do_get(workspace_id, file, org_id, hub_code))


@app.command("set")
def set_thumbnail(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID."),
    file: Path = typer.Option(..., "--file", help="Path to a JPEG or PNG image to upload."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Upload or replace a workspace's thumbnail image."""
    if not file.is_file():
        output.emit_error(f"File not found: {file}")
    asyncio.run(_do_set(workspace_id, file, org_id, hub_code))


@app.command()
def delete(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Remove a workspace's thumbnail image."""
    asyncio.run(_do_delete(workspace_id, org_id, hub_code))
