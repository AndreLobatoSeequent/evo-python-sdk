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
from typing import TYPE_CHECKING, Optional
from uuid import UUID

import typer

from evo.cli import output
from evo.cli._connector import make_connector, make_environment, require_credentials
from evo.cli._session import build_connector, handle_api_error, require_login, resolve_org_and_hub
from evo.cli.state import load_selection, save_selection

if TYPE_CHECKING:
    from evo.common import HealthCheckType
    from evo.workspaces import BoundingBox, Workspace

app = typer.Typer(help="List and inspect Evo workspaces.")


def _parse_bounding_box(value: str | None) -> list[tuple[float, float]] | None:
    """Parse a '--bounding-box' value of the form 'lon,lat;lon,lat;...' into coordinate tuples."""
    if not value:
        return None
    points: list[tuple[float, float]] = []
    for pair in value.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        parts = pair.split(",")
        if len(parts) != 2:
            output.emit_error(
                f"Invalid --bounding-box coordinate {pair!r}. Expected 'longitude,latitude' pairs separated by ';'."
            )
        try:
            points.append((float(parts[0]), float(parts[1])))
        except ValueError:
            output.emit_error(
                f"Invalid --bounding-box coordinate {pair!r}. Expected 'longitude,latitude' pairs separated by ';'."
            )
    return points


def _bounding_box_to_data(bbox: BoundingBox | None) -> list[list[dict]] | None:
    if bbox is None:
        return None
    return [[{"longitude": c.longitude, "latitude": c.latitude} for c in ring] for ring in bbox.coordinates]


def _bounding_box_to_plain(bbox: BoundingBox | None) -> str:
    if bbox is None:
        return "-"
    rings = ["[" + ", ".join(f"({c.longitude},{c.latitude})" for c in ring) + "]" for ring in bbox.coordinates]
    return "; ".join(rings)


def _workspace_to_data(ws: Workspace) -> dict:
    return {
        "id": str(ws.id),
        "display_name": ws.display_name,
        "description": ws.description,
        "role": ws.user_role.name if ws.user_role else None,
        "org_id": str(ws.org_id),
        "hub_url": ws.hub_url,
        "created_at": ws.created_at.isoformat(),
        "created_by": ws.created_by.name or ws.created_by.email,
        "updated_at": ws.updated_at.isoformat(),
        "updated_by": ws.updated_by.name or ws.updated_by.email,
        "labels": ws.labels,
        "default_coordinate_system": ws.default_coordinate_system or None,
        "bounding_box": _bounding_box_to_data(ws.bounding_box),
    }


def _workspace_to_plain_lines(ws: Workspace, *, heading: str) -> list[str]:
    return [
        f"{heading}: {ws.display_name} ({ws.id})",
        f"  Description: {ws.description or '-'}",
        f"  Role: {ws.user_role.name if ws.user_role else '-'}",
        f"  Org: {ws.org_id}",
        f"  Hub: {ws.hub_url}",
        f"  Created: {ws.created_at:%Y-%m-%d %H:%M} by {ws.created_by.name or ws.created_by.email}",
        f"  Updated: {ws.updated_at:%Y-%m-%d %H:%M} by {ws.updated_by.name or ws.updated_by.email}",
        f"  Labels: {', '.join(ws.labels) if ws.labels else '-'}",
        f"  Default coordinate system: {ws.default_coordinate_system or '-'}",
        f"  Bounding box: {_bounding_box_to_plain(ws.bounding_box)}",
    ]


