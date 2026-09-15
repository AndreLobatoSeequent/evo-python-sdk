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
from typing import Optional
from uuid import UUID

import typer

from evo.files import FileAPIClient
from evo.files.data import FileMetadata, FileVersion

from evo.cli import output
from evo.cli._connector import make_connector, make_environment, make_transport, require_credentials

app = typer.Typer(help="Manage files.")


def _meta_to_dict(f: FileMetadata) -> dict:
    return {
        "id": str(f.id),
        "name": f.name,
        "path": f.path,
        "size": f.size,
        "version_id": f.version_id,
        "modified_at": f.modified_at.isoformat(),
        "modified_by": f.modified_by.email if f.modified_by else None,
    }


def _version_to_dict(v: FileVersion) -> dict:
    return {
        "version_id": v.version_id,
        "created_at": v.created_at.isoformat(),
        "created_by": v.created_by.email if v.created_by else None,
    }


@app.command("list")
def list_files(
    name: Optional[str] = typer.Option(None, "--name", help="Filter by exact file name"),
    deleted: bool = typer.Option(False, "--deleted", help="Show only deleted files"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """List files in the workspace."""
    asyncio.run(_do_list(name, deleted, workspace))


async def _do_list(name: str | None, deleted: bool, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = FileAPIClient(environment=env, connector=connector)
        files = await client.list_all_files(name=name, deleted=deleted)

    items = [_meta_to_dict(f) for f in files]
    output.emit(
        items,
        plain="\n".join(
            f"{f['path']}  {f['size']} bytes  {f['id']}" for f in items
        ) or "No files found.",
    )


@app.command()
def get(
    path: Optional[str] = typer.Option(None, "--path", help="Remote file path"),
    id: Optional[str] = typer.Option(None, "--id", help="File UUID"),
    version: Optional[str] = typer.Option(None, "--version", help="Version ID (default: latest)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Get metadata for a file (no download)."""
    if not path and not id:
        output.emit_error("provide --path or --id")
    if path and id:
        output.emit_error("provide only one of --path or --id")
    asyncio.run(_do_get(path, id, version, workspace))


async def _do_get(path: str | None, file_id: str | None, version: str | None, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = FileAPIClient(environment=env, connector=connector)
        try:
            if path:
                meta = await client.get_file_by_path(path, version_id=version)
            else:
                meta = await client.get_file_by_id(UUID(file_id), version_id=version)
        except Exception as exc:
            output.emit_error(str(exc))

    data = _meta_to_dict(meta)
    output.emit(
        data,
        plain=f"{meta.path}  {meta.size} bytes  v{meta.version_id}  modified {meta.modified_at.isoformat()}",
    )


@app.command()
def versions(
    path: Optional[str] = typer.Option(None, "--path", help="Remote file path"),
    id: Optional[str] = typer.Option(None, "--id", help="File UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """List all versions of a file."""
    if not path and not id:
        output.emit_error("provide --path or --id")
    if path and id:
        output.emit_error("provide only one of --path or --id")
    asyncio.run(_do_versions(path, id, workspace))


async def _do_versions(path: str | None, file_id: str | None, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = FileAPIClient(environment=env, connector=connector)
        try:
            if path:
                vers = await client.list_versions_by_path(path)
            else:
                vers = await client.list_versions_by_id(UUID(file_id))
        except Exception as exc:
            output.emit_error(str(exc))

    items = [_version_to_dict(v) for v in vers]
    output.emit(
        items,
        plain="\n".join(f"{v['version_id']}  {v['created_at']}" for v in items) or "No versions found.",
    )


@app.command()
def upload(
    src: str = typer.Option(..., "--src", help="Local file path to upload"),
    dest: str = typer.Option(..., "--dest", help="Remote path (e.g. /surveys/gravity.dat)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Upload a local file. Creates a new version if the remote path already exists."""
    src_path = Path(src)
    if not src_path.exists():
        output.emit_error(f"local file not found: {src}")
    asyncio.run(_do_upload(src_path, dest, workspace))


async def _do_upload(src: Path, dest: str, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    transport = make_transport()

    async with make_connector(creds) as connector:
        client = FileAPIClient(environment=env, connector=connector)

        # Check if the file already exists to detect new-version vs new-file.
        is_new_version = False
        try:
            await client.get_file_by_path(dest)
            is_new_version = True
        except Exception:
            pass

        try:
            upload_ctx = await client.prepare_upload_by_path(dest)
            await upload_ctx.upload_from_path(src, transport)
        except Exception as exc:
            output.emit_error(str(exc))

    action = "new_version" if is_new_version else "uploaded"
    result = {
        "status": action,
        "file_id": str(upload_ctx.file_id),
        "version_id": upload_ctx.version_id,
        "dest": dest,
        "src": str(src),
    }
    if is_new_version:
        plain = f"New version uploaded — {dest}  version {upload_ctx.version_id}"
    else:
        plain = f"Uploaded — {dest}  version {upload_ctx.version_id}"
    output.emit(result, plain=plain)


@app.command()
def download(
    path: Optional[str] = typer.Option(None, "--path", help="Remote file path"),
    id: Optional[str] = typer.Option(None, "--id", help="File UUID"),
    version: Optional[str] = typer.Option(None, "--version", help="Version ID (default: latest)"),
    output_path: Optional[str] = typer.Option(None, "--output", "-o", help="Local destination path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing local file"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Download a file to local disk."""
    if not path and not id:
        output.emit_error("provide --path or --id")
    if path and id:
        output.emit_error("provide only one of --path or --id")
    asyncio.run(_do_download(path, id, version, output_path, overwrite, workspace))


async def _do_download(
    path: str | None,
    file_id: str | None,
    version: str | None,
    output_path: str | None,
    overwrite: bool,
    workspace: str | None,
) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    transport = make_transport()

    async with make_connector(creds) as connector:
        client = FileAPIClient(environment=env, connector=connector)
        try:
            if path:
                dl = await client.prepare_download_by_path(path, version_id=version)
            else:
                dl = await client.prepare_download_by_id(UUID(file_id), version_id=version)
        except Exception as exc:
            output.emit_error(str(exc))

        dest = Path(output_path) if output_path else Path.cwd() / dl.metadata.name

        if dest.exists() and not overwrite:
            if output.is_interactive():
                overwrite = typer.confirm(f"'{dest}' already exists. Overwrite?", default=False)
                if not overwrite:
                    output.emit_error("download cancelled — file already exists", exit_code=0)
            else:
                output.emit_error(
                    "file_exists",
                    path=str(dest),
                    hint="Use --overwrite to replace it",
                )

        try:
            await dl.download_to_path(dest, transport, overwrite=overwrite)
        except Exception as exc:
            output.emit_error(str(exc))

    output.emit(
        {"status": "downloaded", "path": str(dest), "size": dl.metadata.size, "version_id": dl.metadata.version_id},
        plain=f"Downloaded to '{dest}'  ({dl.metadata.size} bytes)",
    )


@app.command()
def delete(
    path: Optional[str] = typer.Option(None, "--path", help="Remote file path"),
    id: Optional[str] = typer.Option(None, "--id", help="File UUID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Soft-delete a file."""
    if not path and not id:
        output.emit_error("provide --path or --id")
    if path and id:
        output.emit_error("provide only one of --path or --id")
    label = path or id
    if output.is_interactive() and not yes:
        typer.confirm(f"Delete file '{label}'?", abort=True)
    asyncio.run(_do_delete(path, id, workspace))


async def _do_delete(path: str | None, file_id: str | None, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = FileAPIClient(environment=env, connector=connector)
        try:
            if path:
                await client.delete_file_by_path(path)
            else:
                await client.delete_file_by_id(UUID(file_id))
        except Exception as exc:
            output.emit_error(str(exc))

    label = path or file_id
    output.emit({"status": "deleted", "file": label}, plain=f"Deleted '{label}'.")


@app.command()
def restore(
    id: str = typer.Argument(help="File UUID to restore"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Restore a soft-deleted file."""
    asyncio.run(_do_restore(id, workspace))


async def _do_restore(file_id: str, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = FileAPIClient(environment=env, connector=connector)
        try:
            result = await client.restore_file_by_id(UUID(file_id))
        except Exception as exc:
            output.emit_error(str(exc))

    if result is not None:
        data = _meta_to_dict(result)
        output.emit(data, plain=f"Restored to '{result.path}'.")
    else:
        output.emit({"status": "restored", "id": file_id}, plain=f"Restored '{file_id}'.")
