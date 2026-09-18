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

from evo.blockmodels.endpoints.models import BBox, BBoxXYZ, FloatRange, IntRange
from evo.cli import output


def _split_six(value: str, flag: str) -> list[str]:
    parts = value.split(",")
    if len(parts) != 6:
        output.emit_error(f"{flag} must be 6 comma-separated numbers: 'i0,i1,j0,j1,k0,k1', got {value!r}.")
    return parts


def parse_bbox_ijk(value: str) -> BBox:
    """Parse '--bbox-ijk i0,i1,j0,j1,k0,k1' into a BBox."""
    parts = _split_six(value, "--bbox-ijk")
    try:
        i0, i1, j0, j1, k0, k1 = (int(p) for p in parts)
    except ValueError:
        output.emit_error(f"--bbox-ijk must be 6 integers, got {value!r}.")
    return BBox(
        i_minmax=IntRange(min=i0, max=i1),
        j_minmax=IntRange(min=j0, max=j1),
        k_minmax=IntRange(min=k0, max=k1),
    )


def parse_bbox_xyz(value: str) -> BBoxXYZ:
    """Parse '--bbox-xyz x0,x1,y0,y1,z0,z1' into a BBoxXYZ."""
    parts = _split_six(value, "--bbox-xyz")
    try:
        x0, x1, y0, y1, z0, z1 = (float(p) for p in parts)
    except ValueError:
        output.emit_error(f"--bbox-xyz must be 6 numbers, got {value!r}.")
    return BBoxXYZ(
        x_minmax=FloatRange(min=x0, max=x1),
        y_minmax=FloatRange(min=y0, max=y1),
        z_minmax=FloatRange(min=z0, max=z1),
    )


def parse_bbox_option(bbox_ijk: str | None, bbox_xyz: str | None):
    """Resolve mutually-exclusive --bbox-ijk/--bbox-xyz options into a BBox|BBoxXYZ, or None if neither given."""
    if bbox_ijk and bbox_xyz:
        output.emit_error("provide only one of --bbox-ijk or --bbox-xyz")
    if bbox_ijk:
        return parse_bbox_ijk(bbox_ijk)
    if bbox_xyz:
        return parse_bbox_xyz(bbox_xyz)
    return None
