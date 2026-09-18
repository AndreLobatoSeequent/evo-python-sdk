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
from typing import TYPE_CHECKING, Optional
from uuid import UUID

import typer

from evo.cli import output
from evo.cli._connector import make_cache, make_connector, make_environment, require_credentials
from evo.cli.blockmodels._bbox import parse_bbox_option
from evo.cli.blockmodels._tables import GEOMETRY_COLUMNS, parse_key_value_option, read_table_file, write_table_file

if TYPE_CHECKING:
    from evo.blockmodels.data import BaseGridDefinition, BlockModel
    from evo.blockmodels.endpoints.models import ColumnHeaderType, GeometryColumns, RotationAxis, UpdateType

app = typer.Typer(help="Manage block models.")

_GRID_TYPES = ["regular", "fully-sub-blocked", "flexible", "octree"]


def _bbox_to_dict(bbox) -> Optional[dict]:
    if bbox is None:
        return None
    return {
        "x": [bbox.x_minmax.min, bbox.x_minmax.max],
        "y": [bbox.y_minmax.min, bbox.y_minmax.max],
        "z": [bbox.z_minmax.min, bbox.z_minmax.max],
    }


def _grid_definition_to_dict(grid: BaseGridDefinition) -> dict:
    from evo.blockmodels.data import (
        FlexibleGridDefinition,
        FullySubBlockedGridDefinition,
        OctreeGridDefinition,
        RegularGridDefinition,
    )

    data = {
        "model_origin": grid.model_origin,
        "rotations": [[axis.value, angle] for axis, angle in grid.rotations],
    }
    if isinstance(grid, RegularGridDefinition):
        data.update(type="regular", n_blocks=grid.n_blocks, block_size=grid.block_size)
    elif isinstance(grid, FullySubBlockedGridDefinition):
        data.update(
            type="fully-sub-blocked",
            n_parent_blocks=grid.n_parent_blocks,
            n_subblocks_per_parent=grid.n_subblocks_per_parent,
            parent_block_size=grid.parent_block_size,
        )
    elif isinstance(grid, FlexibleGridDefinition):
        data.update(
            type="flexible",
            n_parent_blocks=grid.n_parent_blocks,
            n_subblocks_per_parent=grid.n_subblocks_per_parent,
            parent_block_size=grid.parent_block_size,
        )
    elif isinstance(grid, OctreeGridDefinition):
        data.update(
            type="octree",
            n_parent_blocks=grid.n_parent_blocks,
            n_subblocks_per_parent=grid.n_subblocks_per_parent,
            parent_block_size=grid.parent_block_size,
        )
    else:
        data["type"] = type(grid).__name__
    return data


def _bm_to_dict(bm: BlockModel) -> dict:
    return {
        "id": str(bm.id),
        "name": bm.name,
        "description": bm.description,
        "created_at": bm.created_at.isoformat(),
        "created_by": bm.created_by.email if bm.created_by else None,
        "last_updated_at": bm.last_updated_at.isoformat(),
        "last_updated_by": bm.last_updated_by.email if bm.last_updated_by else None,
        "coordinate_reference_system": bm.coordinate_reference_system,
        "size_unit_id": bm.size_unit_id,
        "fill_subblocks": bm.fill_subblocks,
        "geoscience_object_id": str(bm.geoscience_object_id) if bm.geoscience_object_id else None,
        "bbox": _bbox_to_dict(bm.bbox),
        "grid_definition": _grid_definition_to_dict(bm.grid_definition),
        "url": bm.url,
    }


def _parse_rotations(entries: list[str]) -> list[tuple[RotationAxis, float]]:
    from evo.blockmodels.endpoints.models import RotationAxis

    rotations: list[tuple[RotationAxis, float]] = []
    for entry in entries:
        if ":" not in entry:
            output.emit_error(f"Invalid --rotation {entry!r}. Expected 'axis:angle', e.g. 'z:45'.")
        axis_str, angle_str = entry.split(":", 1)
        try:
            axis = RotationAxis(axis_str.strip().lower())
        except ValueError:
            output.emit_error(f"Invalid rotation axis {axis_str!r} in --rotation {entry!r}. Expected x, y, or z.")
        try:
            angle = float(angle_str)
        except ValueError:
            output.emit_error(f"Invalid rotation angle {angle_str!r} in --rotation {entry!r}.")
        rotations.append((axis, angle))
    if len(rotations) > 3:
        output.emit_error("at most 3 --rotation entries are allowed")
    return rotations


