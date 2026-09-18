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
from typing import TYPE_CHECKING, Optional, Union
from uuid import UUID

import typer

from evo.cli import output
from evo.cli._connector import make_connector, make_environment, require_credentials
from evo.cli.blockmodels._bbox import parse_bbox_option

if TYPE_CHECKING:
    from evo.blockmodels.data import Column, ListingColumn, ListingGroup, ListingVersion, ResolvedGroup, Version

app = typer.Typer(help="Manage block model versions.")


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _column_to_dict(col: Union[Column, ListingColumn]) -> dict:
    from evo.blockmodels.data import Column

    data = {
        "col_id": col.col_id,
        "title": col.title,
        "data_type": _enum_value(col.data_type),
        "unit_id": col.unit_id,
        "group_uuid": str(col.group_uuid) if col.group_uuid else None,
    }
    if isinstance(col, Column):
        data["tags"] = col.tags
    return data


def _group_to_dict(group: Union[ResolvedGroup, ListingGroup]) -> dict:
    from evo.blockmodels.data import ResolvedGroup

    data = {
        "group_uuid": str(group.group_uuid),
        "title": group.title,
        "is_hidden": group.is_hidden,
        "parent_group_uuid": str(group.parent_group_uuid) if group.parent_group_uuid else None,
        "missing_column_policy": _enum_value(group.missing_column_policy),
        "resolved_missing_column_policy": _enum_value(group.resolved_missing_column_policy),
    }
    if isinstance(group, ResolvedGroup):
        data["tags"] = group.tags
    return data


def _bbox_ijk_to_dict(bbox) -> dict | None:
    if bbox is None:
        return None
    return {
        "i": [bbox.i_minmax.min, bbox.i_minmax.max],
        "j": [bbox.j_minmax.min, bbox.j_minmax.max],
        "k": [bbox.k_minmax.min, bbox.k_minmax.max],
    }


def _version_to_dict(v: Union[Version, ListingVersion]) -> dict:
    return {
        "bm_uuid": str(v.bm_uuid),
        "version_id": v.version_id,
        "version_uuid": str(v.version_uuid),
        "parent_version_id": v.parent_version_id,
        "base_version_id": v.base_version_id,
        "geoscience_version_id": v.geoscience_version_id,
        "created_at": v.created_at.isoformat(),
        "created_by": v.created_by.email if v.created_by else None,
        "comment": v.comment,
        "bbox": _bbox_ijk_to_dict(v.bbox),
        "columns": [_column_to_dict(c) for c in v.columns],
        "groups": [_group_to_dict(g) for g in v.groups],
    }


def _format_version_plain(data: dict) -> str:
    lines = [f"v{data['version_id']}  {data['version_uuid']}"]
    lines.append(f"  Block model  {data['bm_uuid']}")
    created_by = data.get("created_by") or "?"
    lines.append(f"  Created      {data['created_at']}  by {created_by}")
    if data.get("comment"):
        lines.append(f"  Comment      {data['comment']}")
    parent = data.get("parent_version_id")
    if parent is not None:
        lines.append(f"  Parent       v{parent}")
    bbox = data.get("bbox")
    if bbox:
        lines.append(
            f"  BBox (IJK)   I {bbox['i'][0]}–{bbox['i'][1]}"
            f"  J {bbox['j'][0]}–{bbox['j'][1]}"
            f"  K {bbox['k'][0]}–{bbox['k'][1]}"
        )
    columns = data.get("columns", [])
    groups = {g["group_uuid"]: g for g in data.get("groups", []) if not g.get("is_hidden")}
    lines.append(f"  Columns ({len(columns)})")
    # Group columns by their group, preserving insertion order
    grouped: dict[str | None, list[dict]] = {}
    for col in columns:
        gid = col.get("group_uuid")
        grouped.setdefault(gid, []).append(col)
    for gid, cols in grouped.items():
        if gid and gid in groups:
            lines.append(f"    [{groups[gid]['title']}]")
            indent = "      "
        else:
            indent = "    "
        for col in cols:
            unit = f"  {col['unit_id']}" if col.get("unit_id") else ""
            lines.append(f"{indent}{col['title']:<30}  {col['data_type']}{unit}")
    return "\n".join(lines)


