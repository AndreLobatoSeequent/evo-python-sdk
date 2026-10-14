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
from evo.cli.blockmodels._tables import GEOMETRY_COLUMNS, parse_key_value_option, read_table_file
from evo.cli.blockmodels.versions import _version_to_dict

if TYPE_CHECKING:
    from evo.blockmodels.endpoints.models import UpdateType

app = typer.Typer(help="Manage block model columns.")


def _version_plain(action: str, data: dict, details: list[str] | None = None) -> str:
    lines = [f"{action}  →  v{data['version_id']}  {data['version_uuid']}"]
    for d in details or []:
        lines.append(f"  {d}")
    return "\n".join(lines)


def _parse_rename_option(entries: list[str]) -> dict[str, str]:
    renames: dict[str, str] = {}
    for entry in entries:
        if "=" not in entry:
            output.emit_error(f"Invalid --rename {entry!r}. Expected 'old_title=new_title'.")
        old_title, new_title = entry.split("=", 1)
        old_title, new_title = old_title.strip(), new_title.strip()
        if not old_title or not new_title:
            output.emit_error(f"--rename {entry!r} must include both an old and new title.")
        renames[old_title] = new_title
    if not renames:
        output.emit_error("provide at least one --rename")
    return renames


def _parse_unit_updates(set_entries: list[str], clear_entries: list[str]) -> dict[str, str | None]:
    updates: dict[str, str | None] = {}
    for entry in set_entries:
        if "=" not in entry:
            output.emit_error(f"Invalid --set-unit {entry!r}. Expected 'column=unit_id'.")
        title, unit_id = entry.split("=", 1)
        title, unit_id = title.strip(), unit_id.strip()
        if not title or not unit_id:
            output.emit_error(f"--set-unit {entry!r} must include both a column title and a unit ID.")
        if title in updates:
            output.emit_error(f"column {title!r} specified more than once across --set-unit/--clear-unit.")
        updates[title] = unit_id
    for raw_title in clear_entries:
        title = raw_title.strip()
        if not title:
            output.emit_error("--clear-unit requires a column title.")
        if title in updates:
            output.emit_error(f"column {title!r} specified more than once across --set-unit/--clear-unit.")
        updates[title] = None
    if not updates:
        output.emit_error("provide at least one --set-unit or --clear-unit")
    return updates