def _build_grid_definition(
    grid_type: str,
    origin: tuple[float, float, float],
    rotation_entries: list[str],
    n_blocks: Optional[tuple[int, int, int]],
    block_size: Optional[tuple[float, float, float]],
    n_parent_blocks: Optional[tuple[int, int, int]],
    n_subblocks: Optional[tuple[int, int, int]],
    parent_block_size: Optional[tuple[float, float, float]],
) -> BaseGridDefinition:
    from evo.blockmodels.data import (
        FlexibleGridDefinition,
        FullySubBlockedGridDefinition,
        OctreeGridDefinition,
        RegularGridDefinition,
    )

    grid_type = grid_type.strip().lower()
    if grid_type not in _GRID_TYPES:
        output.emit_error(f"Invalid --grid-type {grid_type!r}. Expected one of: {', '.join(_GRID_TYPES)}.")

    rotations = _parse_rotations(rotation_entries)

    if grid_type == "regular":
        if n_blocks is None or block_size is None:
            output.emit_error("--grid-type regular requires --n-blocks and --block-size")
        return RegularGridDefinition(
            model_origin=list(origin),
            rotations=rotations,
            n_blocks=list(n_blocks),
            block_size=list(block_size),
        )

    if n_parent_blocks is None or n_subblocks is None or parent_block_size is None:
        output.emit_error(f"--grid-type {grid_type} requires --n-parent-blocks, --n-subblocks, and --parent-block-size")

    kwargs = dict(
        model_origin=list(origin),
        rotations=rotations,
        n_parent_blocks=list(n_parent_blocks),
        n_subblocks_per_parent=list(n_subblocks),
        parent_block_size=list(parent_block_size),
    )
    if grid_type == "fully-sub-blocked":
        return FullySubBlockedGridDefinition(**kwargs)
    elif grid_type == "flexible":
        return FlexibleGridDefinition(**kwargs)
    else:  # octree
        return OctreeGridDefinition(**kwargs)


