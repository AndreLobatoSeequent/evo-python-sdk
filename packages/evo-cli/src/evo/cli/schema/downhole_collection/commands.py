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
from pathlib import Path
from typing import Optional

import typer

from evo.cli import output
from evo.cli._connector import make_connector, make_environment, require_credentials

app = typer.Typer(help="Manage DownholeCollection objects.")

_COLLAR_ALIASES: dict[str, list[str]] = {
    "hole_id": ["hole_id", "bhid", "holeid", "borehole_id", "id"],
    "x": ["x", "xcollar", "easting", "east", "longitude"],
    "y": ["y", "ycollar", "northing", "north", "latitude"],
    "z": ["z", "zcollar", "elevation", "elev", "rl"],
}

_SURVEY_ALIASES: dict[str, list[str]] = {
    "hole_id": ["hole_id", "bhid", "holeid", "borehole_id"],
    "distance": ["distance", "at", "depth", "md", "measured_depth"],
    "azimuth": ["azimuth", "az", "brg", "bearing", "azi"],
    "dip": ["dip", "incl", "inclination", "inc"],
}

_INTERVAL_ALIASES: dict[str, list[str]] = {
    "hole_id": ["hole_id", "bhid", "holeid", "borehole_id"],
    "distance": ["from", "from_m", "depth_from", "distance", "depth", "at", "md"],
}


def _resolve_columns(df_cols: list[str], aliases: dict[str, list[str]]) -> dict[str, str]:
    """Return {canonical_name: actual_col} for each canonical name found via aliases."""
    lower_map = {c.lower(): c for c in df_cols}
    result: dict[str, str] = {}
    for canonical, options in aliases.items():
        for opt in options:
            if opt in lower_map:
                result[canonical] = lower_map[opt]
                break
    return result


@app.command("create")
def create_downhole_collection(
    csv_file: str = typer.Option(..., "--from-csv", help="Path to CSV file (requires hole_id, x, y, z columns)"),
    name: Optional[str] = typer.Option(None, "--name", help="DownholeCollection name (defaults to CSV filename)"),
    crs: Optional[str] = typer.Option(None, "--crs", help="Coordinate Reference System (EPSG code or WKT)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Create a DownholeCollection object from a CSV file with downhole collar data."""
    asyncio.run(_do_create_downhole_collection(csv_file, name, crs, workspace))


async def _do_create_downhole_collection(
    csv_path: str, obj_name: str | None, crs: str | None, workspace: str | None
) -> None:
    import pandas as pd

    from evo.common import StaticContext
    from evo.common.utils import Cache
    from evo.objects.typed.downhole_collection import DownholeCollection, DownholeCollectionData

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        output.emit_error(f"Failed to read CSV: {e}")

    required_cols = {"hole_id", "x", "y", "z"}
    if not required_cols.issubset(set(col.lower() for col in df.columns)):
        output.emit_error(f"CSV must contain hole_id, x, y, z columns. Found: {list(df.columns)}")

    df.columns = [col.lower() for col in df.columns]
    name_to_use = obj_name or csv_path.split("\\")[-1].replace(".csv", "")

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

    with tempfile.TemporaryDirectory() as cache_dir:
        cache = Cache(cache_dir, mkdir=False)
        async with make_connector(creds) as connector:
            context = StaticContext.from_environment(env, connector, cache=cache)
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
        data, plain=f"Created DownholeCollection '{result.name}' with {len(df)} boreholes ({result.metadata.id})"
    )


@app.command("create-from-dir")
def create_from_dir(
    directory: str = typer.Argument(..., help="Directory containing collar.csv, survey.csv, and optional interval CSVs."),
    name: Optional[str] = typer.Option(None, "--name", help="Object name (defaults to directory name)."),
    crs: Optional[str] = typer.Option(None, "--crs", help="Coordinate Reference System (EPSG code or WKT)."),
    desurvey: str = typer.Option("minimum_curvature", "--desurvey", help="Desurvey method: minimum_curvature, balanced_tangent, or trench."),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)."),
) -> None:
    """Create a DownholeCollection from a directory of drilling CSVs.

    Expects collar.csv (hole positions) and survey.csv (hole paths) as required files.
    Any other CSV files in the directory are imported as interval collections.

    Column aliases recognised automatically:
      collar  — hole_id/BHID, x/XCOLLAR, y/YCOLLAR, z/ZCOLLAR
      survey  — hole_id/BHID, distance/AT/depth, azimuth/BRG, dip/DIP
      intervals — hole_id/BHID, distance/FROM
    """
    asyncio.run(_do_create_from_dir(directory, name, crs, desurvey, workspace))


