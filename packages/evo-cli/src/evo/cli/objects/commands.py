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
from typing import Optional
from uuid import UUID

import typer

from evo.objects import ObjectAPIClient
from evo.objects.data import ObjectMetadata, ObjectVersion

from evo.cli import output
from evo.cli._connector import make_connector, make_environment, require_credentials

app = typer.Typer(help="Manage geoscience objects.")


def _meta_to_dict(obj: ObjectMetadata) -> dict:
    return {
        "id": str(obj.id),
        "name": obj.name,
        "path": obj.path,
        "type": str(obj.schema_id),
        "version_id": obj.version_id,
        "modified_at": obj.modified_at.isoformat(),
        "modified_by": obj.modified_by.email if obj.modified_by else None,
    }


def _version_to_dict(v: ObjectVersion) -> dict:
    return {
        "version_id": v.version_id,
        "created_at": v.created_at.isoformat(),
        "created_by": v.created_by.email if v.created_by else None,
    }


@app.command("list")
def list_objects(
    type: Optional[str] = typer.Option(None, "--type", help="Filter by schema type, e.g. PointSet"),
    deleted: bool = typer.Option(False, "--deleted", help="Show only deleted objects"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides EVO_WORKSPACE_ID)"),
) -> None:
    """List geoscience objects in the workspace."""
    asyncio.run(_do_list(type, deleted, workspace))


async def _do_list(type_filter: str | None, deleted: bool, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = ObjectAPIClient(environment=env, connector=connector)
        schema_id = [type_filter] if type_filter else None
        objects = await client.list_all_objects(schema_id=schema_id, deleted=deleted or None)

    items = [_meta_to_dict(o) for o in objects]
    output.emit(
        items,
        plain="\n".join(
            f"{o['path']}  [{o['type']}]  {o['id']}" for o in items
        ) or "No objects found.",
    )


@app.command()
def get(
    path: Optional[str] = typer.Option(None, "--path", help="Object path"),
    id: Optional[str] = typer.Option(None, "--id", help="Object UUID"),
    version: Optional[str] = typer.Option(None, "--version", help="Version ID (default: latest)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides EVO_WORKSPACE_ID)"),
) -> None:
    """Get metadata for a geoscience object."""
    if not path and not id:
        output.emit_error("provide --path or --id")
    if path and id:
        output.emit_error("provide only one of --path or --id")
    asyncio.run(_do_get(path, id, version, workspace))


async def _do_get(path: str | None, obj_id: str | None, version: str | None, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = ObjectAPIClient(environment=env, connector=connector)
        try:
            if path:
                downloaded = await client.download_object_by_path(path, version=version)
            else:
                downloaded = await client.download_object_by_id(UUID(obj_id), version=version)
        except Exception as exc:
            output.emit_error(str(exc))

    meta = downloaded.metadata
    data = _meta_to_dict(meta)
    output.emit(
        data,
        plain=f"{meta.path}  [{meta.schema_id}]  v{meta.version_id}  modified {meta.modified_at.isoformat()}",
    )


@app.command()
def versions(
    path: Optional[str] = typer.Option(None, "--path", help="Object path"),
    id: Optional[str] = typer.Option(None, "--id", help="Object UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides EVO_WORKSPACE_ID)"),
) -> None:
    """List all versions of a geoscience object."""
    if not path and not id:
        output.emit_error("provide --path or --id")
    if path and id:
        output.emit_error("provide only one of --path or --id")
    asyncio.run(_do_versions(path, id, workspace))


async def _do_versions(path: str | None, obj_id: str | None, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = ObjectAPIClient(environment=env, connector=connector)
        try:
            if path:
                vers = await client.list_versions_by_path(path)
            else:
                vers = await client.list_versions_by_id(UUID(obj_id))
        except Exception as exc:
            output.emit_error(str(exc))

    items = [_version_to_dict(v) for v in vers]
    output.emit(
        items,
        plain="\n".join(f"{v['version_id']}  {v['created_at']}" for v in items) or "No versions found.",
    )


@app.command()
def delete(
    path: Optional[str] = typer.Option(None, "--path", help="Object path"),
    id: Optional[str] = typer.Option(None, "--id", help="Object UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides EVO_WORKSPACE_ID)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Soft-delete a geoscience object."""
    if not path and not id:
        output.emit_error("provide --path or --id")
    if path and id:
        output.emit_error("provide only one of --path or --id")
    label = path or id
    if output.is_interactive() and not yes:
        typer.confirm(f"Delete object '{label}'?", abort=True)
    asyncio.run(_do_delete(path, id, workspace))


async def _do_delete(path: str | None, obj_id: str | None, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = ObjectAPIClient(environment=env, connector=connector)
        try:
            if path:
                await client.delete_object_by_path(path)
            else:
                await client.delete_object_by_id(UUID(obj_id))
        except Exception as exc:
            output.emit_error(str(exc))

    label = path or obj_id
    output.emit({"status": "deleted", "object": label}, plain=f"Deleted '{label}'.")


@app.command()
def restore(
    id: str = typer.Argument(help="Object UUID to restore"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides EVO_WORKSPACE_ID)"),
) -> None:
    """Restore a soft-deleted geoscience object."""
    asyncio.run(_do_restore(id, workspace))


async def _do_restore(obj_id: str, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = ObjectAPIClient(environment=env, connector=connector)
        try:
            result = await client.restore_geoscience_object(UUID(obj_id))
        except Exception as exc:
            output.emit_error(str(exc))

    if result is not None:
        data = _meta_to_dict(result)
        output.emit(data, plain=f"Restored to '{result.path}'.")
    else:
        output.emit({"status": "restored", "id": obj_id}, plain=f"Restored '{obj_id}'.")
