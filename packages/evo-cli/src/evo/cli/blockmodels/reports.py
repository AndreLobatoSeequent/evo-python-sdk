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
from typing import TYPE_CHECKING, Optional
from uuid import UUID

import typer

from evo.cli import output
from evo.cli._connector import make_connector, make_environment, require_credentials

if TYPE_CHECKING:
    from evo.blockmodels import BlockModelAPIClient
    from evo.blockmodels.endpoints.models import (
        ReportAggregation,
        ReportCategory,
        ReportColumn,
        ReportComparison,
        ReportComparisonJobResult,
        ReportResult,
        ReportRunResult,
        ReportSpecificationWithJobUrl,
        ReportSpecificationWithLastRunInfo,
    )

app = typer.Typer(help="Manage block model report specifications.")


def _api_error(exc: Exception, *, not_found: str = "not found") -> None:
    """Surface API errors with clean, human-readable messages."""
    from evo.common.exceptions import (
        BaseTypedError,
        EvoAPIException,
        ForbiddenException,
        NotFoundException,
        UnauthorizedException,
    )

    if isinstance(exc, NotFoundException):
        output.emit_error(not_found, code="not_found")
    elif isinstance(exc, (UnauthorizedException, ForbiddenException)):
        output.emit_error(
            "access denied — check your permissions or try 'evo auth login'",
            code="access_denied",
        )
    elif isinstance(exc, BaseTypedError):
        msg = exc.detail if exc.detail else exc.title
        output.emit_error(msg)
    elif isinstance(exc, EvoAPIException):
        msg = f"API error ({exc.status})"
        if exc.reason:
            msg += f": {exc.reason}"
        output.emit_error(msg)
    else:
        raise exc


results_app = typer.Typer(help="Manage report results.")
app.add_typer(results_app, name="results")


# ---------------------------------------------------------------------------
# Serialisation helpers — Phase 1
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
        "null_values_policy": spec.null_values_policy.value
        if hasattr(spec.null_values_policy, "value")
        else spec.null_values_policy,
        "negative_values_policy": spec.negative_values_policy.value
        if hasattr(spec.negative_values_policy, "value")
        else spec.negative_values_policy,
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


def _spec_with_job_to_dict(spec: ReportSpecificationWithJobUrl) -> dict:
    return {
        "report_specification_uuid": str(spec.report_specification_uuid),
        "name": spec.name,
        "description": spec.description,
        "revision": spec.revision,
        "autorun": spec.autorun,
        "block_model_uuid": str(spec.bm_uuid),
        "mass_unit_id": spec.mass_unit_id,
        "null_values_policy": spec.null_values_policy.value
        if hasattr(spec.null_values_policy, "value")
        else spec.null_values_policy,
        "negative_values_policy": spec.negative_values_policy.value
        if hasattr(spec.negative_values_policy, "value")
        else spec.negative_values_policy,
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
        "job_url": str(spec.job_url) if spec.job_url else None,
    }