async def _do_list(
    org_id: UUID | None,
    hub_code: str | None,
    name: str | None,
    limit: int,
    fetch_all: bool,
    deleted: bool,
    summary: bool,
) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            if summary:
                page = await client.list_workspaces_summary(limit=limit, name=name, deleted=deleted)
                workspaces = page.items()
            elif fetch_all:
                workspaces = await client.list_all_workspaces(name=name, deleted=deleted)
            else:
                page = await client.list_workspaces(limit=limit, name=name, deleted=deleted)
                workspaces = page.items()
        except Exception as e:
            handle_api_error(e, not_found_message="Workspace not found.")

    if summary:
        items = [{"id": str(ws.id), "display_name": ws.display_name} for ws in workspaces]
        if not items:
            output.emit({"workspaces": []}, plain="No workspaces found.")
            return
        lines = [f"Workspaces — showing {len(items)} (summary):"]
        lines.extend(f"  {ws.id}  {ws.display_name}" for ws in workspaces)
        output.emit({"workspaces": items}, plain="\n".join(lines))
        return

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

    lines = [f"Workspaces — showing {len(items)}:"]
    for ws in workspaces:
        role = ws.user_role.name if ws.user_role else "-"
        lines.append(f"  {ws.id}  {ws.display_name.ljust(30)}  {role.ljust(8)}  {ws.updated_at:%Y-%m-%d}")

    output.emit({"workspaces": items}, plain="\n".join(lines))


async def _do_get(workspace_id: UUID, org_id: UUID | None, hub_code: str | None) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            ws = await client.get_workspace(workspace_id)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

    output.emit(_workspace_to_data(ws), plain="\n".join(_workspace_to_plain_lines(ws, heading="Workspace")))


async def _do_health(org_id: UUID | None, hub_code: str | None, check_type: HealthCheckType) -> None:
    from evo.common import ServiceStatus
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            health = await client.get_service_health(check_type)
        except Exception as e:
            handle_api_error(e, not_found_message="Workspace service not found.")

    data = {
        "hub_url": hub_url,
        "status": health.status.value,
        "version": health.version,
        "dependencies": (
            {dep_name: dep_status.value for dep_name, dep_status in health.dependencies.items()}
            if health.dependencies
            else {}
        ),
    }
    lines = [
        f"Workspace service health — hub: {hub_url}",
        f"  Status: {health.status.value} ({health.status.name.lower()})",
        f"  Version: {health.version}",
    ]
    if health.dependencies:
        lines.append("  Dependencies:")
        for dep_name, dep_status in health.dependencies.items():
            lines.append(f"    - {dep_name}: {dep_status.value}")

    output.emit(data, plain="\n".join(lines))

    if health.status != ServiceStatus.HEALTHY:
        raise typer.Exit(1)


async def _do_create(
    name: str,
    org_id: UUID | None,
    hub_code: str | None,
    description: str | None,
    labels: list[str] | None,
    default_coordinate_system: str | None,
    bounding_box: list[tuple[float, float]] | None,
) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            ws = await client.create_workspace(
                name=name,
                description=description,
                labels=labels,
                default_coordinate_system=default_coordinate_system,
                bounding_box_coordinates=bounding_box,
            )
        except Exception as e:
            handle_api_error(e, not_found_message="Workspace service not found.")

    output.emit(_workspace_to_data(ws), plain="\n".join(_workspace_to_plain_lines(ws, heading="Created workspace")))


async def _do_update(
    workspace_id: UUID,
    org_id: UUID | None,
    hub_code: str | None,
    name: str | None,
    description: str | None,
    labels: list[str] | None,
    default_coordinate_system: str | None,
    bounding_box: list[tuple[float, float]] | None,
) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            ws = await client.update_workspace(
                workspace_id,
                name=name,
                description=description,
                labels=labels,
                default_coordinate_system=default_coordinate_system,
                bounding_box_coordinates=bounding_box,
            )
        except Exception as e:
            handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

    output.emit(_workspace_to_data(ws), plain="\n".join(_workspace_to_plain_lines(ws, heading="Updated workspace")))


async def _do_delete(workspace_id: UUID, org_id: UUID | None, hub_code: str | None) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            await client.delete_workspace(workspace_id)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

    output.emit({"id": str(workspace_id), "status": "deleted"}, plain=f"Deleted workspace {workspace_id}.")


