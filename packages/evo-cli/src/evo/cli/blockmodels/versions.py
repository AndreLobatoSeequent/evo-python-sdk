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
from typing import Optional, Union
from uuid import UUID

import typer

from evo.blockmodels import BlockModelAPIClient
from evo.blockmodels.data import Column, ListingColumn, ListingGroup, ListingVersion, ResolvedGroup, Version
from evo.cli import output
from evo.cli._connector import make_connector, make_environment, require_credentials

app = typer.Typer(help="Manage block model versions.")


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _column_to_dict(col: Union[Column, ListingColumn]) -> dict:
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
        "columns": [_column_to_dict(c) for c in v.columns],
        "groups": [_group_to_dict(g) for g in v.groups],
    }


@app.command("list")
def list_versions(
    bm_id: str = typer.Argument(help="Block model UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """List all versions of a block model, newest first."""
    asyncio.run(_do_list(bm_id, workspace))


async def _do_list(bm_id: str, workspace: str | None) -> None:
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
        plain="\n".join(f"v{v['version_id']}  {v['created_at']}  {v['comment'] or ''}" for v in items)
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
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            version = await client.get_version(UUID(bm_id), UUID(version_uuid))
        except Exception as exc:
            output.emit_error(str(exc))

    data = _version_to_dict(version)
    output.emit(data, plain=f"v{data['version_id']}  {data['created_at']}  {data['comment'] or ''}")