@app.command()
def rename(
    bm_id: str = typer.Argument(help="Block model UUID"),
    renames: list[str] = typer.Option(
        ..., "--rename", help="'old_title=new_title' - repeat --rename for multiple columns"
    ),
    comment: Optional[str] = typer.Option(None, "--comment", help="Comment describing the change (max 250 chars)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Rename existing block model columns."""
    column_renames = _parse_rename_option(renames)
    asyncio.run(_do_rename(bm_id, column_renames, comment, workspace))


async def _do_rename(bm_id: str, column_renames: dict[str, str], comment: str | None, workspace: str | None) -> None:
    from evo.blockmodels import BlockModelAPIClient

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            version = await client.rename_block_model_columns(UUID(bm_id), column_renames, comment=comment)
        except Exception as exc:
            output.emit_error(str(exc))

    data = _version_to_dict(version)
    rename_details = "  ".join(f"{old} → {new}" for old, new in column_renames.items())
    output.emit(data, plain=_version_plain(f"Renamed ({len(column_renames)})", data, [rename_details]))


@app.command("delete")
def delete_columns(
    bm_id: str = typer.Argument(help="Block model UUID"),
    column: list[str] = typer.Option(
        ..., "--column", help="Title of a column to delete - repeat --column for multiple columns"
    ),
    comment: Optional[str] = typer.Option(None, "--comment", help="Comment describing the change (max 250 chars)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Delete existing columns from a block model."""
    if not column:
        output.emit_error("provide at least one --column")
    asyncio.run(_do_delete(bm_id, column, comment, workspace))


async def _do_delete(bm_id: str, column_titles: list[str], comment: str | None, workspace: str | None) -> None:
    from evo.blockmodels import BlockModelAPIClient

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            version = await client.delete_block_model_columns(UUID(bm_id), column_titles, comment=comment)
        except Exception as exc:
            output.emit_error(str(exc))

    data = _version_to_dict(version)
    output.emit(data, plain=_version_plain(f"Deleted ({len(column_titles)})", data, [", ".join(column_titles)]))


@app.command("update-metadata")
def update_metadata(
    bm_id: str = typer.Argument(help="Block model UUID"),
    set_unit: list[str] = typer.Option(
        [], "--set-unit", help="'column=unit_id' - repeat --set-unit for multiple columns"
    ),
    clear_unit: list[str] = typer.Option(
        [], "--clear-unit", help="Column title to clear the unit of - repeat --clear-unit for multiple columns"
    ),
    comment: Optional[str] = typer.Option(None, "--comment", help="Comment describing the change (max 250 chars)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Update unit metadata for existing block model columns.

    Column tags are a preview feature and are not exposed by this command yet.
    """
    column_updates = _parse_unit_updates(set_unit, clear_unit)
    asyncio.run(_do_update_metadata(bm_id, column_updates, comment, workspace))


async def _do_update_metadata(
    bm_id: str, column_updates: dict[str, str | None], comment: str | None, workspace: str | None
) -> None:
    from evo.blockmodels import BlockModelAPIClient

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            version = await client.update_column_metadata(UUID(bm_id), column_updates, comment=comment)
        except Exception as exc:
            output.emit_error(str(exc))

    data = _version_to_dict(version)
    set_cols = [(t, u) for t, u in column_updates.items() if u is not None]
    clear_cols = [t for t, u in column_updates.items() if u is None]
    details = []
    if set_cols:
        details.append("Unit set  " + "  ".join(f"{t} → {u}" for t, u in set_cols))
    if clear_cols:
        details.append("Unit cleared  " + ", ".join(clear_cols))
    output.emit(data, plain=_version_plain("Updated column metadata", data, details))


@app.command()
def add(
    bm_id: str = typer.Argument(help="Block model UUID"),
    data: Path = typer.Option(..., "--data", help="Local .csv or .parquet file with the new column data"),
    units: list[str] = typer.Option([], "--units", help="'column=unit_id' - repeat --units for multiple columns"),
    subblocked: bool = typer.Option(
        False, "--subblocked", help="Add columns to a sub-blocked model without changing sub-block geometry"
    ),
    cache_dir: Optional[str] = typer.Option(
        None, "--cache-dir", help="Local cache directory for uploads (default: ~/.evo/cache)"
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Add new columns to an existing block model from a local .csv or .parquet file."""
    table = read_table_file(data)
    parsed_units = parse_key_value_option(units, "--units") if units else None
    asyncio.run(_do_add(bm_id, table, parsed_units, subblocked, cache_dir, workspace))


async def _do_add(
    bm_id: str,
    table,
    units: dict[str, str] | None,
    subblocked: bool,
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
            if subblocked:
                version = await client.add_new_subblocked_columns(UUID(bm_id), table, units=units)
            else:
                version = await client.add_new_columns(UUID(bm_id), table, units=units)
        except Exception as exc:
            output.emit_error(str(exc))

    data = _version_to_dict(version)
    new_col_names = [n for n in table.schema.names if n not in GEOMETRY_COLUMNS]
    output.emit(data, plain=_version_plain(f"Added ({len(new_col_names)})", data, [", ".join(new_col_names)]))


@app.command()
def update(
    bm_id: str = typer.Argument(help="Block model UUID"),
    data: Path = typer.Option(..., "--data", help="Local .csv or .parquet file with the column data"),
    new_column: list[str] = typer.Option(
        [], "--new-column", help="Title of a new column present in --data - repeat for multiple columns"
    ),
    update_column: list[str] = typer.Option(
        [], "--update-column", help="Title of an existing column to update from --data - repeat for multiple columns"
    ),
    delete_column: list[str] = typer.Option(
        [], "--delete-column", help="Title of an existing column to delete - repeat for multiple columns"
    ),
    units: list[str] = typer.Option(
        [], "--units", help="'column=unit_id' for --new-column columns - repeat for multiple columns"
    ),
    update_type: str = typer.Option("replace", "--update-type", help="'replace' or 'merge'"),
    subblocked: bool = typer.Option(False, "--subblocked", help="Update columns of a sub-blocked model"),
    geometry_change: bool = typer.Option(
        False, "--geometry-change", help="[--subblocked only] Whether the sub-blocking geometry is changing"
    ),
    fill_subblocks: Optional[bool] = typer.Option(
        None,
        "--fill-subblocks/--no-fill-subblocks",
        help="[--subblocked only] Fill missing sub-blocks with parent data",
    ),
    comment: Optional[str] = typer.Option(None, "--comment", help="Comment describing the change"),
    cache_dir: Optional[str] = typer.Option(
        None, "--cache-dir", help="Local cache directory for uploads (default: ~/.evo/cache)"
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Add, update, or delete block model columns from a local .csv or .parquet file."""
    from evo.blockmodels.endpoints.models import UpdateType

    if not subblocked and (geometry_change or fill_subblocks is not None):
        output.emit_error("--geometry-change and --fill-subblocks are only valid with --subblocked")
    try:
        update_type_enum = UpdateType(update_type)
    except ValueError:
        output.emit_error(f"Invalid --update-type {update_type!r}. Expected 'replace' or 'merge'.")

    table = read_table_file(data)
    parsed_units = parse_key_value_option(units, "--units") if units else None
    asyncio.run(
        _do_update(
            bm_id,
            table,
            new_column,
            set(update_column),
            set(delete_column),
            parsed_units,
            update_type_enum,
            subblocked,
            geometry_change,
            fill_subblocks,
            comment,
            cache_dir,
            workspace,
        )
    )


async def _do_update(
    bm_id: str,
    table,
    new_columns: list[str],
    update_columns: set[str],
    delete_columns: set[str],
    units: dict[str, str] | None,
    update_type: UpdateType,
    subblocked: bool,
    geometry_change: bool,
    fill_subblocks: bool | None,
    comment: str | None,
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
            if subblocked:
                version = await client.update_subblocked_columns(
                    UUID(bm_id),
                    table,
                    new_columns,
                    update_columns=update_columns,
                    delete_columns=delete_columns,
                    units=units,
                    geometry_change=geometry_change,
                    fill_subblocks=fill_subblocks,
                    update_type=update_type,
                )
            else:
                version = await client.update_block_model_columns(
                    UUID(bm_id),
                    table,
                    new_columns,
                    update_columns=update_columns,
                    delete_columns=delete_columns,
                    units=units,
                    update_type=update_type,
                )
        except Exception as exc:
            output.emit_error(str(exc))

    data = _version_to_dict(version)
    details = []
    if new_columns:
        details.append(f"Added   ({len(new_columns)})  {', '.join(new_columns)}")
    if update_columns:
        cols = sorted(update_columns)
        details.append(f"Updated ({len(cols)})  {', '.join(cols)}")
    if delete_columns:
        details.append(f"Deleted ({len(delete_columns)})  {', '.join(sorted(delete_columns))}")
    output.emit(data, plain=_version_plain("Column update", data, details))
