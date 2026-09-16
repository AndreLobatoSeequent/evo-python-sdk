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
from evo.objects.typed import object_from_uuid
from evo.objects.typed.pointset import PointSetData, PointSet
from evo.objects.typed.line_segments import LineSegmentsData, LineSegments
from evo.objects.typed.downhole import DownholeCollectionData, DownholeCollection
from evo.widgets import get_portal_url, get_viewer_url
from evo.common import StaticContext

from evo.cli import output
from evo.cli._connector import make_connector, make_environment, require_credentials

import pandas as pd

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
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
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
    content: bool = typer.Option(False, "--content", help="Include full object definition/schema"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Get metadata for a geoscience object."""
    if not path and not id:
        output.emit_error("provide --path or --id")
    if path and id:
        output.emit_error("provide only one of --path or --id")
    asyncio.run(_do_get(path, id, version, content, workspace))


async def _do_get(path: str | None, obj_id: str | None, version: str | None, include_content: bool, workspace: str | None) -> None:
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

    if include_content:
        # Include the full object definition/schema
        try:
            # Get the full object definition by serializing the downloaded object
            data = downloaded.model_dump(mode="json")
        except Exception:
            # Fallback: just include metadata
            data = _meta_to_dict(meta)
            data["__content_warning"] = "Full content unavailable; showing metadata only"
    else:
        data = _meta_to_dict(meta)

    output.emit(
        data,
        plain=f"{meta.path}  [{meta.schema_id}]  v{meta.version_id}  modified {meta.modified_at.isoformat()}",
    )


@app.command()
def versions(
    path: Optional[str] = typer.Option(None, "--path", help="Object path"),
    id: Optional[str] = typer.Option(None, "--id", help="Object UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
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
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
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
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
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


@app.command("generate-links")
def generate_links(
    object_ids: list[str] = typer.Argument(..., help="Object UUIDs to generate links for"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Generate viewer and portal links for one or more objects."""
    if not object_ids:
        output.emit_error("provide at least one object UUID")
    asyncio.run(_do_generate_links(object_ids, workspace))


async def _do_generate_links(object_ids: list[str], workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        context = StaticContext.from_environment(env, connector)
        try:
            # Resolve all objects in parallel
            import asyncio
            resolved_objects = await asyncio.gather(
                *[object_from_uuid(context, obj_id) for obj_id in object_ids],
                return_exceptions=True
            )
        except Exception as exc:
            output.emit_error(str(exc))

    # Filter out any errors and deduplicate
    objects = [
        obj for obj in resolved_objects
        if not isinstance(obj, Exception)
    ]
    unique_ids = list(dict.fromkeys(str(obj.metadata.id) for obj in objects))

    if not objects:
        output.emit_error("Could not resolve any objects")

    try:
        viewer_url = get_viewer_url(
            org_id=str(env.org_id),
            workspace_id=str(env.workspace_id),
            object_ids=unique_ids,
            hub_url=env.hub_url,
        )
    except Exception as exc:
        output.emit_error(str(exc))

    object_links = []
    for obj in objects:
        try:
            portal_url = get_portal_url(
                org_id=str(env.org_id),
                workspace_id=str(env.workspace_id),
                object_id=str(obj.metadata.id),
                hub_url=env.hub_url,
            )
            object_links.append({
                "id": str(obj.metadata.id),
                "name": getattr(obj, "name", str(obj.metadata.id)),
                "type": str(obj.metadata.schema_id),
                "portal_url": portal_url,
            })
        except Exception:
            object_links.append({
                "id": str(obj.metadata.id),
                "name": getattr(obj, "name", str(obj.metadata.id)),
                "type": str(obj.metadata.schema_id),
            })

    data = {
        "status": "success",
        "viewer_url": viewer_url,
        "object_count": len(objects),
        "objects": object_links,
    }

    lines = [
        f"Generated links for {len(objects)} object(s)",
        f"Viewer: {viewer_url}",
    ]
    output.emit(data, plain="\n".join(lines))


@app.command()
def create(
    schema: str = typer.Argument(..., help="Object schema as JSON string or path to JSON file"),
    path: Optional[str] = typer.Option(None, "--path", help="Object path in workspace (defaults to 'name' from schema)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Create a new geoscience object from a schema definition."""
    asyncio.run(_do_create(schema, path, workspace))


async def _do_create(schema_input: str, obj_path: str | None, workspace: str | None) -> None:
    import json

    # Parse schema from JSON string or file
    schema_data = None
    try:
        # Try parsing as JSON string first
        schema_data = json.loads(schema_input)
    except json.JSONDecodeError:
        # Try reading from file
        try:
            with open(schema_input, 'r') as f:
                schema_data = json.load(f)
        except (FileNotFoundError, IOError, json.JSONDecodeError) as e:
            output.emit_error(f"Invalid schema: {e}")

    if not schema_data:
        output.emit_error("Schema is empty or invalid")

    # Determine the object path
    path_to_use = obj_path or schema_data.get("name")
    if not path_to_use:
        output.emit_error("Object path required: provide --path or include 'name' in schema")

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = ObjectAPIClient(environment=env, connector=connector)
        try:
            result = await client.create_geoscience_object(path_to_use, schema_data)
        except Exception as exc:
            output.emit_error(str(exc))

    data = _meta_to_dict(result)
    output.emit(
        data,
        plain=f"Created '{result.path}' [{result.schema_id}] ({result.id})"
    )


@app.command("create-pointset")
def create_pointset(
    csv_file: str = typer.Option(..., "--from-csv", help="Path to CSV file with point data (requires x, y, z columns)"),
    name: Optional[str] = typer.Option(None, "--name", help="PointSet name (defaults to CSV filename)"),
    crs: Optional[str] = typer.Option(None, "--crs", help="Coordinate Reference System (EPSG code or WKT)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Create a PointSet object from a CSV file with x, y, z coordinates."""
    asyncio.run(_do_create_pointset(csv_file, name, crs, workspace))


async def _do_create_pointset(csv_path: str, obj_name: str | None, crs: str | None, workspace: str | None) -> None:
    try:
        # Read CSV file
        df = pd.read_csv(csv_path)
    except Exception as e:
        output.emit_error(f"Failed to read CSV: {e}")

    # Validate required columns
    required_cols = {'x', 'y', 'z'}
    if not required_cols.issubset(set(col.lower() for col in df.columns)):
        output.emit_error(f"CSV must contain 'x', 'y', 'z' columns. Found: {list(df.columns)}")

    # Normalize column names to lowercase
    df.columns = [col.lower() for col in df.columns]

    # Determine object name
    name_to_use = obj_name or csv_path.split('\\')[-1].replace('.csv', '')

    try:
        # Create PointSetData object
        pointset_data = PointSetData(
            name=name_to_use,
            locations=df,
            coordinate_reference_system=crs or "unspecified",
        )
    except Exception as e:
        output.emit_error(f"Failed to create PointSet data: {e}")

    creds = await require_credentials()
    env = make_environment(creds, workspace)

    async with make_connector(creds) as connector:
        context = StaticContext.from_environment(env, connector)
        try:
            # Create the PointSet using the typed API
            result = await PointSet.create(context=context, data=pointset_data)
        except Exception as exc:
            output.emit_error(f"Failed to create PointSet: {exc}")

    # Format output
    data = {
        "id": str(result.metadata.id),
        "name": result.name,
        "path": result.metadata.path,
        "type": str(result.metadata.schema_id),
        "version_id": result.metadata.version_id,
        "source": "CSV import",
        "row_count": len(df),
        "columns": list(df.columns),
    }

    output.emit(
        data,
        plain=f"Created PointSet '{result.name}' with {len(df)} points and {len(df.columns)} attributes ({result.metadata.id})"
    )


@app.command("create-line-segments")
def create_line_segments(
    csv_file: str = typer.Option(..., "--from-csv", help="Path to CSV file (requires vertex_index, x, y, z columns)"),
    name: Optional[str] = typer.Option(None, "--name", help="LineSegments name (defaults to CSV filename)"),
    crs: Optional[str] = typer.Option(None, "--crs", help="Coordinate Reference System (EPSG code or WKT)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Create a LineSegments object from a CSV file with vertex and coordinate data."""
    asyncio.run(_do_create_line_segments(csv_file, name, crs, workspace))


async def _do_create_line_segments(csv_path: str, obj_name: str | None, crs: str | None, workspace: str | None) -> None:
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        output.emit_error(f"Failed to read CSV: {e}")

    required_cols = {'vertex_index', 'x', 'y', 'z'}
    if not required_cols.issubset(set(col.lower() for col in df.columns)):
        output.emit_error(f"CSV must contain vertex_index, x, y, z columns. Found: {list(df.columns)}")

    df.columns = [col.lower() for col in df.columns]
    name_to_use = obj_name or csv_path.split('\\')[-1].replace('.csv', '')

    try:
        line_segs_data = LineSegmentsData(
            name=name_to_use,
            vertices=df,
            coordinate_reference_system=crs or "unspecified",
        )
    except Exception as e:
        output.emit_error(f"Failed to create LineSegments data: {e}")

    creds = await require_credentials()
    env = make_environment(creds, workspace)

    async with make_connector(creds) as connector:
        context = StaticContext.from_environment(env, connector)
        try:
            result = await LineSegments.create(context=context, data=line_segs_data)
        except Exception as exc:
            output.emit_error(f"Failed to create LineSegments: {exc}")

    data = {
        "id": str(result.metadata.id),
        "name": result.name,
        "path": result.metadata.path,
        "type": str(result.metadata.schema_id),
        "source": "CSV import",
        "vertex_count": len(df),
        "columns": list(df.columns),
    }

    output.emit(
        data,
        plain=f"Created LineSegments '{result.name}' with {len(df)} vertices ({result.metadata.id})"
    )


@app.command("create-downhole-collection")
def create_downhole_collection(
    csv_file: str = typer.Option(..., "--from-csv", help="Path to CSV file (requires hole_id, x, y, z columns)"),
    name: Optional[str] = typer.Option(None, "--name", help="DownholeCollection name (defaults to CSV filename)"),
    crs: Optional[str] = typer.Option(None, "--crs", help="Coordinate Reference System (EPSG code or WKT)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Create a DownholeCollection object from a CSV file with downhole collar data."""
    asyncio.run(_do_create_downhole_collection(csv_file, name, crs, workspace))


async def _do_create_downhole_collection(csv_path: str, obj_name: str | None, crs: str | None, workspace: str | None) -> None:
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        output.emit_error(f"Failed to read CSV: {e}")

    required_cols = {'hole_id', 'x', 'y', 'z'}
    if not required_cols.issubset(set(col.lower() for col in df.columns)):
        output.emit_error(f"CSV must contain hole_id, x, y, z columns. Found: {list(df.columns)}")

    df.columns = [col.lower() for col in df.columns]
    name_to_use = obj_name or csv_path.split('\\')[-1].replace('.csv', '')

    try:
        downhole_data = DownholeCollectionData(
            name=name_to_use,
            collars=df,
            coordinate_reference_system=crs or "unspecified",
        )
    except Exception as e:
        output.emit_error(f"Failed to create DownholeCollection data: {e}")

    creds = await require_credentials()
    env = make_environment(creds, workspace)

    async with make_connector(creds) as connector:
        context = StaticContext.from_environment(env, connector)
        try:
            result = await DownholeCollection.create(context=context, data=downhole_data)
        except Exception as exc:
            output.emit_error(f"Failed to create DownholeCollection: {exc}")

    data = {
        "id": str(result.metadata.id),
        "name": result.name,
        "path": result.metadata.path,
        "type": str(result.metadata.schema_id),
        "source": "CSV import",
        "hole_count": len(df),
        "columns": list(df.columns),
    }

    output.emit(
        data,
        plain=f"Created DownholeCollection '{result.name}' with {len(df)} boreholes ({result.metadata.id})"
    )
