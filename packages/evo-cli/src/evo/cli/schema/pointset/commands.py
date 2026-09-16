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
import tempfile
from typing import Optional

import typer

from evo.cli import output
from evo.cli._connector import make_connector, make_environment, require_credentials

app = typer.Typer(help="Manage PointSet objects.")


@app.command("create")
def create_pointset(
    csv_file: str = typer.Option(..., "--from-csv", help="Path to CSV file with point data (requires x, y, z columns)"),
    name: Optional[str] = typer.Option(None, "--name", help="PointSet name (defaults to CSV filename)"),
    crs: Optional[str] = typer.Option(None, "--crs", help="Coordinate Reference System (EPSG code or WKT)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Create a PointSet object from a CSV file with x, y, z coordinates."""
    asyncio.run(_do_create_pointset(csv_file, name, crs, workspace))


async def _do_create_pointset(csv_path: str, obj_name: str | None, crs: str | None, workspace: str | None) -> None:
    import pandas as pd

    from evo.common import StaticContext
    from evo.common.utils import Cache
    from evo.objects.typed.pointset import PointSet, PointSetData

    try:
        # Read CSV file
        df = pd.read_csv(csv_path)
    except Exception as e:
        output.emit_error(f"Failed to read CSV: {e}")

    # Validate required columns
    required_cols = {"x", "y", "z"}
    if not required_cols.issubset(set(col.lower() for col in df.columns)):
        output.emit_error(f"CSV must contain 'x', 'y', 'z' columns. Found: {list(df.columns)}")

    # Normalize column names to lowercase
    df.columns = [col.lower() for col in df.columns]

    # Determine object name
    name_to_use = obj_name or csv_path.split("\\")[-1].replace(".csv", "")

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

    with tempfile.TemporaryDirectory() as cache_dir:
        cache = Cache(cache_dir, mkdir=False)
        async with make_connector(creds) as connector:
            context = StaticContext.from_environment(env, connector, cache=cache)
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
        plain=f"Created PointSet '{result.name}' with {len(df)} points and {len(df.columns)} attributes ({result.metadata.id})",
    )
