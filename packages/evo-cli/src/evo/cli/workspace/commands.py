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
import dataclasses
from uuid import UUID

import typer

from evo.common import HealthCheckType, ServiceStatus
from evo.common.exceptions import EvoAPIException, ForbiddenException, NotFoundException, UnauthorizedException
from evo.workspaces import WorkspaceAPIClient

from evo.cli._session import build_connector, require_login, resolve_org_and_hub
from evo.cli.state import load_selection, save_selection

app = typer.Typer(help="List and inspect Evo workspaces.")


def _handle_api_error(e: Exception, *, not_found_message: str) -> None:
    """Convert known API errors into a friendly typer.Exit; re-raise anything unexpected."""
    if isinstance(e, NotFoundException):
        typer.echo(not_found_message, err=True)
    elif isinstance(e, (UnauthorizedException, ForbiddenException)):
        typer.echo(
            "Access denied. Your session may be expired or you may lack permission — try 'evo auth login'.",
            err=True,
        )
    elif isinstance(e, EvoAPIException):
        typer.echo(f"Error: {e}", err=True)
    else:
        raise e
    raise typer.Exit(1)


async def _do_list(
    org_id: UUID | None,
    hub_code: str | None,
    name: str | None,
    limit: int,
    fetch_all: bool,
    deleted: bool,
) -> None:
    creds = require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            if fetch_all:
                workspaces = await client.list_all_workspaces(name=name, deleted=deleted)
            else:
                page = await client.list_workspaces(limit=limit, name=name, deleted=deleted)
                workspaces = page.items()
        except Exception as e:
            _handle_api_error(e, not_found_message="Workspace not found.")

    if not workspaces:
        typer.echo("No workspaces found.")
        return

    typer.echo(f"Workspaces — showing {len(workspaces)}:")
    for ws in workspaces:
        role = ws.user_role.name if ws.user_role else "-"
        typer.echo(f"  {ws.id}  {ws.display_name.ljust(30)}  {role.ljust(8)}  {ws.updated_at:%Y-%m-%d}")


async def _do_get(workspace_id: UUID, org_id: UUID | None, hub_code: str | None) -> None:
    creds = require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            ws = await client.get_workspace(workspace_id)
        except Exception as e:
            _handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

    typer.echo(f"Workspace: {ws.display_name} ({ws.id})")
    typer.echo(f"  Description: {ws.description or '-'}")
    typer.echo(f"  Role: {ws.user_role.name if ws.user_role else '-'}")
    typer.echo(f"  Org: {ws.org_id}")
    typer.echo(f"  Hub: {ws.hub_url}")
    typer.echo(f"  Created: {ws.created_at:%Y-%m-%d %H:%M} by {ws.created_by.name or ws.created_by.email}")
    typer.echo(f"  Updated: {ws.updated_at:%Y-%m-%d %H:%M} by {ws.updated_by.name or ws.updated_by.email}")
    typer.echo(f"  Labels: {', '.join(ws.labels) if ws.labels else '-'}")


async def _do_health(org_id: UUID | None, hub_code: str | None, check_type: HealthCheckType) -> None:
    creds = require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            health = await client.get_service_health(check_type)
        except Exception as e:
            _handle_api_error(e, not_found_message="Workspace service not found.")

    typer.echo(f"Workspace service health — hub: {hub_url}")
    typer.echo(f"  Status: {health.status.value} ({health.status.name.lower()})")
    typer.echo(f"  Version: {health.version}")
    if health.dependencies:
        typer.echo("  Dependencies:")
        for dep_name, dep_status in health.dependencies.items():
            typer.echo(f"    - {dep_name}: {dep_status.value}")

    if health.status != ServiceStatus.HEALTHY:
        raise typer.Exit(1)


async def _do_create(
    name: str,
    org_id: UUID | None,
    hub_code: str | None,
    description: str | None,
    labels: list[str] | None,
) -> None:
    creds = require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            ws = await client.create_workspace(name=name, description=description, labels=labels)
        except Exception as e:
            _handle_api_error(e, not_found_message="Workspace service not found.")

    typer.echo(f"Created workspace: {ws.display_name} ({ws.id})")
    if ws.description:
        typer.echo(f"  Description: {ws.description}")
    if ws.labels:
        typer.echo(f"  Labels: {', '.join(ws.labels)}")


async def _do_select(workspace_id: UUID, org_id: UUID | None, hub_code: str | None) -> None:
    creds = require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            ws = await client.get_workspace(workspace_id)
        except Exception as e:
            _handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

    selection = load_selection()
    updated = dataclasses.replace(
        selection,
        org_id=org_id,
        hub_code=hub_code,
        hub_url=hub_url,
        hub_display_name=selection.hub_display_name if selection.hub_code == hub_code else None,
        workspace_id=ws.id,
        workspace_name=ws.display_name,
    )
    save_selection(updated)
    typer.echo(f"Selected workspace — {ws.display_name} ({ws.id})")


@app.command("list")
def list_workspaces(
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
    name: str | None = typer.Option(None, "--name", help="Filter by workspace name."),
    limit: int = typer.Option(50, "--limit", help="Page size when not using --all."),
    all: bool = typer.Option(False, "--all", help="Fetch every page of results."),  # noqa: A002
    deleted: bool = typer.Option(False, "--deleted", help="Include soft-deleted workspaces."),
) -> None:
    """List workspaces in the current (or specified) organization/hub."""
    asyncio.run(_do_list(org_id, hub_code, name, limit, all, deleted))


@app.command()
def get(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID to look up."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Show details for a single workspace."""
    asyncio.run(_do_get(workspace_id, org_id, hub_code))


@app.command()
def health(
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
    check_type: str = typer.Option(
        "full", "--check-type", help="Health check depth: basic, full, or strict.", case_sensitive=False
    ),
) -> None:
    """Check the health of the workspace service for the current (or specified) hub."""
    try:
        parsed_check_type = HealthCheckType[check_type.upper()]
    except KeyError:
        typer.echo(f"Error: invalid --check-type {check_type!r}. Expected one of: basic, full, strict.", err=True)
        raise typer.Exit(1)
    asyncio.run(_do_health(org_id, hub_code, parsed_check_type))


@app.command()
def select(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID to select as the current default."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Persist a workspace as the current default for future commands."""
    asyncio.run(_do_select(workspace_id, org_id, hub_code))


@app.command()
def create(
    name: str = typer.Argument(..., help="The name of the new workspace."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
    description: str | None = typer.Option(None, "--description", help="Workspace description."),
    labels: str | None = typer.Option(None, "--labels", help="Comma-separated labels to attach to the workspace."),
) -> None:
    """Create a new workspace."""
    label_list = [label.strip() for label in labels.split(",") if label.strip()] if labels else None
    asyncio.run(_do_create(name, org_id, hub_code, description, label_list))
