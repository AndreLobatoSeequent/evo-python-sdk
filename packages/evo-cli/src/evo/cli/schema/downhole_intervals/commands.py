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

app = typer.Typer(help="Manage DownholeIntervals objects.")


@app.command("create")
def create_downhole_intervals(
    csv_file: str = typer.Option(
        ..., "--from-csv", help="Path to CSV file (requires hole_id, from_depth, to_depth columns)"
    ),
    name: Optional[str] = typer.Option(None, "--name", help="DownholeIntervals name (defaults to CSV filename)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Create a DownholeIntervals object from a CSV file with interval depth data."""
    asyncio.run(_do_create_downhole_intervals(csv_file, name, workspace))


async def _do_create_downhole_intervals(csv_path: str, obj_name: str | None, workspace: str | None) -> None:
    import pandas as pd

    from evo.common import StaticContext
    from evo.common.utils import Cache
    from evo.objects.typed.downhole_intervals import DownholeIntervals, DownholeIntervalsData

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        output.emit_error(f"Failed to read CSV: {e}")

    required_cols = {"hole_id", "from_depth", "to_depth"}
    if not required_cols.issubset(set(col.lower() for col in df.columns)):
        output.emit_error(f"CSV must contain hole_id, from_depth, to_depth columns. Found: {list(df.columns)}")

    df.columns = [col.lower() for col in df.columns]
    name_to_use = obj_name or csv_path.split("\\")[-1].replace(".csv", "")

    try:
        intervals_data = DownholeIntervalsData(
            name=name_to_use,
            intervals=df,
        )
    except Exception as e:
        output.emit_error(f"Failed to create DownholeIntervals data: {e}")

    creds = await require_credentials()
    env = make_environment(creds, workspace)

    with tempfile.TemporaryDirectory() as cache_dir:
        cache = Cache(cache_dir, mkdir=False)
        async with make_connector(creds) as connector:
            context = StaticContext.from_environment(env, connector, cache=cache)
            try:
                result = await DownholeIntervals.create(context=context, data=intervals_data)
            except Exception as exc:
                output.emit_error(f"Failed to create DownholeIntervals: {exc}")

    data = {
        "id": str(result.metadata.id),
        "name": result.name,
        "path": result.metadata.path,
        "type": str(result.metadata.schema_id),
        "source": "CSV import",
        "interval_count": len(df),
        "columns": list(df.columns),
    }

    output.emit(
        data, plain=f"Created DownholeIntervals '{result.name}' with {len(df)} intervals ({result.metadata.id})"
    )