def _format_spec_plain(data: dict, *, prefix: str = "") -> str:
    lines = [f"{prefix}{data['name']}  ({data['report_specification_uuid']})"]
    if data.get("description"):
        lines.append(f"  Description  {data['description']}")
    lines.append(f"  Block model  {data['block_model_uuid']}")
    lines.append(f"  Revision     {data['revision']}")
    lines.append(f"  Mass unit    {data['mass_unit_id']}  autorun: {'yes' if data['autorun'] else 'no'}")

    if data.get("density_col_id"):
        lines.append(f"  Density      column {data['density_col_id']}")
    elif data.get("density_value") is not None:
        lines.append(f"  Density      {data['density_value']} {data.get('density_unit_id', '')}")

    if data.get("cutoff_col_id"):
        cutoff_vals = ", ".join(str(v) for v in (data.get("cutoff_values") or []))
        lines.append(f"  Cutoff       col {data['cutoff_col_id']}  values: {cutoff_vals or '(none)'}")
    elif data.get("cutoff_values"):
        cutoff_vals = ", ".join(str(v) for v in data["cutoff_values"])
        lines.append(f"  Cutoff       {cutoff_vals}")

    if data.get("last_result_created_at"):
        lines.append(f"  Last run     v{data['last_result_version_id']}  {data['last_result_created_at']}")
    elif "last_result_version_id" in data:
        lines.append("  Last run     (never)")

    if data.get("job_url"):
        lines.append(f"  Job          {data['job_url']}")

    cols = data.get("columns", [])
    lines.append(f"  Columns ({len(cols)})")
    for c in cols:
        unit = f"  {c['output_unit_id']}" if c.get("output_unit_id") else ""
        lines.append(f"    {c['label']:<30}  {c['aggregation']}{unit}")

    cats = data.get("categories", [])
    if cats:
        lines.append(f"  Categories ({len(cats)})")
        for c in cats:
            filter_str = f"  filter: {', '.join(c['values'])}" if c.get("values") else ""
            lines.append(f"    {c['label']}{filter_str}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 2: column resolution and spec parsing helpers
# ---------------------------------------------------------------------------


def _parse_aggregation(text: str) -> ReportAggregation:
    from evo.blockmodels.endpoints.models import ReportAggregation

    agg_aliases: dict[str, ReportAggregation] = {
        "SUM": ReportAggregation.SUM,
        "MASS_AVERAGE": ReportAggregation.MASS_AVERAGE,
        "AVG": ReportAggregation.MASS_AVERAGE,
        "AVERAGE": ReportAggregation.MASS_AVERAGE,
    }
    key = text.strip().upper()
    if key not in agg_aliases:
        raise typer.BadParameter(f"Unknown aggregation '{text}'. Valid: SUM, MASS_AVERAGE (or AVG).")
    return agg_aliases[key]


def _parse_column_spec(entry: str, col_map: dict[str, str]) -> ReportColumn:
    """Parse 'Title:AGG[:output_unit]' into a ReportColumn.  Title is resolved to col_id."""
    from evo.blockmodels.endpoints.models import ReportColumn

    parts = entry.split(":", 2)
    if len(parts) < 2:
        raise typer.BadParameter(f"--column '{entry}': expected format Title:AGGREGATION[:unit]")
    title, agg_str = parts[0].strip(), parts[1].strip()
    unit = parts[2].strip() if len(parts) == 3 else None
    if title not in col_map:
        raise typer.BadParameter(
            f"--column '{entry}': column '{title}' not found in latest version. Available: {', '.join(sorted(col_map))}"
        )
    return ReportColumn(
        col_id=UUID(col_map[title]),
        label=title,
        aggregation=_parse_aggregation(agg_str),
        output_unit_id=unit or "",
    )


def _parse_category_spec(entry: str, col_map: dict[str, str]) -> ReportCategory:
    """Parse 'Title' or 'Title:Label' into a ReportCategory."""
    from evo.blockmodels.endpoints.models import ReportCategory

    parts = entry.split(":", 1)
    title = parts[0].strip()
    label = parts[1].strip() if len(parts) == 2 else title
    if title not in col_map:
        raise typer.BadParameter(
            f"--category '{entry}': column '{title}' not found in latest version. "
            f"Available: {', '.join(sorted(col_map))}"
        )
    return ReportCategory(col_id=UUID(col_map[title]), label=label, values=None)


async def _interactive_select_workspace(creds) -> UUID:
    """List the user's workspaces and prompt them to pick one; saves the choice."""
    from uuid import UUID as _UUID

    from evo.cli._session import build_connector
    from evo.cli.state import CurrentSelection, load_selection, save_selection
    from evo.workspaces import WorkspaceAPIClient

    output.emit_panel(
        "Select workspace",
        [
            "No workspace is currently selected.",
            "Choose one to continue — your selection will be saved for future commands.",
        ],
    )
    typer.echo("  Fetching workspaces…")

    async with build_connector(creds.hub_url, creds) as connector:
        ws_client = WorkspaceAPIClient(connector, creds.org_id)
        try:
            workspaces = await ws_client.list_all_workspaces()
        except Exception as exc:
            _api_error(exc, not_found="workspaces not found")

    if not workspaces:
        output.emit_error("No workspaces found in your organization.")

    labels = [f"{ws.display_name:<40}  {ws.id}" for ws in workspaces]
    for i, label in enumerate(labels, 1):
        typer.echo(f"  {i:>3})  {label}")
    typer.echo("")

    while True:
        raw = typer.prompt("Workspace", default="1").strip()
        try:
            idx = int(raw)
        except ValueError:
            typer.echo(f"  Enter a number between 1 and {len(workspaces)}.", err=True)
            continue
        if idx < 1 or idx > len(workspaces):
            typer.echo(f"  Enter a number between 1 and {len(workspaces)}.", err=True)
            continue
        break

    selected = workspaces[idx - 1]
    existing = load_selection()
    save_selection(
        CurrentSelection(
            schema_version=existing.schema_version,
            org_id=existing.org_id,
            org_name=existing.org_name,
            hub_code=existing.hub_code,
            hub_url=existing.hub_url,
            hub_display_name=existing.hub_display_name,
            workspace_id=selected.id,
            workspace_name=selected.display_name,
        )
    )
    typer.echo(f"  Workspace set to: {selected.display_name}")
    return _UUID(str(selected.id))


async def _build_col_map(client: BlockModelAPIClient, bm_id: str) -> dict[str, str]:
    """Return {col_title: col_id_str} for the latest version of a block model."""
    versions = await client.list_versions(UUID(bm_id))
    if not versions:
        output.emit_error("Block model has no versions; cannot resolve column names.")
        raise typer.Exit(1)
    version = await client.get_version(UUID(bm_id), versions[0].version_uuid)
    return {c.title: c.col_id for c in version.columns}


# ---------------------------------------------------------------------------
# Phase 3: result table renderer
# ---------------------------------------------------------------------------


def _fmt_num(v: float | int | None) -> str:
    if v is None:
        return "-"
    if isinstance(v, int):
        return f"{v:,}"
    if v == int(v) and abs(v) < 1e15:
        return f"{int(v):,}"
    return f"{v:,.4g}"


def _result_to_dict(result: ReportResult) -> dict:
    return {
        "report_result_uuid": str(result.report_result_uuid),
        "report_specification_uuid": str(result.report_specification_uuid),
        "report_specification_name": result.report_specification_name,
        "report_specification_revision": result.report_specification_revision,
        "version_id": result.version_id,
        "version_uuid": str(result.version_uuid) if result.version_uuid else None,
        "version_created_at": result.version_created_at.isoformat(),
        "bm_uuid": str(result.bm_uuid),
        "categories": [{"col_id": str(c.col_id), "label": c.label} for c in result.categories],
        "value_columns": [
            {"col_id": str(c.col_id) if c.col_id else None, "label": c.label, "unit_id": c.unit_id}
            for c in result.value_columns
        ],
        "result_sets": [
            {
                "cutoff_value": rs.cutoff_value,
                "rows": [{"categories": list(r.categories), "values": list(r.values)} for r in rs.rows],
            }
            for rs in result.result_sets
        ],
        "warnings": [{"type": str(w.warning_type), "message": w.message} for w in result.warnings]
        if result.warnings
        else [],
    }


def _format_result_table(result: ReportResult) -> str:
    cat_labels = [c.label for c in result.categories]
    val_labels = [f"{c.label} ({c.unit_id})" if c.unit_id else c.label for c in result.value_columns]

    has_cutoff = any(rs.cutoff_value is not None for rs in result.result_sets)
    header_parts: list[str] = []
    if has_cutoff:
        header_parts.append("cutoff")
    header_parts.extend(cat_labels)
    header_parts.extend(val_labels)

    # Build raw rows
    raw_rows: list[list[str]] = []
    for rs in result.result_sets:
        for row in rs.rows:
            cells: list[str] = []
            if has_cutoff:
                cells.append(_fmt_num(rs.cutoff_value))
            for v in row.categories:
                cells.append("(total)" if v is None else str(v))
            for v in row.values:
                cells.append(_fmt_num(v))
            raw_rows.append(cells)

    if not raw_rows:
        return "(no result rows)"

    # Compute column widths
    widths = [len(h) for h in header_parts]
    for row in raw_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return "  ".join(c.rjust(widths[i]) for i, c in enumerate(cells))

    sep = "  ".join("-" * w for w in widths)
    lines = [
        f"{result.report_specification_name}  ({result.report_specification_uuid})  rev.{result.report_specification_revision}",
        f"v{result.version_id}  {result.version_created_at.isoformat()[:10]}",
        "",
        fmt_row(header_parts),
        sep,
    ]
    for row in raw_rows:
        lines.append(fmt_row(row))

    if result.warnings:
        lines.append("")
        for w in result.warnings:
            lines.append(f"  Warning: {w.warning_type}  {w.message or ''}")

    return "\n".join(lines)


def _format_comparison_table(comp: ReportComparison) -> str:
    cat_labels = [c.label for c in comp.categories]
    val_labels = [f"{c.label} ({c.unit_id})" if c.unit_id else c.label for c in comp.value_columns]

    has_cutoff = any(rs.cutoff_value is not None for rs in comp.result_sets)
    header_parts: list[str] = []
    if has_cutoff:
        header_parts.append("cutoff")
    header_parts.extend(cat_labels)
    header_parts.extend(val_labels)

    raw_rows: list[list[str]] = []
    for rs in comp.result_sets:
        for row in rs.rows:
            cells: list[str] = []
            if has_cutoff:
                cells.append(_fmt_num(rs.cutoff_value))
            for v in row.categories:
                cells.append("(total)" if v is None else str(v))
            for cmpv in row.values:
                pct = f" ({cmpv.percent:+.1f}%)" if cmpv.percent is not None else ""
                cells.append(f"{_fmt_num(cmpv.from_value)} → {_fmt_num(cmpv.to_value)}{pct}")
            raw_rows.append(cells)

    if not raw_rows:
        return "(no comparison rows)"

    widths = [len(h) for h in header_parts]
    for row in raw_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells))

    sep = "  ".join("-" * w for w in widths)

    from_info = comp.from_result
    to_info = comp.to_result
    lines = [
        f"{comp.report_specification_name}  ({comp.report_specification_uuid})  rev.{comp.report_specification_revision}",
        f"From v{from_info.version_id}  ({from_info.version_created_at.isoformat()[:10]})"
        f"  →  To v{to_info.version_id}  ({to_info.version_created_at.isoformat()[:10]})",
        "",
        fmt_row(header_parts),
        sep,
    ]
    for row in raw_rows:
        lines.append(fmt_row(row))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 1 commands — list, get