async def _do_restore(workspace_id: UUID, org_id: UUID | None, hub_code: str | None) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)
        try:
            await client.restore_deleted_workspace(workspace_id)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

    output.emit({"id": str(workspace_id), "status": "restored"}, plain=f"Restored workspace {workspace_id}.")


async def _do_select(workspace_id: UUID | None, org_id: UUID | None, hub_code: str | None) -> None:
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = WorkspaceAPIClient(connector, org_id)

        if workspace_id is None:
            if not output.is_interactive():
                output.emit_error(
                    "workspace_id is required in non-interactive mode — pass it as an argument.",
                    code="missing_argument",
                )
            try:
                workspaces = await client.list_all_workspaces()
            except Exception as e:
                handle_api_error(e, not_found_message="Workspaces not found.")
            if not workspaces:
                output.emit_error("No workspaces found in your organization.")

            output.emit_panel(
                "Select workspace",
                ["Choose a workspace to set as your default for future commands."],
            )
            for i, w in enumerate(workspaces, 1):
                typer.echo(f"  {i:>3})  {w.display_name:<40}  {w.id}")
            typer.echo("")

            while True:
                raw = typer.prompt("Workspace", default="1").strip()
                try:
                    idx = int(raw)
                except ValueError:
                    typer.echo(f"  Enter a number between 1 and {len(workspaces)}.", err=True)
                    continue
                if idx < 1 or idx > len(workspaces):
                    typer.echo(f"  Enter a number between 1 and {len(workspaces)}.", err=True)
                    continue
                break

            ws = workspaces[idx - 1]
        else:
            try:
                ws = await client.get_workspace(workspace_id)
            except Exception as e:
                handle_api_error(e, not_found_message=f"Workspace {workspace_id} not found.")

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
    output.emit(
        {"id": str(ws.id), "display_name": ws.display_name},
        plain=f"Selected workspace — {ws.display_name} ({ws.id})",
    )


@app.command("list")
def list_workspaces(
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
    name: str | None = typer.Option(None, "--name", help="Filter by workspace name."),
    limit: int = typer.Option(50, "--limit", help="Page size when not using --all."),
    all: bool = typer.Option(False, "--all", help="Fetch every page of results."),  # noqa: A002
    deleted: bool = typer.Option(False, "--deleted", help="Include soft-deleted workspaces."),
    summary: bool = typer.Option(
        False, "--summary", help="Use the faster lightweight listing (id + name only). Ignored with --all."
    ),
) -> None:
    """List workspaces in the current (or specified) organization/hub."""
    asyncio.run(_do_list(org_id, hub_code, name, limit, all, deleted, summary))


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
    from evo.common import HealthCheckType

    try:
        parsed_check_type = HealthCheckType[check_type.upper()]
    except KeyError:
        output.emit_error(f"invalid --check-type {check_type!r}. Expected one of: basic, full, strict.")
    asyncio.run(_do_health(org_id, hub_code, parsed_check_type))


@app.command()
def select(
    workspace_id: Optional[UUID] = typer.Argument(None, help="Workspace UUID. Omit to choose interactively."),
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
    default_coordinate_system: str | None = typer.Option(
        None, "--default-coordinate-system", help="Default coordinate system, e.g. an EPSG code."
    ),
    bounding_box: str | None = typer.Option(
        None, "--bounding-box", help="Bounding box as 'lon,lat;lon,lat;...' (a closed polygon ring)."
    ),
) -> None:
    """Create a new workspace."""
    label_list = [label.strip() for label in labels.split(",") if label.strip()] if labels else None
    bbox = _parse_bounding_box(bounding_box)
    asyncio.run(_do_create(name, org_id, hub_code, description, label_list, default_coordinate_system, bbox))