@app.command("list")
def list_block_models(
    deleted: bool = typer.Option(False, "--deleted", help="Show only deleted block models"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """List block models in the workspace."""
    asyncio.run(_do_list(deleted, workspace))


async def _do_list(deleted: bool, workspace: str | None) -> None:
    from evo.blockmodels import BlockModelAPIClient

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            models = await client.list_all_block_models(deleted=deleted or None)
        except Exception as exc:
            output.emit_error(str(exc))

    items = [_bm_to_dict(m) for m in models]
    output.emit(
        items,
        plain="\n".join(f"{m['name']}  {m['id']}" for m in items) or "No block models found.",
    )


@app.command()
def get(
    bm_id: str = typer.Argument(help="Block model UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Get metadata for a block model."""
    asyncio.run(_do_get(bm_id, workspace))


def _format_bm_plain(data: dict) -> str:
    lines = [f"{data['name']}  ({data['id']})"]
    if data.get("description"):
        lines.append(f"  Description  {data['description']}")
    g = data.get("grid_definition", {})
    gtype = g.get("type", "?")
    origin = g.get("model_origin", [])
    origin_str = ", ".join(f"{v:.3g}" for v in origin) if origin else "?"
    lines.append(f"  Grid type    {gtype}  origin [{origin_str}]")
    if gtype == "regular":
        nb = g.get("n_blocks", [])
        bs = g.get("block_size", [])
        lines.append(f"  Blocks       {' × '.join(str(v) for v in nb)}  size {' × '.join(f'{v:.3g}' for v in bs)}")
    elif gtype in ("fully-sub-blocked", "flexible", "octree"):
        npb = g.get("n_parent_blocks", [])
        nsp = g.get("n_subblocks_per_parent", [])
        pbs = g.get("parent_block_size", [])
        lines.append(
            f"  Parent blocks {' × '.join(str(v) for v in npb)}  "
            f"sub-blocks {' × '.join(str(v) for v in nsp)}  "
            f"size {' × '.join(f'{v:.3g}' for v in pbs)}"
        )
    bbox = data.get("bbox")
    if bbox:
        lines.append(
            f"  BBox         X {bbox['x'][0]:.3g}–{bbox['x'][1]:.3g}  "
            f"Y {bbox['y'][0]:.3g}–{bbox['y'][1]:.3g}  "
            f"Z {bbox['z'][0]:.3g}–{bbox['z'][1]:.3g}"
        )
    if data.get("coordinate_reference_system"):
        lines.append(f"  CRS          {data['coordinate_reference_system']}")
    created_by = data.get("created_by") or "?"
    lines.append(f"  Created      {data['created_at']}  by {created_by}")
    updated_by = data.get("last_updated_by") or "?"
    lines.append(f"  Updated      {data['last_updated_at']}  by {updated_by}")
    if data.get("url"):
        lines.append(f"  URL          {data['url']}")
    return "\n".join(lines)


async def _do_get(bm_id: str, workspace: str | None) -> None:
    from evo.blockmodels import BlockModelAPIClient

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            bm = await client.get_block_model(UUID(bm_id))
        except Exception as exc:
            output.emit_error(str(exc))

    data = _bm_to_dict(bm)
    output.emit(data, plain=_format_bm_plain(data))


@app.command()
def create(
    name: str = typer.Argument(help="Name of the block model"),
    grid_type: str = typer.Option(..., "--grid-type", help=f"Grid type: {', '.join(_GRID_TYPES)}"),
    origin: tuple[float, float, float] = typer.Option(..., "--origin", help="Model origin, e.g. --origin 0 0 0"),
    rotation: list[str] = typer.Option(
        [], "--rotation", help="'axis:angle' (axis one of x/y/z) - repeat for up to 3 rotations"
    ),
    n_blocks: Optional[tuple[int, int, int]] = typer.Option(
        None, "--n-blocks", help="[regular] Number of blocks along each axis"
    ),
    block_size: Optional[tuple[float, float, float]] = typer.Option(
        None, "--block-size", help="[regular] Size of each block along each axis"
    ),
    n_parent_blocks: Optional[tuple[int, int, int]] = typer.Option(
        None, "--n-parent-blocks", help="[sub-blocked grid types] Number of parent blocks along each axis"
    ),
    n_subblocks: Optional[tuple[int, int, int]] = typer.Option(
        None, "--n-subblocks", help="[sub-blocked grid types] Number of sub-blocks per parent along each axis"
    ),
    parent_block_size: Optional[tuple[float, float, float]] = typer.Option(
        None, "--parent-block-size", help="[sub-blocked grid types] Size of each parent block along each axis"
    ),
    description: Optional[str] = typer.Option(None, "--description", help="Block model description"),
    object_path: Optional[str] = typer.Option(
        None, "--object-path", help="Folder path in Geoscience Object Service to create the reference object in"
    ),
    crs: Optional[str] = typer.Option(None, "--crs", help="Coordinate reference system"),
    size_unit_id: Optional[str] = typer.Option(None, "--size-unit-id", help="Unit ID for the block model's blocks"),
    data: Optional[Path] = typer.Option(
        None, "--data", help="Local .csv or .parquet file of initial column data to populate the block model with"
    ),
    units: list[str] = typer.Option(
        [], "--units", help="'column=unit_id' for columns in --data - repeat for multiple columns"
    ),
    comment: Optional[str] = typer.Option(None, "--comment", help="Comment describing the initial data"),
    fill_subblocks: bool = typer.Option(False, "--fill-subblocks", help="Default fill_subblocks behaviour"),
    cache_dir: Optional[str] = typer.Option(
        None, "--cache-dir", help="Local cache directory for uploads (default: ~/.evo/cache)"
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Create a new block model, optionally populated with initial column data from --data."""
    grid_definition = _build_grid_definition(
        grid_type, origin, rotation, n_blocks, block_size, n_parent_blocks, n_subblocks, parent_block_size
    )
    initial_data = read_table_file(data) if data is not None else None
    parsed_units = parse_key_value_option(units, "--units") if units else None
    asyncio.run(
        _do_create(
            name,
            grid_definition,
            description,
            object_path,
            crs,
            size_unit_id,
            initial_data,
            parsed_units,
            comment,
            fill_subblocks,
            cache_dir,
            workspace,
        )
    )


async def _do_create(
    name: str,
    grid_definition: BaseGridDefinition,
    description: str | None,
    object_path: str | None,
    crs: str | None,
    size_unit_id: str | None,
    initial_data,
    units: dict[str, str] | None,
    comment: str | None,
    fill_subblocks: bool,
    cache_dir: str | None,
    workspace: str | None,
) -> None:
    from evo.blockmodels import BlockModelAPIClient

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    cache = make_cache(cache_dir) if initial_data is not None else None
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector, cache=cache)
        try:
            bm, version = await client.create_block_model(
                name,
                grid_definition,
                description=description,
                object_path=object_path,
                coordinate_reference_system=crs,
                size_unit_id=size_unit_id,
                initial_data=initial_data,
                units=units,
                comment=comment,
                fill_subblocks=fill_subblocks,
            )
        except Exception as exc:
            output.emit_error(str(exc))

    bm_data = _bm_to_dict(bm)
    output.emit(
        {"block_model": bm_data, "version_id": version.version_id},
        plain=f"Created '{bm_data['name']}'  {bm_data['id']}  (version {version.version_id})",
    )


@app.command()
def update(
    bm_id: str = typer.Argument(help="Block model UUID"),
    name: Optional[str] = typer.Option(None, "--name", help="New name"),
    description: Optional[str] = typer.Option(None, "--description", help="New description"),
    crs: Optional[str] = typer.Option(None, "--crs", help="New coordinate reference system"),
    size_unit_id: Optional[str] = typer.Option(None, "--size-unit-id", help="New size unit ID"),
    fill_subblocks: Optional[bool] = typer.Option(
        None, "--fill-subblocks/--no-fill-subblocks", help="Set the default fill_subblocks behaviour"
    ),
    data: Optional[Path] = typer.Option(
        None, "--data", help="Local .csv or .parquet file to upload as new or updated column data"
    ),
    new_column: list[str] = typer.Option(
        [], "--new-column", help="Column in --data to add as new — repeat for multiple (default: all columns)"
    ),
    update_column: list[str] = typer.Option(
        [], "--update-column", help="Column in --data to update existing values — repeat for multiple"
    ),
    delete_column: list[str] = typer.Option(
        [], "--delete-column", help="Column to delete from the block model — repeat for multiple"
    ),
    units: list[str] = typer.Option(
        [], "--units", help="'column=unit_id' for new columns in --data — repeat for multiple"
    ),
    update_type: str = typer.Option(
        "replace", "--update-type", help="How updates overwrite existing data: 'replace' or 'merge'"
    ),
    cache_dir: Optional[str] = typer.Option(
        None, "--cache-dir", help="Local cache directory for uploads (default: ~/.evo/cache)"
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Update a block model's metadata and/or column data.

    Metadata options (--name, --description, --crs, --size-unit-id, --fill-subblocks) are applied first.

    Column data upload via --data:
      - No column flags: all non-geometry columns in the file are updated (round-trip friendly).
      - --new-column: add columns that don't yet exist in the block model.
      - --update-column: update specific existing columns.
      - --delete-column: remove columns; can be combined with --data or used alone.
    """
    from evo.blockmodels.endpoints.models import UpdateType

    metadata_updates = {
        k: v
        for k, v in {
            "name": name,
            "description": description,
            "coordinate_reference_system": crs,
            "size_unit_id": size_unit_id,
            "fill_subblocks": fill_subblocks,
        }.items()
        if v is not None
    }
    has_data_op = data is not None or bool(delete_column)
    if not metadata_updates and not has_data_op:
        output.emit_error("provide at least one option to update (metadata or --data/--delete-column)")

    try:
        update_type_enum = UpdateType(update_type)
    except ValueError:
        output.emit_error(f"Invalid --update-type {update_type!r}. Expected 'replace' or 'merge'.")

    parsed_units = parse_key_value_option(units, "--units") if units else None
    table = read_table_file(data) if data is not None else None
    asyncio.run(
        _do_update(
            bm_id,
            metadata_updates,
            table,
            new_column,
            update_column,
            delete_column,
            parsed_units,
            update_type_enum,
            cache_dir,
            workspace,
        )
    )


async def _do_update(
    bm_id: str,
    metadata_updates: dict,
    table,
    new_columns: list[str],
    update_columns: list[str],
    delete_columns: list[str],
    units: dict[str, str] | None,
    update_type: UpdateType,
    cache_dir: str | None,
    workspace: str | None,
) -> None:
    from evo.blockmodels import BlockModelAPIClient
    from evo.blockmodels.endpoints.models import UpdateBlockModel

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    cache = make_cache(cache_dir) if (table is not None) else None
    version = None
    effective_update_columns: set[str] = set()

    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector, cache=cache)
        bm_uuid = UUID(bm_id)

        if metadata_updates:
            try:
                bm = await client.update_block_model_metadata(bm_uuid, UpdateBlockModel(**metadata_updates))
            except Exception as exc:
                output.emit_error(str(exc))
        else:
            try:
                bm = await client.get_block_model(bm_uuid)
            except Exception as exc:
                output.emit_error(str(exc))

        if table is not None:
            has_column_spec = bool(new_columns or update_columns)
            try:
                if has_column_spec or delete_columns:
                    # Explicit column categorisation: new, update, delete
                    if not new_columns and not update_columns:
                        output.emit_error(
                            "--delete-column with --data requires at least one --new-column or --update-column"
                        )
                    effective_update_columns = set(update_columns)
                    version = await client.update_block_model_columns(
                        bm_uuid,
                        table,
                        new_columns=new_columns,
                        update_columns=effective_update_columns or None,
                        delete_columns=set(delete_columns) if delete_columns else None,
                        units=units,
                        update_type=update_type,
                    )
                else:
                    # No column spec — treat all non-geometry table columns as updates.
                    # This is the right default for round-trip workflows (query → upload).
                    # Use --new-column for genuinely new columns that don't yet exist.
                    effective_update_columns = set(table.schema.names) - GEOMETRY_COLUMNS
                    if not effective_update_columns:
                        output.emit_error(
                            "No data columns found in file. "
                            "Use --new-column or --update-column to specify columns explicitly."
                        )
                    version = await client.update_block_model_columns(
                        bm_uuid,
                        table,
                        new_columns=[],
                        update_columns=effective_update_columns,
                        units=units,
                        update_type=update_type,
                    )
            except Exception as exc:
                output.emit_error(str(exc))
        elif delete_columns:
            try:
                version = await client.delete_block_model_columns(bm_uuid, delete_columns)
            except Exception as exc:
                output.emit_error(str(exc))

    bm_data = _bm_to_dict(bm)
    result: dict = {"block_model": bm_data}
    if metadata_updates:
        result["metadata_changes"] = metadata_updates
    if version is not None:
        result["version_id"] = version.version_id
        result["version_uuid"] = str(version.version_uuid)
    if new_columns:
        result["columns_added"] = new_columns
    if effective_update_columns:
        result["columns_updated"] = sorted(effective_update_columns)
    if delete_columns:
        result["columns_deleted"] = delete_columns

    output.emit(
        result,
        plain=_format_update_plain(
            bm_data, metadata_updates, version, new_columns, effective_update_columns, delete_columns
        ),
    )


def _format_update_plain(
    bm_data: dict,
    metadata_updates: dict,
    version,
    new_columns: list[str],
    update_columns: set[str],
    delete_columns: list[str],
) -> str:
    lines = [f"Updated '{bm_data['name']}'  ({bm_data['id']})"]
    if metadata_updates:
        _META_LABELS = {
            "name": "name",
            "description": "description",
            "coordinate_reference_system": "CRS",
            "size_unit_id": "size unit",
            "fill_subblocks": "fill subblocks",
        }
        changes = "  ".join(f"{_META_LABELS.get(k, k)} → {v!r}" for k, v in metadata_updates.items())
        lines.append(f"  Metadata     {changes}")
    if version is not None:
        lines.append(f"  New version  v{version.version_id}  {version.version_uuid}")
    if new_columns:
        lines.append(f"  Added   ({len(new_columns)})  {', '.join(new_columns)}")
    if update_columns:
        cols = sorted(update_columns)
        lines.append(f"  Updated ({len(cols)})  {', '.join(cols)}")
    if delete_columns:
        lines.append(f"  Deleted ({len(delete_columns)})  {', '.join(delete_columns)}")
    return "\n".join(lines)


@app.command()
def delete(
    bm_id: str = typer.Argument(help="Block model UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Delete a block model."""
    if output.is_interactive() and not yes:
        typer.confirm(f"Delete block model '{bm_id}'?", abort=True)
    asyncio.run(_do_delete(bm_id, workspace))


async def _do_delete(bm_id: str, workspace: str | None) -> None:
    from evo.blockmodels import BlockModelAPIClient

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            await client.delete_block_model(UUID(bm_id))
        except Exception as exc:
            output.emit_error(str(exc))

    output.emit({"status": "deleted", "block_model": bm_id}, plain=f"Deleted '{bm_id}'.")


@app.command()
def health(
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Check the health of the Block Model Service."""
    asyncio.run(_do_health(workspace))


async def _do_health(workspace: str | None) -> None:
    from evo.blockmodels import BlockModelAPIClient

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            health_status = await client.get_service_health()
        except Exception as exc:
            output.emit_error(str(exc))

    data = {
        "service": health_status.service,
        "status": health_status.status.value,
        "status_code": health_status.status_code,
        "version": health_status.version,
    }
    output.emit(data, plain=f"{data['service']}: {data['status']} (v{data['version']})")


@app.command()
def query(
    bm_id: str = typer.Argument(help="Block model UUID"),
    column: list[str] = typer.Option(
        ..., "--column", help="Column title or UUID to query - repeat --column for multiple columns"
    ),
    output_path: Path = typer.Option(..., "--output", help="Local .csv or .parquet file to write the result to"),
    version: Optional[str] = typer.Option(None, "--version", help="Version UUID to query (default: latest)"),
    bbox_ijk: Optional[str] = typer.Option(
        None, "--bbox-ijk", help="'i0,i1,j0,j1,k0,k1' bounding box (default: entire block model)"
    ),
    bbox_xyz: Optional[str] = typer.Option(
        None, "--bbox-xyz", help="'x0,x1,y0,y1,z0,z1' bounding box (default: entire block model)"
    ),
    geometry_columns: str = typer.Option("coordinates", "--geometry-columns", help="'coordinates' or 'indices'"),
    column_headers: str = typer.Option("uuid", "--column-headers", help="'uuid' or 'title'"),
    include_null_rows: bool = typer.Option(
        False, "--include-null-rows", help="Include rows where all queried values are null"
    ),
    cache_dir: Optional[str] = typer.Option(
        None, "--cache-dir", help="Local cache directory for query results (default: ~/.evo/cache)"
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Query block model column data and write the result to a local .csv or .parquet file."""
    from evo.blockmodels.endpoints.models import ColumnHeaderType, GeometryColumns

    bbox = parse_bbox_option(bbox_ijk, bbox_xyz)
    try:
        geometry_columns_enum = GeometryColumns(geometry_columns)
    except ValueError:
        output.emit_error(f"Invalid --geometry-columns {geometry_columns!r}. Expected 'coordinates' or 'indices'.")
    _column_headers_map = {"uuid": ColumnHeaderType.id, "title": ColumnHeaderType.name}
    if column_headers not in _column_headers_map:
        output.emit_error(f"Invalid --column-headers {column_headers!r}. Expected 'uuid' or 'title'.")
    column_headers_enum = _column_headers_map[column_headers]
    asyncio.run(
        _do_query(
            bm_id,
            column,
            output_path,
            version,
            bbox,
            geometry_columns_enum,
            column_headers_enum,
            include_null_rows,
            cache_dir,
            workspace,
        )
    )


async def _do_query(
    bm_id: str,
    columns: list[str],
    output_path: Path,
    version: str | None,
    bbox,
    geometry_columns: GeometryColumns,
    column_headers: ColumnHeaderType,
    include_null_rows: bool,
    cache_dir: str | None,
    workspace: str | None,
) -> None:
    from evo.blockmodels import BlockModelAPIClient

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    cache = make_cache(cache_dir)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector, cache=cache)
        try:
            table = await client.query_block_model_as_table(
                UUID(bm_id),
                columns,
                bbox=bbox,
                version_uuid=UUID(version) if version else None,
                geometry_columns=geometry_columns,
                column_headers=column_headers,
                exclude_null_rows=not include_null_rows,
            )
        except Exception as exc:
            output.emit_error(str(exc))

    write_table_file(table, output_path)
    output.emit(
        {"status": "written", "path": str(output_path), "rows": table.num_rows},
        plain=f"Wrote {table.num_rows} row(s) to '{output_path}'.",
    )
