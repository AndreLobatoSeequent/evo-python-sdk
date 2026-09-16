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
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

import typer

from evo.cli import output
from evo.cli._connector import make_connector, make_environment, require_credentials

if TYPE_CHECKING:
    from evo.objects.typed.variogram import VariogramStructure

app = typer.Typer(help="Manage variogram objects.")


def _structure_types() -> dict[str, type[VariogramStructure]]:
    from evo.objects.typed.variogram import (
        CubicStructure,
        ExponentialStructure,
        GaussianStructure,
        GeneralisedCauchyStructure,
        LinearStructure,
        SphericalStructure,
        SpheroidalStructure,
    )

    return {
        "spherical": SphericalStructure,
        "exponential": ExponentialStructure,
        "gaussian": GaussianStructure,
        "cubic": CubicStructure,
        "linear": LinearStructure,
        "spheroidal": SpheroidalStructure,
        "generalisedcauchy": GeneralisedCauchyStructure,
    }


_EXAMPLE_JSON = """{
  "name": "My Variogram",
  "sill": 1.0,
  "nugget": 0.1,
  "is_rotation_fixed": true,
  "modelling_space": "data",
  "data_variance": 1.0,
  "attribute": "grade",
  "domain": null,
  "structures": [
    {
      "variogram_type": "spherical",
      "contribution": 0.9,
      "anisotropy": {
        "ranges": {"major": 200, "semi_major": 150, "minor": 100},
        "rotation": {"dip_azimuth": 0, "dip": 0, "pitch": 0}
      }
    }
  ]
}"""


def _parse_structure(s: dict[str, Any]) -> VariogramStructure:
    from evo.objects.typed.types import Ellipsoid, EllipsoidRanges, Rotation

    structure_types = _structure_types()
    vtype = s.get("variogram_type", "").lower()
    cls = structure_types.get(vtype)
    if cls is None:
        valid = ", ".join(structure_types)
        raise ValueError(f"Unknown variogram_type '{vtype}'. Valid types: {valid}")

    aniso = s.get("anisotropy", {})
    ranges_dict = aniso.get("ranges", {})
    rot_dict = aniso.get("rotation", {})

    ranges = EllipsoidRanges(
        major=ranges_dict["major"],
        semi_major=ranges_dict["semi_major"],
        minor=ranges_dict["minor"],
    )
    rotation = Rotation(
        dip_azimuth=rot_dict.get("dip_azimuth", 0),
        dip=rot_dict.get("dip", 0),
        pitch=rot_dict.get("pitch", 0),
    )
    ellipsoid = Ellipsoid(ranges=ranges, rotation=rotation)

    kwargs: dict[str, Any] = {
        "contribution": s["contribution"],
        "anisotropy": ellipsoid,
    }
    if vtype in ("spheroidal", "generalisedcauchy"):
        kwargs["alpha"] = s["alpha"]

    return cls(**kwargs)


def _load_json(path_or_inline: str) -> dict[str, Any]:
    try:
        return json.loads(path_or_inline)
    except json.JSONDecodeError:
        with open(path_or_inline) as f:
            return json.load(f)


@app.command("create")
def create_variogram(
    json_input: str = typer.Option(
        ...,
        "--from-json",
        help="Path to a JSON file (or inline JSON string) describing the variogram.",
    ),
    name: Optional[str] = typer.Option(None, "--name", help="Override the variogram name from the JSON."),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)."),
) -> None:
    """Create a Variogram object from a JSON definition.

    The JSON must contain: name, sill, nugget, is_rotation_fixed, and structures.
    Each structure requires variogram_type, contribution, and anisotropy (ranges + rotation).

    Example JSON:

    \b
    {
      "name": "My Variogram",
      "sill": 1.0,
      "nugget": 0.1,
      "is_rotation_fixed": true,
      "structures": [
        {
          "variogram_type": "spherical",
          "contribution": 0.9,
          "anisotropy": {
            "ranges": {"major": 200, "semi_major": 150, "minor": 100},
            "rotation": {"dip_azimuth": 0, "dip": 0, "pitch": 0}
          }
        }
      ]
    }

    Run 'evo variograms example-json' to print a full example to stdout.
    """
    asyncio.run(_do_create_variogram(json_input, name, workspace))