@app.command("list")
def list_versions(
    bm_id: str = typer.Argument(help="Block model UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """List all versions of a block model, newest first."""
    asyncio.run(_do_list(bm_id, workspace))


async def _do_list(bm_id: str, workspace: str | None) -> None:
    from evo.blockmodels import BlockModelAPIClient

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            versions = await client.list_all_versions(UUID(bm_id))
        except Exception as exc:
            output.emit_error(str(exc))

    items = [_version_to_dict(v) for v in versions]
    output.emit(
        items,
        plain="\n".join(
            f"v{v['version_id']}  {v['version_uuid']}  {v['created_at']}  {v['comment'] or ''}" for v in items
        )
        or "No versions found.",
    )


@app.command()
def get(
    bm_id: str = typer.Argument(help="Block model UUID"),
    version_uuid: str = typer.Argument(help="Version UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Get a single version of a block model, including each column's tags."""
    asyncio.run(_do_get(bm_id, version_uuid, workspace))


async def _do_get(bm_id: str, version_uuid: str, workspace: str | None) -> None:
    from evo.blockmodels import BlockModelAPIClient

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            version = await client.get_version(UUID(bm_id), UUID(version_uuid))
        except Exception as exc:
            output.emit_error(str(exc))

    data = _version_to_dict(version)
    output.emit(data, plain=_format_version_plain(data))


def _format_deltas_plain(data: dict) -> str:
    n_new = len(data.get("new_deltas", []))
    n_upd = len(data.get("update_deltas", []))
    n_del = len(data.get("delete_deltas", []))
    lines = [f"Changes found — new versions: {n_new}  updated: {n_upd}  deleted: {n_del}"]
    for vd in data.get("version_data", []):
        vid = vd.get("version_id", "?")
        vuuid = vd.get("version_uuid", "?")
        cols = vd.get("update_columns", {})
        new_cols = cols.get("new", [])
        upd_cols = cols.get("update", [])
        del_cols = cols.get("delete", [])
        rename_cols = cols.get("rename", [])
        if not (new_cols or upd_cols or del_cols or rename_cols):
            continue
        lines.append(f"\n  v{vid}  {vuuid}")
        for c in new_cols:
            lines.append(f"    + {c.get('title', c.get('col_id', '?'))}  ({c.get('data_type', '?')})")
        for col_id in upd_cols:
            lines.append(f"    ~ {col_id}")
        for col_id in del_cols:
            lines.append(f"    - {col_id}")
        for r in rename_cols:
            lines.append(f"    > {r.get('col_id', '?')} → {r.get('new_title', '?')}")
    return "\n".join(lines)


@app.command()
def deltas(
    bm_id: str = typer.Argument(help="Block model UUID"),
    since_version: str = typer.Option(..., "--since-version", help="Version UUID to search for changes after"),
    column: list[str] = typer.Option(
        ["*"], "--column", help="Column title/UUID to check, or '*' for all - repeat for multiple columns"
    ),
    end_version: Optional[str] = typer.Option(
        None, "--end-version", help="Last version UUID to search up to (default: latest)"
    ),
    bbox_ijk: Optional[str] = typer.Option(None, "--bbox-ijk", help="'i0,i1,j0,j1,k0,k1' bounding box"),
    bbox_xyz: Optional[str] = typer.Option(None, "--bbox-xyz", help="'x0,x1,y0,y1,z0,z1' bounding box"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Check for changes to a block model since a given version, within a bounding box."""
    bbox = parse_bbox_option(bbox_ijk, bbox_xyz)
    if bbox is None:
        output.emit_error("provide one of --bbox-ijk or --bbox-xyz")
    asyncio.run(_do_deltas(bm_id, since_version, column, end_version, bbox, workspace))


async def _do_deltas(
    bm_id: str,
    since_version: str,
    columns: list[str],
    end_version: str | None,
    bbox,
    workspace: str | None,
) -> None:
    from evo.blockmodels import BlockModelAPIClient
    from evo.blockmodels.endpoints.models import DeltaRequestData
    from evo.common.data import EmptyResponse

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        delta_request = DeltaRequestData(
            bbox=bbox,
            columns=columns,
            end_version_uuid=UUID(end_version) if end_version else None,
            verbose=True,  # always request full data; empty body on 200 cannot be deserialised
        )
        try:
            result = await client.get_deltas_for_block_model(UUID(since_version), UUID(bm_id), delta_request)
        except Exception as exc:
            output.emit_error(str(exc))

    if isinstance(result, EmptyResponse):
        output.emit({"status": "no_changes"}, plain="No changes found.")
        return

    data = result.model_dump(mode="json")
    output.emit(data, plain=_format_deltas_plain(data))