# ---------------------------------------------------------------------------


@app.command("list")
def list_reports(
    bm_id: UUID = typer.Argument(help="Block model UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """List report specifications for a block model."""
    asyncio.run(_do_list(str(bm_id), workspace))


async def _do_list(bm_id: str, workspace: str | None) -> None:
    from evo.blockmodels import BlockModelAPIClient

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
            _api_error(exc, not_found="block model not found")

    items = [_spec_to_dict(s) for s in page.results]

    if not items:
        output.emit(items, plain="No report specifications found.")
        return

    col_w = max(len(s["name"]) for s in items)
    plain_lines = []
    for s in items:
        last = (
            f"v{s['last_result_version_id']}  {s['last_result_created_at']}"
            if s["last_result_created_at"]
            else "(never)"
        )
        autorun = "autorun" if s["autorun"] else "manual"
        plain_lines.append(f"{s['name']:<{col_w}}  {s['report_specification_uuid']}  {autorun:<8}  {last}")

    output.emit(items, plain="\n".join(plain_lines))


@app.command()
def get(
    bm_id: UUID = typer.Argument(help="Block model UUID"),
    spec_id: UUID = typer.Argument(help="Report specification UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Get a report specification, including columns, categories, and last run info."""
    asyncio.run(_do_get(str(bm_id), str(spec_id), workspace))


async def _do_get(bm_id: str, spec_id: str, workspace: str | None) -> None:
    from evo.blockmodels import BlockModelAPIClient

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
            _api_error(exc, not_found="report specification not found")

    data = _spec_to_dict(spec)
    output.emit(data, plain=_format_spec_plain(data))


# ---------------------------------------------------------------------------
# Phase 2 commands — create, update
# ---------------------------------------------------------------------------


@app.command()
def create(
    bm_id: Optional[UUID] = typer.Argument(default=None, help="Block model UUID (optional with --interactive)"),
    name: Optional[str] = typer.Option(None, "--name", help="Report specification name"),
    description: Optional[str] = typer.Option(None, "--description", help="Description"),
    column: list[str] = typer.Option([], "--column", help="Value column: Title:AGGREGATION[:unit]  (repeat)"),
    category: list[str] = typer.Option([], "--category", help="Category column: Title or Title:Label  (repeat, max 5)"),
    density_column: Optional[str] = typer.Option(
        None, "--density-column", help="Column title to use for block density"
    ),
    density_value: Optional[float] = typer.Option(None, "--density-value", help="Fixed density value"),
    density_unit: Optional[str] = typer.Option(None, "--density-unit", help="Density unit (e.g. t/m3)"),
    mass_unit: Optional[str] = typer.Option(None, "--mass-unit", help="Mass unit (e.g. t)"),
    cutoff_column: Optional[str] = typer.Option(
        None, "--cutoff-column", help="Column title to use for cutoff evaluation"
    ),
    cutoff: list[float] = typer.Option([], "--cutoff", help="Cutoff value  (repeat, max 20)"),
    autorun: Optional[bool] = typer.Option(None, "--autorun/--no-autorun", help="Auto-run on new version"),
    null_values_policy: Optional[str] = typer.Option(
        None,
        "--null-values-policy",
        help="How to handle null block values: IGNORE_BLOCK, ZERO, IGNORE_VALUE, MARK_AS_INVALID",
    ),
    negative_values_policy: Optional[str] = typer.Option(
        None,
        "--negative-values-policy",
        help="How to handle negative block values: IGNORE_BLOCK, USE, ZERO, IGNORE_VALUE, MARK_AS_INVALID",
    ),
    run_now: Optional[bool] = typer.Option(
        None, "--run-now/--no-run-now", help="Trigger a run immediately after creation"
    ),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Guided interactive wizard"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Create a new report specification."""
    if interactive:
        asyncio.run(
            _do_create_interactive(
                str(bm_id) if bm_id else None,
                name,
                column or None,
                category or None,
                density_column,
                density_value,
                density_unit,
                mass_unit,
                cutoff_column,
                list(cutoff) or None,
                autorun,
                null_values_policy,
                negative_values_policy,
                run_now,
                workspace,
            )
        )
    else:
        if bm_id is None:
            output.emit_error("bm_id is required when not using --interactive.")
        if name is None:
            output.emit_error("--name is required when not using --interactive.")
        if not column:
            output.emit_error("At least one --column is required when not using --interactive.")
        if mass_unit is None:
            output.emit_error("--mass-unit is required when not using --interactive.")
        asyncio.run(
            _do_create(
                str(bm_id),
                name,
                description,
                column,
                category,
                density_column,
                density_value,
                density_unit,
                mass_unit,
                cutoff_column,
                cutoff,
                autorun if autorun is not None else True,
                null_values_policy,
                negative_values_policy,
                run_now if run_now is not None else True,
                workspace,
            )
        )


async def _do_create_interactive(
    bm_id: str | None,
    name: str | None,
    columns: list[str] | None,
    categories: list[str] | None,
    density_column: str | None,
    density_value: float | None,
    density_unit: str | None,
    mass_unit: str | None,
    cutoff_column: str | None,
    cutoffs: list[float] | None,
    autorun: bool | None,
    null_values_policy: str | None,
    negative_values_policy: str | None,
    run_now: bool | None,
    workspace: str | None,
) -> None:
    from evo.blockmodels import BlockModelAPIClient
    from evo.blockmodels.endpoints.models import (
        CreateReportNegativeValuesPolicy,
        CreateReportNullValuesPolicy,
        CreateReportSpecification,
    )
    from evo.cli.blockmodels.interactive import InteractiveReportWizard

    if not output.is_interactive():
        output.emit_error("--interactive cannot be used in agent/non-interactive mode.")

    creds = await require_credentials()

    # Resolve workspace — may require interactive selection if not already saved
    from evo.cli.config import get_workspace_id

    workspace_id = get_workspace_id(workspace)
    if workspace_id is None:
        workspace_id = await _interactive_select_workspace(creds)

    env = make_environment(creds, workspace_id)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        wizard = InteractiveReportWizard(client, env, bm_id=bm_id)
        try:
            kwargs = await wizard.run(
                name=name,
                columns=columns,
                categories=categories,
                mass_unit=mass_unit,
                density_column=density_column,
                density_value=density_value,
                density_unit=density_unit,
                cutoff_column=cutoff_column,
                cutoffs=cutoffs,
                autorun=autorun,
                null_values_policy=null_values_policy,
                negative_values_policy=negative_values_policy,
                run_now=run_now,
            )
        except typer.Exit:
            raise

        # Extract resolved objects from wizard output
        resolved_columns = kwargs.pop("_resolved_columns")
        resolved_categories = kwargs.pop("_resolved_categories")
        density_col_id = kwargs.pop("_density_col_id")
        cutoff_col_id = kwargs.pop("_cutoff_col_id")
        resolved_bm_id: str = kwargs["bm_id"]
        resolved_name: str = kwargs["name"]
        resolved_mass_unit: str = kwargs["mass_unit"]
        resolved_run_now: bool = kwargs["run_now"]
        resolved_autorun: bool = kwargs["autorun"]
        resolved_density_value: float | None = kwargs["density_value"]
        resolved_density_unit: str | None = kwargs["density_unit"]
        resolved_cutoffs: list[float] = kwargs["cutoff_values"]
        resolved_null_policy: str | None = kwargs.get("null_values_policy")
        resolved_neg_policy: str | None = kwargs.get("negative_values_policy")

        spec_kwargs: dict = dict(
            name=resolved_name,
            description=None,
            autorun=resolved_autorun,
            columns=resolved_columns,
            categories=resolved_categories,
            mass_unit_id=resolved_mass_unit,
            density_col_id=density_col_id,
            density_value=resolved_density_value,
            density_unit_id=resolved_density_unit,
            cutoff_col_id=cutoff_col_id,
            cutoff_values=resolved_cutoffs if resolved_cutoffs else None,
        )
        spec_kwargs["null_values_policy"] = CreateReportNullValuesPolicy(
            resolved_null_policy if resolved_null_policy else "IGNORE_VALUE"
        )
        spec_kwargs["negative_values_policy"] = CreateReportNegativeValuesPolicy(
            resolved_neg_policy if resolved_neg_policy else "IGNORE_VALUE"
        )
        spec_body = CreateReportSpecification(**spec_kwargs)

        try:
            spec = await client._reports_api.create_report_specification(
                workspace_id=str(env.workspace_id),
                org_id=str(env.org_id),
                bm_id=resolved_bm_id,
                create_report_specification=spec_body,
                run_now=resolved_run_now,
            )
        except Exception as exc:
            _api_error(exc, not_found="block model not found")

    data = _spec_with_job_to_dict(spec)
    output.emit(data, plain=_format_spec_plain(data, prefix="Created "))


async def _do_create(
    bm_id: str,
    name: str,
    description: str | None,
    column_specs: list[str],
    category_specs: list[str],
    density_column: str | None,
    density_value: float | None,
    density_unit: str | None,
    mass_unit: str,
    cutoff_column: str | None,
    cutoff_values: list[float],
    autorun: bool,
    null_values_policy: str | None,
    negative_values_policy: str | None,
    run_now: bool,
    workspace: str | None,
) -> None:
    from evo.blockmodels import BlockModelAPIClient
    from evo.blockmodels.endpoints.models import (
        CreateReportNegativeValuesPolicy,
        CreateReportNullValuesPolicy,
        CreateReportSpecification,
    )

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)

        needs_resolution = bool(column_specs or category_specs or density_column or cutoff_column)
        col_map: dict[str, str] = {}
        if needs_resolution:
            col_map = await _build_col_map(client, bm_id)

        columns = [_parse_column_spec(e, col_map) for e in column_specs]
        categories = [_parse_category_spec(e, col_map) for e in category_specs] or None

        density_col_id: UUID | None = None
        if density_column:
            if density_column not in col_map:
                output.emit_error(f"--density-column '{density_column}' not found in latest version.")
                raise typer.Exit(1)
            density_col_id = UUID(col_map[density_column])

        cutoff_col_id: UUID | None = None
        if cutoff_column:
            if cutoff_column not in col_map:
                output.emit_error(f"--cutoff-column '{cutoff_column}' not found in latest version.")
                raise typer.Exit(1)
            cutoff_col_id = UUID(col_map[cutoff_column])

        spec_kwargs: dict = dict(
            name=name,
            description=description,
            autorun=autorun,
            columns=columns,
            categories=categories,
            mass_unit_id=mass_unit,
            density_col_id=density_col_id,
            density_value=float(density_value) if density_value is not None else None,
            density_unit_id=density_unit,
            cutoff_col_id=cutoff_col_id,
            cutoff_values=[float(v) for v in cutoff_values] if cutoff_values else None,
        )
        spec_kwargs["null_values_policy"] = CreateReportNullValuesPolicy(
            null_values_policy if null_values_policy else "IGNORE_VALUE"
        )
        spec_kwargs["negative_values_policy"] = CreateReportNegativeValuesPolicy(
            negative_values_policy if negative_values_policy else "IGNORE_VALUE"
        )
        spec_body = CreateReportSpecification(**spec_kwargs)

        try:
            spec = await client._reports_api.create_report_specification(
                workspace_id=str(env.workspace_id),
                org_id=str(env.org_id),
                bm_id=bm_id,
                create_report_specification=spec_body,
                run_now=run_now,
            )
        except Exception as exc:
            _api_error(exc, not_found="block model not found")

    data = _spec_with_job_to_dict(spec)
    output.emit(data, plain=_format_spec_plain(data, prefix="Created "))


@app.command()
def update(
    bm_id: UUID = typer.Argument(help="Block model UUID"),
    spec_id: UUID = typer.Argument(help="Report specification UUID"),
    name: Optional[str] = typer.Option(None, "--name", help="New name"),
    description: Optional[str] = typer.Option(None, "--description", help="New description"),
    column: list[str] = typer.Option([], "--column", help="Replace all value columns: Title:AGG[:unit]  (repeat)"),
    category: list[str] = typer.Option(
        [], "--category", help="Replace all category columns: Title or Title:Label  (repeat)"
    ),
    density_column: Optional[str] = typer.Option(None, "--density-column", help="Column title for block density"),
    density_value: Optional[float] = typer.Option(None, "--density-value", help="Fixed density value"),
    density_unit: Optional[str] = typer.Option(None, "--density-unit", help="Density unit"),
    mass_unit: Optional[str] = typer.Option(None, "--mass-unit", help="Mass unit"),
    cutoff_column: Optional[str] = typer.Option(None, "--cutoff-column", help="Column title for cutoff evaluation"),
    cutoff: list[float] = typer.Option([], "--cutoff", help="Cutoff value  (repeat)"),
    autorun: Optional[bool] = typer.Option(None, "--autorun/--no-autorun", help="Auto-run on new version"),
    run_now: bool = typer.Option(False, "--run-now/--no-run-now", help="Trigger a run immediately after update"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Update an existing report specification. Only provided options are changed."""
    asyncio.run(
        _do_update(
            str(bm_id),
            str(spec_id),
            name,
            description,
            column,
            category,
            density_column,
            density_value,
            density_unit,
            mass_unit,
            cutoff_column,
            cutoff,
            autorun,
            run_now,
            workspace,
        )
    )


async def _do_update(
    bm_id: str,
    spec_id: str,
    name: str | None,
    description: str | None,
    column_specs: list[str],
    category_specs: list[str],
    density_column: str | None,
    density_value: float | None,
    density_unit: str | None,
    mass_unit: str | None,
    cutoff_column: str | None,
    cutoff_values: list[float],
    autorun: bool | None,
    run_now: bool,
    workspace: str | None,
) -> None:
    from evo.blockmodels import BlockModelAPIClient
    from evo.blockmodels.endpoints.models import UpdateReportSpecification

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)

        # Fetch existing spec silently for defaults
        try:
            existing = await client._reports_api.get_report_specification(
                rs_id=spec_id,
                workspace_id=str(env.workspace_id),
                org_id=str(env.org_id),
                bm_id=bm_id,
            )
        except Exception as exc:
            _api_error(exc, not_found="report specification not found")

        needs_resolution = bool(column_specs or category_specs or density_column or cutoff_column)
        col_map: dict[str, str] = {}
        if needs_resolution:
            col_map = await _build_col_map(client, bm_id)

        columns = [_parse_column_spec(e, col_map) for e in column_specs] if column_specs else list(existing.columns)
        categories = (
            [_parse_category_spec(e, col_map) for e in category_specs] if category_specs else existing.categories
        )

        density_col_id: UUID | None = existing.density_col_id
        eff_density_value: float | None = existing.density_value
        eff_density_unit: str | None = existing.density_unit_id
        if density_column:
            if density_column not in col_map:
                output.emit_error(f"--density-column '{density_column}' not found in latest version.")
                raise typer.Exit(1)
            density_col_id = UUID(col_map[density_column])
            eff_density_value = None
            eff_density_unit = None
        elif density_value is not None:
            density_col_id = None
            eff_density_value = float(density_value)
            eff_density_unit = density_unit or existing.density_unit_id

        cutoff_col_id: UUID | None = existing.cutoff_col_id
        if cutoff_column:
            if cutoff_column not in col_map:
                output.emit_error(f"--cutoff-column '{cutoff_column}' not found in latest version.")
                raise typer.Exit(1)
            cutoff_col_id = UUID(col_map[cutoff_column])

        eff_cutoffs = [float(v) for v in cutoff_values] if cutoff_values else existing.cutoff_values

        spec_body = UpdateReportSpecification(
            name=name if name is not None else existing.name,
            description=description if description is not None else existing.description,
            autorun=autorun if autorun is not None else existing.autorun,
            columns=columns,
            categories=categories,
            mass_unit_id=mass_unit if mass_unit is not None else existing.mass_unit_id,
            density_col_id=density_col_id,
            density_value=eff_density_value,
            density_unit_id=eff_density_unit,
            cutoff_col_id=cutoff_col_id,
            cutoff_values=eff_cutoffs,
        )

        try:
            spec = await client._reports_api.update_report_specification(
                rs_id=spec_id,
                workspace_id=str(env.workspace_id),
                org_id=str(env.org_id),
                bm_id=bm_id,
                update_report_specification=spec_body,
                run_now=run_now,
            )
        except Exception as exc:
            _api_error(exc, not_found="report specification not found")

    data = _spec_with_job_to_dict(spec)
    output.emit(data, plain=_format_spec_plain(data, prefix="Updated "))


# ---------------------------------------------------------------------------
# Phase 3 commands — run, results list, results get
# ---------------------------------------------------------------------------


@app.command()
def run(
    bm_id: UUID = typer.Argument(help="Block model UUID"),
    spec_id: UUID = typer.Argument(help="Report specification UUID"),
    version_uuid: Optional[UUID] = typer.Option(
        None, "--version-uuid", help="Block model version UUID (default: latest)"
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Run a reporting job and display the result table."""
    asyncio.run(_do_run(str(bm_id), str(spec_id), str(version_uuid) if version_uuid else None, workspace))


async def _do_run(bm_id: str, spec_id: str, version_uuid_str: str | None, workspace: str | None) -> None:
    from evo.blockmodels import BlockModelAPIClient
    from evo.blockmodels.endpoints.models import ReportingJobSpec

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)

        job_spec = ReportingJobSpec(version_uuid=UUID(version_uuid_str) if version_uuid_str else None)
        try:
            job_result = await client._reports_api.run_reporting_job(
                rs_id=spec_id,
                workspace_id=str(env.workspace_id),
                org_id=str(env.org_id),
                bm_id=bm_id,
                reporting_job_spec=job_spec,
            )
        except Exception as exc:
            _api_error(exc, not_found="report specification not found")

        # Poll until done
        try:
            job_response = await client._poll_job_url(UUID(bm_id), job_result.job_uuid)
        except Exception as exc:
            output.emit_error(f"Reporting job failed: {exc}")
            raise typer.Exit(1)

        run_result: ReportRunResult = job_response.payload  # type: ignore[assignment]
        report_result_uuid = str(run_result.report_result_uuid)

        try:
            result = await client._reports_api.get_report_result(
                rs_id=spec_id,
                report_result_uuid=report_result_uuid,
                workspace_id=str(env.workspace_id),
                org_id=str(env.org_id),
                bm_id=bm_id,
            )
        except Exception as exc:
            _api_error(exc, not_found="report result not found")

    data = _result_to_dict(result)
    output.emit(data, plain=_format_result_table(result))


@results_app.command("list")
def results_list(
    bm_id: UUID = typer.Argument(help="Block model UUID"),
    spec_id: UUID = typer.Argument(help="Report specification UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """List all results for a report specification."""
    asyncio.run(_do_results_list(str(bm_id), str(spec_id), workspace))


async def _do_results_list(bm_id: str, spec_id: str, workspace: str | None) -> None:
    from evo.blockmodels import BlockModelAPIClient

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            page = await client._reports_api.get_report_results_list(
                rs_id=spec_id,
                workspace_id=str(env.workspace_id),
                org_id=str(env.org_id),
                bm_id=bm_id,
            )
        except Exception as exc:
            _api_error(exc, not_found="report specification not found")

    if not page.results:
        output.emit([], plain="No results found.")
        return

    items = [
        {
            "report_result_uuid": str(r.report_result_uuid),
            "version_id": r.version_id,
            "version_uuid": str(r.version_uuid) if r.version_uuid else None,
            "report_result_created_at": r.report_result_created_at.isoformat(),
            "version_created_at": r.version_created_at.isoformat(),
        }
        for r in page.results
    ]

    plain_lines = []
    for item in items:
        plain_lines.append(f"{item['report_result_uuid']}  v{item['version_id']}  {item['report_result_created_at']}")
    output.emit(items, plain="\n".join(plain_lines))


@results_app.command("get")
def results_get(
    bm_id: UUID = typer.Argument(help="Block model UUID"),
    spec_id: UUID = typer.Argument(help="Report specification UUID"),
    result_uuid: UUID = typer.Argument(help="Report result UUID"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Get a report result and display it as a table."""
    asyncio.run(_do_results_get(str(bm_id), str(spec_id), str(result_uuid), workspace))


async def _do_results_get(bm_id: str, spec_id: str, result_uuid: str, workspace: str | None) -> None:
    from evo.blockmodels import BlockModelAPIClient

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)
        try:
            result = await client._reports_api.get_report_result(
                rs_id=spec_id,
                report_result_uuid=result_uuid,
                workspace_id=str(env.workspace_id),
                org_id=str(env.org_id),
                bm_id=bm_id,
            )
        except Exception as exc:
            _api_error(exc, not_found="report result not found")

    data = _result_to_dict(result)
    output.emit(data, plain=_format_result_table(result))


# ---------------------------------------------------------------------------
# Phase 4 command — compare
# ---------------------------------------------------------------------------


@app.command()
def compare(
    bm_id: UUID = typer.Argument(help="Block model UUID"),
    spec_id: UUID = typer.Argument(help="Report specification UUID"),
    from_version: UUID = typer.Option(..., "--from", help="Baseline block model version UUID"),
    to_version: UUID = typer.Option(..., "--to", help="Comparison block model version UUID"),
    decimal_places: Optional[int] = typer.Option(None, "--decimal-places", help="Rounding for comparison (0–10)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Compare report results between two block model versions."""
    asyncio.run(_do_compare(str(bm_id), str(spec_id), str(from_version), str(to_version), decimal_places, workspace))


async def _do_compare(
    bm_id: str,
    spec_id: str,
    from_version: str,
    to_version: str,
    decimal_places: int | None,
    workspace: str | None,
) -> None:
    from evo.blockmodels import BlockModelAPIClient
    from evo.blockmodels.endpoints.models import ReportComparisonSpec

    creds = await require_credentials()
    env = make_environment(creds, workspace)
    async with make_connector(creds) as connector:
        client = BlockModelAPIClient(environment=env, connector=connector)

        comp_spec = ReportComparisonSpec(
            from_version_uuid=UUID(from_version),
            to_version_uuid=UUID(to_version),
        )
        try:
            req_result = await client._reports_api.request_report_comparison(
                rs_id=spec_id,
                workspace_id=str(env.workspace_id),
                org_id=str(env.org_id),
                bm_id=bm_id,
                report_comparison_spec=comp_spec,
            )
        except Exception as exc:
            _api_error(exc, not_found="report specification not found")

        from_result_uuid = req_result.from_result_uuid
        to_result_uuid = req_result.to_result_uuid

        if req_result.job_url:
            # Parse job UUID from the URL last segment
            job_uuid = UUID(str(req_result.job_url).rstrip("/").split("/")[-1])
            try:
                job_response = await client._poll_job_url(UUID(bm_id), job_uuid)
            except Exception as exc:
                output.emit_error(f"Comparison job failed: {exc}")
                raise typer.Exit(1)
            payload: ReportComparisonJobResult = job_response.payload  # type: ignore[assignment]
            from_result_uuid = payload.from_result_uuid
            to_result_uuid = payload.to_result_uuid

        if not from_result_uuid or not to_result_uuid:
            output.emit_error("Could not determine result UUIDs for comparison.")
            raise typer.Exit(1)

        try:
            comparison = await client._reports_api.get_report_result_comparison(
                rs_id=spec_id,
                workspace_id=str(env.workspace_id),
                org_id=str(env.org_id),
                bm_id=bm_id,
                var_from=str(from_result_uuid),
                to=str(to_result_uuid),
                decimal_places=decimal_places,
            )
        except Exception as exc:
            _api_error(exc, not_found="comparison results not found")

    data = {
        "report_specification_uuid": str(comparison.report_specification_uuid),
        "report_specification_name": comparison.report_specification_name,
        "from_result_uuid": str(from_result_uuid),
        "to_result_uuid": str(to_result_uuid),
        "from_version_id": comparison.from_result.version_id,
        "to_version_id": comparison.to_result.version_id,
        "result_sets": [
            {
                "cutoff_value": rs.cutoff_value,
                "rows": [
                    {
                        "categories": list(r.categories),
                        "values": [
                            {
                                "from_value": v.from_value,
                                "to_value": v.to_value,
                                "difference": v.difference,
                                "percent": v.percent,
                            }
                            for v in r.values
                        ],
                    }
                    for r in rs.rows
                ],
            }
            for rs in comparison.result_sets
        ],
    }
    output.emit(data, plain=_format_comparison_table(comparison))