async def _do_create_variogram(json_input: str, name_override: str | None, workspace: str | None) -> None:
    from evo.common import StaticContext
    from evo.common.utils import Cache
    from evo.objects.typed.variogram import Variogram, VariogramData

    try:
        raw = _load_json(json_input)
    except Exception as e:
        output.emit_error(f"Failed to read JSON: {e}")

    try:
        structures = [_parse_structure(s) for s in raw.get("structures", [])]
    except (KeyError, ValueError) as e:
        output.emit_error(f"Invalid structure definition: {e}")

    if not structures:
        output.emit_error("JSON must contain at least one structure.")

    name = name_override or raw.get("name")
    if not name:
        output.emit_error("Variogram name is required (set 'name' in JSON or use --name).")

    try:
        data = VariogramData(
            name=name,
            sill=raw["sill"],
            nugget=raw.get("nugget", 0.0),
            is_rotation_fixed=raw["is_rotation_fixed"],
            structures=structures,
            data_variance=raw.get("data_variance"),
            modelling_space=raw.get("modelling_space"),
            domain=raw.get("domain"),
            attribute=raw.get("attribute"),
            description=raw.get("description"),
            tags=raw.get("tags", []),
        )
    except Exception as e:
        output.emit_error(f"Failed to build VariogramData: {e}")

    creds = await require_credentials()
    env = make_environment(creds, workspace)

    with tempfile.TemporaryDirectory() as cache_dir:
        cache = Cache(cache_dir, mkdir=False)
        async with make_connector(creds) as connector:
            context = StaticContext.from_environment(env, connector, cache=cache)
            try:
                result = await Variogram.create(context=context, data=data)
            except Exception as exc:
                output.emit_error(f"Failed to create Variogram: {exc}")

    out = {
        "id": str(result.metadata.id),
        "name": result.name,
        "path": result.metadata.path,
        "type": str(result.metadata.schema_id),
        "version_id": result.metadata.version_id,
        "sill": data.sill,
        "nugget": data.nugget,
        "structure_count": len(structures),
    }
    output.emit(
        out,
        plain=f"Created Variogram '{result.name}' with {len(structures)} structure(s) ({result.metadata.id})",
    )


@app.command("get")
def get_variogram(
    variogram_id: str = typer.Argument(..., help="Variogram object UUID."),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)."),
) -> None:
    """Fetch a Variogram object by UUID and display its parameters."""
    asyncio.run(_do_get_variogram(variogram_id, workspace))


async def _do_get_variogram(variogram_id: str, workspace: str | None) -> None:
    from evo.common import StaticContext
    from evo.common.utils import Cache
    from evo.objects.typed.variogram import Variogram

    try:
        uid = UUID(variogram_id)
    except ValueError:
        output.emit_error(f"Invalid UUID: {variogram_id!r}")

    creds = await require_credentials()
    env = make_environment(creds, workspace)

    with tempfile.TemporaryDirectory() as cache_dir:
        cache = Cache(cache_dir, mkdir=False)
        async with make_connector(creds) as connector:
            context = StaticContext.from_environment(env, connector, cache=cache)
            try:
                variogram = await Variogram.from_reference(context=context, reference=uid)
            except Exception as exc:
                output.emit_error(f"Failed to fetch Variogram: {exc}")

    structures_out = []
    for s in variogram.structures:
        entry: dict[str, Any] = {
            "variogram_type": s.variogram_type,
            "contribution": s.contribution,
            "anisotropy": s.anisotropy.to_dict(),
        }
        if hasattr(s, "alpha"):
            entry["alpha"] = s.alpha
        structures_out.append(entry)

    out = {
        "id": str(variogram.metadata.id),
        "name": variogram.name,
        "path": variogram.metadata.path,
        "type": str(variogram.metadata.schema_id),
        "version_id": variogram.metadata.version_id,
        "sill": variogram.sill,
        "nugget": variogram.nugget,
        "is_rotation_fixed": variogram.is_rotation_fixed,
        "modelling_space": variogram.modelling_space,
        "data_variance": variogram.data_variance,
        "attribute": variogram.attribute,
        "domain": variogram.domain,
        "structures": structures_out,
    }
    output.emit(
        out,
        plain=(
            f"Variogram '{variogram.name}' — sill={variogram.sill}, nugget={variogram.nugget}, "
            f"{len(structures_out)} structure(s) ({variogram.metadata.id})"
        ),
    )