async def _do_create_from_dir(
    directory: str,
    obj_name: str | None,
    crs: str | None,
    desurvey: str,
    workspace: str | None,
) -> None:
    import numpy as np
    import pandas as pd

    from evo.common import StaticContext
    from evo.common.utils import Cache
    from evo.objects.typed.downhole_collection import DistanceCollection, DownholeCollection, DownholeCollectionData

    dir_path = Path(directory)
    if not dir_path.is_dir():
        output.emit_error(f"Not a directory: {directory}")

    collar_path = dir_path / "collar.csv"
    survey_path = dir_path / "survey.csv"
    for required in (collar_path, survey_path):
        if not required.exists():
            output.emit_error(f"Required file not found: {required}")

    # --- Collar ---
    collar_df = pd.read_csv(collar_path)
    collar_map = _resolve_columns(list(collar_df.columns), _COLLAR_ALIASES)
    missing = [k for k in ("hole_id", "x", "y", "z") if k not in collar_map]
    if missing:
        output.emit_error(f"collar.csv missing columns for: {missing}. Found: {list(collar_df.columns)}")
    collar_df = collar_df.rename(columns={v: k for k, v in collar_map.items()})
    collar_df["hole_id"] = collar_df["hole_id"].astype(str)
    hole_order = list(collar_df["hole_id"])

    # --- Survey ---
    survey_df = pd.read_csv(survey_path)
    survey_map = _resolve_columns(list(survey_df.columns), _SURVEY_ALIASES)
    missing = [k for k in ("hole_id", "distance", "azimuth", "dip") if k not in survey_map]
    if missing:
        output.emit_error(f"survey.csv missing columns for: {missing}. Found: {list(survey_df.columns)}")
    survey_df = survey_df.rename(columns={v: k for k, v in survey_map.items()})
    survey_df["hole_id"] = survey_df["hole_id"].astype(str)
    survey_df = survey_df.sort_values(["hole_id", "distance"]).reset_index(drop=True)

    # Build concatenated path table and holes chunk table
    path_rows: list[pd.DataFrame] = []
    holes_rows: list[dict] = []
    offset = 0
    for idx, hole_id in enumerate(hole_order):
        hole_survey = survey_df[survey_df["hole_id"] == hole_id][["distance", "azimuth", "dip"]]
        count = len(hole_survey)
        path_rows.append(hole_survey.reset_index(drop=True))
        holes_rows.append({"hole_index": np.int32(idx), "offset": np.int32(offset), "count": np.int32(count)})
        offset += count

    path = pd.concat(path_rows, ignore_index=True) if path_rows else pd.DataFrame(columns=["distance", "azimuth", "dip"])
    holes = pd.DataFrame(holes_rows).astype({"hole_index": np.int32, "offset": np.uint64, "count": np.uint64})

    # Build properties: hole_id, x, y, z, final, target, current
    # final/current = max survey depth per hole; target = final
    max_depth = survey_df.groupby("hole_id")["distance"].max().rename("final")
    properties = collar_df[["hole_id", "x", "y", "z"]].copy()
    properties = properties.merge(max_depth, on="hole_id", how="left")
    properties["target"] = properties["final"]
    properties["current"] = properties["final"]
    properties = properties[["hole_id", "x", "y", "z", "final", "target", "current"]]
    properties["x"] = properties["x"].astype(np.float64)
    properties["y"] = properties["y"].astype(np.float64)
    properties["z"] = properties["z"].astype(np.float64)
    properties["final"] = properties["final"].astype(np.float64)
    properties["target"] = properties["target"].astype(np.float64)
    properties["current"] = properties["current"].astype(np.float64)

    # --- Interval collections ---
    collections: list[DistanceCollection] = []
    interval_files = [
        p for p in sorted(dir_path.glob("*.csv"))
        if p.name.lower() not in ("collar.csv", "survey.csv")
    ]
    for csv_path in interval_files:
        try:
            iv_df = pd.read_csv(csv_path)
            iv_map = _resolve_columns(list(iv_df.columns), _INTERVAL_ALIASES)
            if "hole_id" not in iv_map or "distance" not in iv_map:
                output.emit(
                    {"step": "skip", "file": csv_path.name, "reason": "no hole_id or FROM/distance column"},
                    plain=f"  Skipping {csv_path.name}: no recognised hole_id or distance column.",
                )
                continue
            iv_df = iv_df.rename(columns={v: k for k, v in iv_map.items()})
            iv_df["hole_id"] = iv_df["hole_id"].astype(str)
            iv_df = iv_df.sort_values(["hole_id", "distance"]).reset_index(drop=True)

            # Drop any 'to' / 'TO' column — evo uses distance-point model
            to_col = next((c for c in iv_df.columns if c.lower() == "to"), None)
            if to_col:
                iv_df = iv_df.drop(columns=[to_col])

            coll_path_rows: list[pd.DataFrame] = []
            coll_holes_rows: list[dict] = []
            coll_offset = 0
            for idx, hole_id in enumerate(hole_order):
                hole_iv = iv_df[iv_df["hole_id"] == hole_id].drop(columns=["hole_id"])
                count = len(hole_iv)
                coll_path_rows.append(hole_iv.reset_index(drop=True))
                coll_holes_rows.append({"hole_index": np.int32(idx), "offset": np.int32(coll_offset), "count": np.int32(count)})
                coll_offset += count

            coll_distance_table = pd.concat(coll_path_rows, ignore_index=True) if coll_path_rows else pd.DataFrame()
            coll_holes = pd.DataFrame(coll_holes_rows).astype({"hole_index": np.int32, "offset": np.uint64, "count": np.uint64})
            collections.append(
                DistanceCollection(
                    name=csv_path.stem,
                    holes=coll_holes,
                    distance_table=coll_distance_table,
                )
            )
            output.emit(
                {"step": "interval_loaded", "file": csv_path.name, "rows": len(iv_df)},
                plain=f"  Loaded interval collection '{csv_path.stem}' ({len(iv_df)} rows).",
            )
        except Exception as exc:
            output.emit(
                {"step": "interval_error", "file": csv_path.name, "error": str(exc)},
                plain=f"  Warning: failed to load {csv_path.name}: {exc}",
            )

    obj_name_to_use = obj_name or dir_path.name

    try:
        dhc_data = DownholeCollectionData(
            name=obj_name_to_use,
            path=path,
            holes=holes,
            properties=properties,
            attributes=None,
            collections=collections,
            distance_unit="m",
            desurvey=desurvey,
            coordinate_reference_system=crs or "unspecified",
        )
    except Exception as e:
        output.emit_error(f"Failed to build DownholeCollectionData: {e}")

    creds = await require_credentials()
    env = make_environment(creds, workspace)

    with tempfile.TemporaryDirectory() as cache_dir:
        cache = Cache(cache_dir, mkdir=False)
        async with make_connector(creds) as connector:
            context = StaticContext.from_environment(env, connector, cache=cache)
            try:
                result = await DownholeCollection.create(context=context, data=dhc_data)
            except Exception as exc:
                output.emit_error(f"Failed to create DownholeCollection: {exc}")

    data = {
        "id": str(result.metadata.id),
        "name": result.name,
        "path": result.metadata.path,
        "type": str(result.metadata.schema_id),
        "hole_count": len(hole_order),
        "collection_count": len(collections),
        "collections": [c.name for c in collections],
    }
    output.emit(
        data,
        plain=(
            f"Created DownholeCollection '{result.name}' — {len(hole_order)} holes, "
            f"{len(collections)} interval collection(s) ({result.metadata.id})"
        ),
    )