@app.command()
def update(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID to update."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
    name: str | None = typer.Option(None, "--name", help="New workspace name."),
    description: str | None = typer.Option(None, "--description", help="New workspace description."),
    labels: str | None = typer.Option(
        None, "--labels", help="Comma-separated labels (replaces the workspace's existing labels)."
    ),
    default_coordinate_system: str | None = typer.Option(
        None, "--default-coordinate-system", help="Default coordinate system, e.g. an EPSG code."
    ),
    bounding_box: str | None = typer.Option(
        None, "--bounding-box", help="Bounding box as 'lon,lat;lon,lat;...' (a closed polygon ring)."
    ),
) -> None:
    """Update a workspace's name, description, labels, or coordinate metadata."""
    label_list = [label.strip() for label in labels.split(",") if label.strip()] if labels else None
    bbox = _parse_bounding_box(bounding_box)
    asyncio.run(
        _do_update(workspace_id, org_id, hub_code, name, description, label_list, default_coordinate_system, bbox)
    )


@app.command()
def summary(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID to summarize."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Get a summary of objects and files in a workspace."""
    asyncio.run(_do_summary(workspace_id, org_id, hub_code))


async def _do_summary(workspace_id: UUID, org_id: UUID | None, hub_code: str | None) -> None:
    from evo.files import FileAPIClient
    from evo.objects import ObjectAPIClient

    creds = await require_credentials()
    env = make_environment(creds, str(workspace_id))

    async with make_connector(creds) as connector:
        obj_client = ObjectAPIClient(environment=env, connector=connector)
        file_client = FileAPIClient(environment=env, connector=connector)

        try:
            objects = await obj_client.list_all_objects()
            files = await file_client.list_all_files()
        except Exception as e:
            output.emit_error(str(e))

    # Count objects by type
    from collections import Counter

    object_types = Counter(str(obj.schema_id) for obj in objects)
    file_extensions = Counter(obj.path.split(".")[-1] if "." in obj.path else "no-extension" for obj in files)

    data = {
        "workspace_id": str(workspace_id),
        "object_count": len(objects),
        "file_count": len(files),
        "object_types": dict(object_types),
        "file_extensions": dict(file_extensions),
    }

    lines = [
        f"Workspace Summary — {workspace_id}",
        f"  Objects: {len(objects)}",
        f"  Files: {len(files)}",
    ]
    if object_types:
        lines.append("  Objects by type:")
        for type_name, count in sorted(object_types.items(), key=lambda x: -x[1]):
            lines.append(f"    - {type_name}: {count}")
    if file_extensions:
        lines.append("  Files by extension:")
        for ext, count in sorted(file_extensions.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"    - .{ext}: {count}")

    output.emit(data, plain="\n".join(lines))


@app.command()
def delete(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID to delete."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Soft-delete a workspace."""
    if output.is_interactive() and not yes:
        typer.confirm(f"Delete workspace {workspace_id}?", abort=True)
    asyncio.run(_do_delete(workspace_id, org_id, hub_code))


@app.command()
def restore(
    workspace_id: UUID = typer.Argument(..., help="The workspace ID to restore."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Restore a soft-deleted workspace."""
    asyncio.run(_do_restore(workspace_id, org_id, hub_code))


@app.command("copy-object")
def copy_object(
    source_workspace: UUID = typer.Option(..., "--from-workspace", help="Source workspace UUID"),
    object_id: UUID = typer.Option(..., "--object", help="Object UUID to copy"),
    target_workspace: UUID = typer.Option(..., "--to-workspace", help="Target workspace UUID"),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Copy an object from one workspace to another."""
    asyncio.run(_do_copy_object(source_workspace, object_id, target_workspace, org_id, hub_code))


async def _do_copy_object(src_ws: UUID, obj_id: UUID, tgt_ws: UUID, org_id: UUID | None, hub_code: str | None) -> None:
    from evo.objects import ObjectAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        src_client = ObjectAPIClient(environment=None, connector=connector)
        tgt_client = ObjectAPIClient(environment=None, connector=connector)

        try:
            # Download from source workspace
            src_env = make_environment(creds, str(src_ws))
            src_client = ObjectAPIClient(environment=src_env, connector=connector)
            source_obj = await src_client.download_object_by_id(obj_id)

            # Create in target workspace
            tgt_env = make_environment(creds, str(tgt_ws))
            tgt_client = ObjectAPIClient(environment=tgt_env, connector=connector)
            result = await tgt_client.create_geoscience_object(
                source_obj.metadata.path, source_obj.model_dump(mode="json")
            )
        except Exception as e:
            handle_api_error(e, not_found_message="Failed to copy object")

    data = {
        "status": "success",
        "source_workspace": str(src_ws),
        "object_id": str(obj_id),
        "target_workspace": str(tgt_ws),
        "new_object_id": str(result.id),
        "path": result.path,
    }

    output.emit(
        data,
        plain=f"Copied object {obj_id} from workspace {src_ws} to {tgt_ws}\nNew object: {result.id} ({result.path})",
    )


@app.command()
def duplicate(
    source_workspace: UUID = typer.Argument(..., help="Source workspace UUID to duplicate."),
    name: str | None = typer.Option(None, "--name", help="Name for the new workspace. Defaults to '<source> (copy)'."),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Duplicate a workspace — copies metadata, all objects, and all files into a new workspace."""
    asyncio.run(_do_duplicate(source_workspace, name, org_id, hub_code))


async def _do_duplicate(
    src_ws_id: UUID, new_name: str | None, org_id: UUID | None, hub_code: str | None
) -> None:
    import tempfile
    from pathlib import Path

    from evo.files import FileAPIClient
    from evo.objects import ObjectAPIClient
    from evo.workspaces import WorkspaceAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        ws_client = WorkspaceAPIClient(connector, org_id)

        try:
            src_ws = await ws_client.get_workspace(src_ws_id)
        except Exception as e:
            handle_api_error(e, not_found_message=f"Workspace {src_ws_id} not found.")

        target_name = new_name or f"{src_ws.display_name} (copy)"

        try:
            tgt_ws = await ws_client.create_workspace(
                name=target_name,
                description=src_ws.description,
                labels=list(src_ws.labels) if src_ws.labels else None,
                default_coordinate_system=src_ws.default_coordinate_system or None,
                bounding_box_coordinates=(
                    [(c.longitude, c.latitude) for c in src_ws.bounding_box.coordinates[0]]
                    if src_ws.bounding_box and src_ws.bounding_box.coordinates
                    else None
                ),
            )
        except Exception as e:
            handle_api_error(e, not_found_message="Failed to create target workspace.")

        output.emit(
            {"step": "workspace_created", "id": str(tgt_ws.id), "display_name": tgt_ws.display_name},
            plain=f"Created workspace — {tgt_ws.display_name} ({tgt_ws.id})",
        )

        src_env = make_environment(creds, str(src_ws_id))
        tgt_env = make_environment(creds, str(tgt_ws.id))
        transport = connector.transport

        src_obj_client = ObjectAPIClient(environment=src_env, connector=connector)
        tgt_obj_client = ObjectAPIClient(environment=tgt_env, connector=connector)
        src_file_client = FileAPIClient(environment=src_env, connector=connector)
        tgt_file_client = FileAPIClient(environment=tgt_env, connector=connector)

        try:
            objects = await src_obj_client.list_all_objects()
        except Exception as e:
            handle_api_error(e, not_found_message="Failed to list objects in source workspace.")

        copied_objects = 0
        failed_objects = 0
        for obj in objects:
            try:
                full_obj = await src_obj_client.download_object_by_id(obj.id)
                obj_dict = full_obj.as_dict()
                obj_dict.pop("uuid", None)
                await tgt_obj_client.create_geoscience_object(full_obj.metadata.path, obj_dict)
                copied_objects += 1
            except Exception as exc:
                output.emit(
                    {"step": "object_error", "id": str(obj.id), "error": str(exc)},
                    plain=f"  Warning: failed to copy object {obj.id} ({obj.path}): {exc}",
                )
                failed_objects += 1

        output.emit(
            {"step": "objects_copied", "copied": copied_objects, "failed": failed_objects},
            plain=f"Objects: {copied_objects} copied, {failed_objects} failed.",
        )

        try:
            files = await src_file_client.list_all_files()
        except Exception as e:
            handle_api_error(e, not_found_message="Failed to list files in source workspace.")

        copied_files = 0
        failed_files = 0
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "transfer"
            for file_meta in files:
                try:
                    dl = await src_file_client.prepare_download_by_id(file_meta.id)
                    await dl.download_to_path(tmp_path, transport, overwrite=True)
                    ul = await tgt_file_client.prepare_upload_by_path(file_meta.path)
                    await ul.upload_from_path(tmp_path, transport)
                    copied_files += 1
                except Exception as exc:
                    output.emit(
                        {"step": "file_error", "id": str(file_meta.id), "path": file_meta.path, "error": str(exc)},
                        plain=f"  Warning: failed to copy file {file_meta.path}: {exc}",
                    )
                    failed_files += 1

        output.emit(
            {"step": "files_copied", "copied": copied_files, "failed": failed_files},
            plain=f"Files: {copied_files} copied, {failed_files} failed.",
        )

    summary = {
        "status": "success",
        "source_workspace": str(src_ws_id),
        "target_workspace": str(tgt_ws.id),
        "target_name": tgt_ws.display_name,
        "objects_copied": copied_objects,
        "objects_failed": failed_objects,
        "files_copied": copied_files,
        "files_failed": failed_files,
    }
    output.emit(
        summary,
        plain=(
            f"Duplicate complete — {src_ws.display_name} → {tgt_ws.display_name} ({tgt_ws.id})\n"
            f"  Objects: {copied_objects} copied, {failed_objects} failed\n"
            f"  Files:   {copied_files} copied, {failed_files} failed"
        ),
    )


@app.command()
def snapshot(
    workspace_id: UUID = typer.Option(..., "--workspace", help="Workspace UUID to snapshot"),
    include_data: bool = typer.Option(False, "--include-data", help="Include object data blobs in snapshot"),
    org_id: UUID | None = typer.Option(None, "--org-id", help="Organization ID (overrides current selection)."),
    hub_code: str | None = typer.Option(None, "--hub-code", help="Hub code (overrides current selection)."),
) -> None:
    """Create a snapshot of all objects in a workspace."""
    asyncio.run(_do_snapshot(workspace_id, include_data, org_id, hub_code))


async def _do_snapshot(ws_id: UUID, with_data: bool, org_id: UUID | None, hub_code: str | None) -> None:
    from datetime import datetime

    from evo.objects import ObjectAPIClient

    creds = await require_login()
    org_id, hub_code, hub_url = resolve_org_and_hub(org_id, hub_code, creds)

    async with build_connector(hub_url, creds) as connector:
        client = ObjectAPIClient(environment=None, connector=connector)
        env = make_environment(creds, str(ws_id))
        client = ObjectAPIClient(environment=env, connector=connector)

        try:
            objects = await client.list_all_objects()
        except Exception as e:
            handle_api_error(e, not_found_message="Failed to list objects")

    snapshot_data = {
        "workspace_id": str(ws_id),
        "timestamp": datetime.utcnow().isoformat(),
        "object_count": len(objects),
        "objects": [],
    }

    for obj in objects:
        obj_info = {
            "id": str(obj.id),
            "name": obj.name,
            "path": obj.path,
            "type": str(obj.schema_id),
            "version_id": obj.version_id,
            "modified_at": obj.modified_at.isoformat() if obj.modified_at else None,
        }

        if with_data:
            try:
                full_obj = await client.download_object_by_id(obj.id)
                obj_info["schema"] = full_obj.model_dump(mode="json")
            except Exception:
                pass

        snapshot_data["objects"].append(obj_info)

    output.emit(
        snapshot_data,
        plain=f"Created snapshot of workspace {ws_id} with {len(objects)} objects at {snapshot_data['timestamp']}",
    )