@app.command("import-lfv")
def import_lfv(
    lfv_file: str = typer.Argument(..., help="Path to a Leapfrog variogram file (.lfv)."),
    name: Optional[str] = typer.Option(None, "--name", help="Override the variogram name from the .lfv metadata."),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)."),
) -> None:
    """Create a Variogram object by importing a Leapfrog variogram file (.lfv).

    The .lfv file format uses a shared top-level rotation applied to all structures,
    and normalised sill/nugget values. The data variance is read from the file's metadata.
    """
    asyncio.run(_do_import_lfv(lfv_file, name, workspace))


async def _do_import_lfv(lfv_path: str, name_override: str | None, workspace: str | None) -> None:
    from evo.common import StaticContext
    from evo.common.utils import Cache
    from evo.objects.typed.types import Ellipsoid, EllipsoidRanges, Rotation
    from evo.objects.typed.variogram import Variogram, VariogramData

    try:
        with open(lfv_path) as f:
            raw = json.load(f)
    except Exception as e:
        output.emit_error(f"Failed to read .lfv file: {e}")

    meta = raw.get("metadata", {})
    rotation_dict = raw.get("rotation", {})

    # LFV uses dip_direction; SDK uses dip_azimuth — same convention in Leapfrog
    shared_rotation = Rotation(
        dip_azimuth=rotation_dict.get("dip_direction", rotation_dict.get("dip_azimuth", 0)),
        dip=rotation_dict.get("dip", 0),
        pitch=rotation_dict.get("pitch", 0),
    )

    structure_types = _structure_types()
    structures: list[VariogramStructure] = []
    for comp in raw.get("components", []):
        vtype = comp.get("structure_type", "").lower()
        cls = structure_types.get(vtype)
        if cls is None:
            valid = ", ".join(structure_types)
            output.emit_error(f"Unknown structure_type '{vtype}' in .lfv file. Valid types: {valid}")

        ranges_dict = comp.get("ranges", {})
        ranges = EllipsoidRanges(
            major=ranges_dict["major"],
            semi_major=ranges_dict["semi_major"],
            minor=ranges_dict["minor"],
        )
        ellipsoid = Ellipsoid(ranges=ranges, rotation=shared_rotation)

        kwargs: dict[str, Any] = {
            "contribution": comp["normalised_sill"],
            "anisotropy": ellipsoid,
        }
        if vtype in ("spheroidal", "generalisedcauchy") and "alpha" in comp:
            kwargs["alpha"] = comp["alpha"]

        structures.append(cls(**kwargs))

    if not structures:
        output.emit_error("No structures found in .lfv file.")

    name = name_override or meta.get("name") or Path(lfv_path).stem

    try:
        data = VariogramData(
            name=name,
            sill=raw["normalised_total_sill"],
            nugget=raw.get("normalised_nugget", 0.0),
            is_rotation_fixed=True,
            structures=structures,
            data_variance=meta.get("variance"),
            modelling_space=meta.get("modelling_space"),
            description=meta.get("description"),
        )
    except Exception as e:
        output.emit_error(f"Failed to build VariogramData: {e}")

    creds = await require_credentials()
    env = make_environment(creds, workspace)

    with tempfile.TemporaryDirectory() as cache_dir:
        cache = Cache(cache_dir, mkdir=False)
        async with make_connector(creds) as connector:
            context = StaticContext.from_environment(env, connector, cache=cache)
            try:
                result = await Variogram.create(context=context, data=data)
            except Exception as exc:
                output.emit_error(f"Failed to create Variogram: {exc}")

    out = {
        "id": str(result.metadata.id),
        "name": result.name,
        "path": result.metadata.path,
        "type": str(result.metadata.schema_id),
        "version_id": result.metadata.version_id,
        "sill": data.sill,
        "nugget": data.nugget,
        "structure_count": len(structures),
        "source": lfv_path,
    }
    output.emit(
        out,
        plain=f"Created Variogram '{result.name}' from .lfv with {len(structures)} structure(s) ({result.metadata.id})",
    )


@app.command("example-json")
def example_json() -> None:
    """Print an example variogram JSON definition to stdout."""
    typer.echo(_EXAMPLE_JSON)
