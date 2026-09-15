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

from evo.blockmodels import BlockModelAPIClient
from evo.blockmodels.data import (
    BaseGridDefinition,
    BlockModel,
    FlexibleGridDefinition,
    FullySubBlockedGridDefinition,
    OctreeGridDefinition,
    RegularGridDefinition,
)
from evo.blockmodels.endpoints.models import RotationAxis, UpdateBlockModel
from evo.cli import output
from evo.cli._connector import make_connector, make_environment, require_credentials

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
        output.emit_error(
            f"--grid-type {grid_type} requires --n-parent-blocks, --n-subblocks, and --parent-block-size"
        )

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


async def _do_get(bm_id: str, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            bm = await client.get_block_model(UUID(bm_id))
        except Exception as exc:
            output.emit_error(str(exc))

    data = _bm_to_dict(bm)
    output.emit(data, plain=f"{data['name']}  {data['id']}  updated {data['last_updated_at']}")


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
    comment: Optional[str] = typer.Option(None, "--comment", help="Comment describing the initial data"),
    fill_subblocks: bool = typer.Option(False, "--fill-subblocks", help="Default fill_subblocks behaviour"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Create a new block model."""
    grid_definition = _build_grid_definition(
        grid_type, origin, rotation, n_blocks, block_size, n_parent_blocks, n_subblocks, parent_block_size
    )
    asyncio.run(
        _do_create(
            name, grid_definition, description, object_path, crs, size_unit_id, comment, fill_subblocks, workspace
        )
    )


async def _do_create(
    name: str,
    grid_definition: BaseGridDefinition,
    description: str | None,
    object_path: str | None,
    crs: str | None,
    size_unit_id: str | None,
    comment: str | None,
    fill_subblocks: bool,
    workspace: str | None,
) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            bm, version = await client.create_block_model(
                name,
                grid_definition,
                description=description,
                object_path=object_path,
                coordinate_reference_system=crs,
                size_unit_id=size_unit_id,
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
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Update a block model's metadata."""
    updates = {
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
    if not updates:
        output.emit_error("provide at least one field to update")
    asyncio.run(_do_update(bm_id, updates, workspace))


async def _do_update(bm_id: str, updates: dict, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            bm = await client.update_block_model_metadata(UUID(bm_id), UpdateBlockModel(**updates))
        except Exception as exc:
            output.emit_error(str(exc))

    data = _bm_to_dict(bm)
    output.emit(data, plain=f"Updated '{data['name']}'  {data['id']}")


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
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            await client.delete_block_model(UUID(bm_id))
        except Exception as exc:
            output.emit_error(str(exc))

    output.emit({"status": "deleted", "block_model": bm_id}, plain=f"Deleted '{bm_id}'.")
