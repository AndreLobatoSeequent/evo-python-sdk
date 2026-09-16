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
from evo.blockmodels.endpoints.models import ReportSpecificationWithLastRunInfo
from evo.cli import output
from evo.cli._connector import make_connector, make_environment, require_credentials

app = typer.Typer(help="Manage block model report specifications.")


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _spec_to_dict(spec: ReportSpecificationWithLastRunInfo) -> dict:
    return {
        "report_specification_uuid": str(spec.report_specification_uuid),
        "name": spec.name,
        "description": spec.description,
        "revision": spec.revision,
        "autorun": spec.autorun,
        "block_model_uuid": str(spec.bm_uuid),
        "mass_unit_id": spec.mass_unit_id,
        "null_values_policy": spec.null_values_policy.value if hasattr(spec.null_values_policy, "value") else spec.null_values_policy,
        "negative_values_policy": spec.negative_values_policy.value if hasattr(spec.negative_values_policy, "value") else spec.negative_values_policy,
        "columns": [
            {
                "col_id": str(c.col_id),
                "label": c.label,
                "aggregation": c.aggregation.value if hasattr(c.aggregation, "value") else c.aggregation,
                "output_unit_id": c.output_unit_id,
            }
            for c in spec.columns
        ],
        "categories": [
            {
                "col_id": str(c.col_id),
                "label": c.label,
                "values": c.values,
            }
            for c in (spec.categories or [])
        ],
        "density_col_id": str(spec.density_col_id) if spec.density_col_id else None,
        "density_value": spec.density_value,
        "density_unit_id": spec.density_unit_id,
        "cutoff_col_id": str(spec.cutoff_col_id) if spec.cutoff_col_id else None,
        "cutoff_values": spec.cutoff_values,
        "last_result_version_id": spec.last_result_version_id,
        "last_result_created_at": spec.last_result_created_at.isoformat() if spec.last_result_created_at else None,
    }


def _format_spec_plain(data: dict, *, prefix: str = "") -> str:
    lines = [f"{prefix}{data['name']}  ({data['report_specification_uuid']})"]
    if data.get("description"):
        lines.append(f"  Description  {data['description']}")
    lines.append(f"  Block model  {data['block_model_uuid']}")
    lines.append(f"  Revision     {data['revision']}")
    lines.append(f"  Mass unit    {data['mass_unit_id']}  autorun: {'yes' if data['autorun'] else 'no'}")

    # Density
    if data.get("density_col_id"):
        lines.append(f"  Density      column {data['density_col_id']}")
    elif data.get("density_value") is not None:
        lines.append(f"  Density      {data['density_value']} {data.get('density_unit_id', '')}")

    # Cutoff
    if data.get("cutoff_col_id"):
        cutoff_vals = ", ".join(str(v) for v in (data.get("cutoff_values") or []))
        lines.append(f"  Cutoff       col {data['cutoff_col_id']}  values: {cutoff_vals or '(none)'}")

    # Last run
    if data.get("last_result_created_at"):
        lines.append(f"  Last run     v{data['last_result_version_id']}  {data['last_result_created_at']}")
    else:
        lines.append("  Last run     (never)")

    # Columns
    cols = data.get("columns", [])
    lines.append(f"  Columns ({len(cols)})")
    for c in cols:
        unit = f"  {c['output_unit_id']}" if c.get("output_unit_id") else ""
        lines.append(f"    {c['label']:<30}  {c['aggregation']}{unit}")

    # Categories
    cats = data.get("categories", [])
    if cats:
        lines.append(f"  Categories ({len(cats)})")
        for c in cats:
            filter_str = f"  filter: {', '.join(c['values'])}" if c.get("values") else ""
            lines.append(f"    {c['label']}{filter_str}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@app.command("list")
def list_reports(
    bm_id: str = typer.Argument(help="Block model UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """List report specifications for a block model."""
    asyncio.run(_do_list(bm_id, workspace))


async def _do_list(bm_id: str, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            page = await client._reports_api.list_block_model_report_specifications(
                workspace_id=str(env.workspace_id),
                org_id=str(env.org_id),
                bm_id=bm_id,
            )
        except Exception as exc:
            output.emit_error(str(exc))

    items = [_spec_to_dict(s) for s in page.results]

    if not items:
        output.emit(items, plain="No report specifications found.")
        return

    # Plain: one line per spec
    col_w = max(len(s["name"]) for s in items)
    plain_lines = []
    for s in items:
        last = f"v{s['last_result_version_id']}  {s['last_result_created_at']}" if s["last_result_created_at"] else "(never)"
        autorun = "autorun" if s["autorun"] else "manual"
        plain_lines.append(f"{s['name']:<{col_w}}  {s['report_specification_uuid']}  {autorun:<8}  {last}")

    output.emit(items, plain="\n".join(plain_lines))


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

@app.command()
def get(
    bm_id: str = typer.Argument(help="Block model UUID"),
    spec_id: str = typer.Argument(help="Report specification UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Get a report specification, including columns, categories, and last run info."""
    asyncio.run(_do_get(bm_id, spec_id, workspace))


async def _do_get(bm_id: str, spec_id: str, workspace: str | None) -> None:
    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            spec = await client._reports_api.get_report_specification(
                rs_id=spec_id,
                workspace_id=str(env.workspace_id),
                org_id=str(env.org_id),
                bm_id=bm_id,
            )
        except Exception as exc:
            output.emit_error(str(exc))

    data = _spec_to_dict(spec)
    output.emit(data, plain=_format_spec_plain(data))
