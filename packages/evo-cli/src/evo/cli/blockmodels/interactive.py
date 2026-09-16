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

"""Interactive wizard for creating block model report specifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import UUID

import typer

from evo.blockmodels import BlockModelAPIClient
from evo.blockmodels.endpoints.models import (
    DataType,
    ReportAggregation,
    ReportCategory,
    ReportColumn,
)
from evo.blockmodels.typed.units import UnitInfo, UnitType, get_available_units
from evo.cli import output


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

@dataclass
class ColumnMeta:
    col_id: str
    title: str
    unit_id: str | None
    data_type: DataType


_NUMERIC_TYPES = {DataType.Float64, DataType.Int64}


async def _fetch_column_meta(client: BlockModelAPIClient, bm_id: str) -> list[ColumnMeta]:
    versions = await client.list_versions(UUID(bm_id))
    if not versions:
        output.emit_error("Block model has no versions — cannot build column list.")
    version = await client.get_version(UUID(bm_id), versions[0].version_uuid)
    return [
        ColumnMeta(
            col_id=col.col_id,
            title=col.title,
            unit_id=col.unit_id,
            data_type=col.data_type,
        )
        for col in version.columns
    ]


async def _fetch_units(client: BlockModelAPIClient, env) -> list[UnitInfo]:
    try:
        return await get_available_units(client)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Low-level prompt helpers
# ---------------------------------------------------------------------------

def _print_numbered(items: list[str]) -> None:
    for i, label in enumerate(items, 1):
        typer.echo(f"  {i:>3})  {label}")


def _prompt_indices(
    prompt: str,
    count: int,
    *,
    min_count: int = 1,
    max_count: int | None = None,
    prompt_fn: Callable[[str, str], str] = typer.prompt,
) -> list[int]:
    """Prompt for comma-separated 1-based indices; loops until valid."""
    while True:
        raw = prompt_fn(prompt, "").strip()
        if not raw:
            indices: list[int] = []
        else:
            try:
                indices = [int(x.strip()) for x in raw.replace(",", " ").split()]
            except ValueError:
                typer.echo("  Enter numbers separated by commas.", err=True)
                continue
        if any(i < 1 or i > count for i in indices):
            typer.echo(f"  Numbers must be between 1 and {count}.", err=True)
            continue
        if len(indices) < min_count:
            typer.echo(f"  Select at least {min_count}.", err=True)
            continue
        if max_count is not None and len(indices) > max_count:
            typer.echo(f"  Select at most {max_count}.", err=True)
            continue
        return indices


def _prompt_single(
    prompt: str,
    count: int,
    default: int = 1,
    *,
    prompt_fn: Callable[[str, str], str] = typer.prompt,
) -> int:
    """Prompt for a single 1-based index with a default."""
    while True:
        raw = prompt_fn(prompt, str(default)).strip()
        try:
            idx = int(raw)
        except ValueError:
            typer.echo(f"  Enter a number between 1 and {count}.", err=True)
            continue
        if idx < 1 or idx > count:
            typer.echo(f"  Enter a number between 1 and {count}.", err=True)
            continue
        return idx


def _prompt_float_list(
    prompt: str,
    *,
    prompt_fn: Callable[[str, str], str] = typer.prompt,
) -> list[float]:
    """Prompt for space/comma-separated floats; loops until valid."""
    while True:
        raw = prompt_fn(prompt, "").strip()
        if not raw:
            return []
        try:
            return [float(x.strip()) for x in raw.replace(",", " ").split()]
        except ValueError:
            typer.echo("  Enter numbers separated by spaces or commas.", err=True)


def _confirm(
    prompt: str,
    default: bool = True,
    *,
    confirm_fn: Callable[[str, bool], bool] = typer.confirm,
) -> bool:
    return confirm_fn(prompt, default=default)


# ---------------------------------------------------------------------------
# Wizard class
# ---------------------------------------------------------------------------

class InteractiveReportWizard:
    """Guides the user through creating a block model report specification.

    All I/O goes through injectable `prompt_fn` / `confirm_fn` so tests can
    pipe input without touching stdin.
    """

    def __init__(
        self,
        client: BlockModelAPIClient,
        env,
        *,
        bm_id: str | None = None,
        prompt_fn: Callable[[str, str], str] = typer.prompt,
        confirm_fn: Callable[[str, bool], bool] = typer.confirm,
    ):
        self._client = client
        self._env = env
        self._bm_id = bm_id
        self._prompt_fn = prompt_fn
        self._confirm_fn = confirm_fn

        self._cols: list[ColumnMeta] = []
        self._units: list[UnitInfo] = []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        *,
        name: str | None = None,
        columns: list[str] | None = None,
        categories: list[str] | None = None,
        mass_unit: str | None = None,
        density_column: str | None = None,
        density_value: float | None = None,
        density_unit: str | None = None,
        cutoff_column: str | None = None,
        cutoffs: list[float] | None = None,
        autorun: bool | None = None,
        run_now: bool | None = None,
    ) -> dict:
        """Run the wizard and return a dict of kwargs for _do_create."""

        # Step 1 — select block model (skipped if bm_id already set)
        if self._bm_id is None:
            self._bm_id = await self._step_select_bm()

        # Pre-flight: fetch columns + units
        typer.echo("  Fetching column data…")
        self._cols = await _fetch_column_meta(self._client, self._bm_id)
        self._units = await _fetch_units(self._client, self._env)

        # Step 2 — report name
        if name is None:
            name = self._step_name()

        # Step 3 — value columns (skip if --column flags given)
        resolved_columns: list[ReportColumn]
        if columns:
            # Parse CLI-provided column specs using existing col_map
            from evo.cli.blockmodels.reports import _parse_column_spec
            col_map = {c.title: c.col_id for c in self._cols}
            resolved_columns = [_parse_column_spec(e, col_map) for e in columns]
        else:
            resolved_columns = self._step_columns()

        # Step 4 — category columns (skip if --category flags given)
        resolved_categories: list[ReportCategory] | None
        if categories:
            from evo.cli.blockmodels.reports import _parse_category_spec
            col_map = {c.title: c.col_id for c in self._cols}
            resolved_categories = [_parse_category_spec(e, col_map) for e in categories] or None
        else:
            resolved_categories = self._step_categories()

        # Step 5 — density
        if density_column is not None or density_value is not None:
            density_col_id: UUID | None = None
            eff_density_value: float | None = density_value
            eff_density_unit: str | None = density_unit
            if density_column is not None:
                col_map = {c.title: c.col_id for c in self._cols}
                density_col_id = UUID(col_map[density_column])
                eff_density_value = None
                eff_density_unit = None
        else:
            density_col_id, eff_density_value, eff_density_unit = self._step_density()

        # Step 6 — mass unit
        if mass_unit is None:
            mass_unit = self._step_mass_unit()

        # Step 7 — cutoffs
        cutoff_col_id: UUID | None = None
        eff_cutoffs: list[float] = []
        if cutoff_column is not None or cutoffs:
            col_map = {c.title: c.col_id for c in self._cols}
            if cutoff_column:
                cutoff_col_id = UUID(col_map[cutoff_column])
            eff_cutoffs = list(cutoffs or [])
        else:
            cutoff_col_id, eff_cutoffs = self._step_cutoffs()

        # Step 8 — autorun
        if autorun is None:
            autorun = self._step_autorun()

        # Step 9 — run now
        if run_now is None:
            run_now = self._step_run_now()

        # Step 10 — summary + confirm
        self._print_summary(
            bm_id=self._bm_id,
            name=name,
            columns=resolved_columns,
            categories=resolved_categories,
            density_col_id=density_col_id,
            density_value=eff_density_value,
            density_unit=eff_density_unit,
            mass_unit=mass_unit,
            cutoff_col_id=cutoff_col_id,
            cutoffs=eff_cutoffs,
            autorun=autorun,
            run_now=run_now,
        )
        if not _confirm("Create this report?", default=True, confirm_fn=self._confirm_fn):
            typer.echo("Aborted.")
            raise typer.Exit(0)

        return dict(
            bm_id=self._bm_id,
            name=name,
            description=None,
            column_specs=[],          # already resolved — pass objects directly
            category_specs=[],
            density_column=None,
            density_value=eff_density_value,
            density_unit=eff_density_unit,
            mass_unit=mass_unit,
            cutoff_column=None,
            cutoff_values=eff_cutoffs,
            autorun=autorun,
            run_now=run_now,
            # Non-string resolved values passed through extras
            _resolved_columns=resolved_columns,
            _resolved_categories=resolved_categories,
            _density_col_id=density_col_id,
            _cutoff_col_id=cutoff_col_id,
        )

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    async def _step_select_bm(self) -> str:
        typer.echo("  Fetching block models…")
        bms = await self._client.list_all_block_models()
        if not bms:
            output.emit_error("No block models found in this workspace.")

        output.emit_panel(
            "Step 1 · Select block model",
            ["Choose which block model to create a report for.", ""],
        )
        labels = [f"{bm.name}  ({str(bm.id)[:8]}…)" for bm in bms]
        _print_numbered(labels)
        typer.echo("")
        idx = _prompt_single(
            "Block model", len(bms), default=1, prompt_fn=self._prompt_fn
        )
        return str(bms[idx - 1].id)

    def _step_name(self) -> str:
        output.emit_panel("Step 2 · Report name", ["Give your report a descriptive name."])
        while True:
            name = self._prompt_fn("Report name", "").strip()
            if name:
                return name
            typer.echo("  Name cannot be empty.", err=True)

    def _step_columns(self) -> list[ReportColumn]:
        numeric_cols = [c for c in self._cols if c.data_type in _NUMERIC_TYPES]
        if not numeric_cols:
            output.emit_error("Block model has no numeric columns — cannot build a report.")

        output.emit_panel(
            "Step 3 · Value columns",
            [
                "Select which numeric columns to aggregate into the report.",
                "Each column produces one result column in the output table.",
            ],
        )
        labels = [
            f"{c.title:<30}  ({c.unit_id or 'no unit'})"
            for c in numeric_cols
        ]
        _print_numbered(labels)
        typer.echo("")

        indices = _prompt_indices(
            "Column numbers (comma-separated)",
            len(numeric_cols),
            min_count=1,
            prompt_fn=self._prompt_fn,
        )
        selected = [numeric_cols[i - 1] for i in indices]

        unit_map = {u.unit_id: u for u in self._units if u.unit_id}

        result: list[ReportColumn] = []
        for col in selected:
            # 3a label
            label_raw = self._prompt_fn(f'  Label for "{col.title}"', col.title).strip()
            label = label_raw or col.title

            # 3b aggregation
            output.emit_panel(
                f'Aggregation for "{label}"',
                [
                    "  1)  MASS_AVERAGE  — weighted mean per unit mass; use for grade (g/t, %, ppm)",
                    "  2)  SUM           — direct sum; use for absolute quantities (metal kg, oz)",
                ],
                width=70,
            )
            agg_idx = _prompt_single("Choice", 2, default=1, prompt_fn=self._prompt_fn)
            agg = ReportAggregation.MASS_AVERAGE if agg_idx == 1 else ReportAggregation.SUM

            # 3c output unit (optional)
            col_unit_info = unit_map.get(col.unit_id) if col.unit_id else None
            compatible = [
                u for u in self._units
                if col_unit_info and u.unit_type == col_unit_info.unit_type
                and u.unit_id != col.unit_id
            ]
            output_unit: str | None = col.unit_id
            if compatible:
                unit_labels = [f"{u.unit_id:<18}  {u.description}" for u in compatible]
                output.emit_panel(
                    f'Output unit for "{label}"',
                    ["Optionally convert the result to a different unit.", ""],
                    width=70,
                )
                typer.echo(f"    1)  {col.unit_id:<18}  (keep native — default)")
                for i, ul in enumerate(unit_labels, 2):
                    typer.echo(f"  {i:>3})  {ul}")
                typer.echo("")
                unit_idx = _prompt_single(
                    "Output unit", len(compatible) + 1, default=1, prompt_fn=self._prompt_fn
                )
                if unit_idx > 1:
                    output_unit = compatible[unit_idx - 2].unit_id

            result.append(
                ReportColumn(
                    col_id=UUID(col.col_id),
                    label=label,
                    aggregation=agg,
                    output_unit_id=output_unit,
                )
            )

        return result

    def _step_categories(self) -> list[ReportCategory] | None:
        output.emit_panel(
            "Step 4 · Category columns",
            [
                "A category column splits results by domain value (e.g. lithology, zone).",
                "Up to 5 categories. Press Enter to skip.",
            ],
        )
        labels = [f"{c.title:<30}  ({c.unit_id or 'string/category'})" for c in self._cols]
        _print_numbered(labels)
        typer.echo("")

        indices = _prompt_indices(
            "Category column numbers (0 or Enter to skip)",
            len(self._cols),
            min_count=0,
            max_count=5,
            prompt_fn=self._prompt_fn,
        )
        if not indices:
            return None

        result: list[ReportCategory] = []
        for i in indices:
            col = self._cols[i - 1]
            label_raw = self._prompt_fn(f'  Label for "{col.title}"', col.title).strip()
            label = label_raw or col.title
            result.append(ReportCategory(col_id=UUID(col.col_id), label=label, values=None))
        return result

    def _step_density(self) -> tuple[UUID | None, float | None, str | None]:
        output.emit_panel(
            "Step 5 · Density",
            [
                "Density converts block volume to mass.",
                "A column reads density per block (most accurate when density varies).",
                "A fixed value applies one number uniformly to all blocks.",
                "",
                "  1)  Density column  — block-by-block values (recommended)",
                "  2)  Fixed value     — single density for all blocks",
                "  3)  Both            — column with fixed fallback",
            ],
        )
        choice = _prompt_single("Choice", 3, default=1, prompt_fn=self._prompt_fn)

        density_col_id: UUID | None = None
        density_value: float | None = None
        density_unit: str | None = None

        mass_per_vol = [u for u in self._units if u.unit_type == UnitType.MASS_PER_VOLUME]
        numeric_cols = [c for c in self._cols if c.data_type in _NUMERIC_TYPES]

        if choice in (1, 3):
            col_labels = [f"{c.title:<30}  ({c.unit_id or 'no unit'})" for c in numeric_cols]
            _print_numbered(col_labels)
            typer.echo("")
            idx = _prompt_single("Density column", len(numeric_cols), prompt_fn=self._prompt_fn)
            density_col_id = UUID(numeric_cols[idx - 1].col_id)

        if choice in (2, 3):
            while True:
                raw = self._prompt_fn("Density value (e.g. 2.7)", "").strip()
                try:
                    density_value = float(raw)
                    break
                except ValueError:
                    typer.echo("  Enter a valid number.", err=True)

            unit_labels = [f"{u.unit_id:<18}  {u.description}" for u in mass_per_vol]
            _print_numbered(unit_labels)
            typer.echo("")
            default_idx = next(
                (i + 1 for i, u in enumerate(mass_per_vol) if u.unit_id == "t/m3"), 1
            )
            unit_idx = _prompt_single(
                "Density unit", len(mass_per_vol), default=default_idx, prompt_fn=self._prompt_fn
            )
            density_unit = mass_per_vol[unit_idx - 1].unit_id

        return density_col_id, density_value, density_unit

    def _step_mass_unit(self) -> str:
        mass_units = [u for u in self._units if u.unit_type == UnitType.MASS]
        if not mass_units:
            # Fallback if units API is unavailable
            raw = self._prompt_fn("Mass unit (e.g. t, kt, Mt)", "t").strip()
            return raw or "t"

        output.emit_panel(
            "Step 6 · Mass unit",
            [
                "Controls how tonnage is displayed in all result tables.",
                "For mine-scale resources, tonnes (t) is most common.",
            ],
        )
        unit_labels = [f"{u.unit_id:<18}  {u.description}" for u in mass_units]
        _print_numbered(unit_labels)
        typer.echo("")
        default_idx = next(
            (i + 1 for i, u in enumerate(mass_units) if u.unit_id == "t"), 1
        )
        idx = _prompt_single(
            "Mass unit", len(mass_units), default=default_idx, prompt_fn=self._prompt_fn
        )
        return mass_units[idx - 1].unit_id

    def _step_cutoffs(self) -> tuple[UUID | None, list[float]]:
        output.emit_panel(
            "Step 7 · Cutoff thresholds",
            [
                "Cutoffs define minimum grade thresholds.",
                "Each cutoff produces a result block showing only material at or above",
                "that grade. Typical set: 0.0, 0.5, 1.0, 2.0.",
            ],
        )
        if not _confirm("Set cutoff thresholds?", default=False, confirm_fn=self._confirm_fn):
            return None, []

        numeric_cols = [c for c in self._cols if c.data_type in _NUMERIC_TYPES]
        col_labels = [f"{c.title:<30}  ({c.unit_id or 'no unit'})" for c in numeric_cols]
        _print_numbered(col_labels)
        typer.echo("")
        idx = _prompt_single("Cutoff column", len(numeric_cols), prompt_fn=self._prompt_fn)
        cutoff_col_id = UUID(numeric_cols[idx - 1].col_id)

        values = _prompt_float_list(
            "Cutoff values (space or comma-separated, e.g. 0 0.5 1.0)",
            prompt_fn=self._prompt_fn,
        )
        return cutoff_col_id, values

    def _step_autorun(self) -> bool:
        output.emit_panel(
            "Step 8 · Autorun",
            [
                "When enabled, a new reporting job runs automatically whenever a new",
                "block model version is published — keeps results current without",
                "manual intervention.",
            ],
        )
        return _confirm("Enable autorun?", default=True, confirm_fn=self._confirm_fn)

    def _step_run_now(self) -> bool:
        output.emit_panel(
            "Step 9 · Run now",
            ["Run the report against the latest block model version immediately."],
        )
        return _confirm("Run report now?", default=True, confirm_fn=self._confirm_fn)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _print_summary(
        self,
        *,
        bm_id: str,
        name: str,
        columns: list[ReportColumn],
        categories: list[ReportCategory] | None,
        density_col_id: UUID | None,
        density_value: float | None,
        density_unit: str | None,
        mass_unit: str,
        cutoff_col_id: UUID | None,
        cutoffs: list[float],
        autorun: bool,
        run_now: bool,
    ) -> None:
        col_map_rev = {c.col_id: c.title for c in self._cols}

        col_lines = []
        for rc in columns:
            agg = rc.aggregation.value if hasattr(rc.aggregation, "value") else str(rc.aggregation)
            unit = f"  {rc.output_unit_id}" if rc.output_unit_id else ""
            col_lines.append(f"    {rc.label:<28}  {agg}{unit}")

        cat_lines: list[str] = []
        for rc in (categories or []):
            cat_lines.append(f"    {rc.label}")

        if density_col_id:
            density_str = f"column {col_map_rev.get(str(density_col_id), str(density_col_id))}"
        elif density_value is not None:
            density_str = f"{density_value} {density_unit or ''}"
        else:
            density_str = "(not set)"

        if cutoff_col_id and cutoffs:
            col_name = col_map_rev.get(str(cutoff_col_id), str(cutoff_col_id))
            cutoff_str = f"{col_name} ≥ {', '.join(str(v) for v in cutoffs)}"
        elif cutoffs:
            cutoff_str = ", ".join(str(v) for v in cutoffs)
        else:
            cutoff_str = "(none)"

        body = [
            f"  Block model  {bm_id[:8]}…",
            f"  Name         {name}",
            "  Columns",
            *col_lines,
        ]
        if cat_lines:
            body += ["  Categories", *cat_lines]
        else:
            body.append("  Categories   (none)")
        body += [
            f"  Density      {density_str}",
            f"  Mass unit    {mass_unit}",
            f"  Cutoffs      {cutoff_str}",
            f"  Autorun      {'yes' if autorun else 'no'}",
            f"  Run now      {'yes' if run_now else 'no'}",
        ]

        typer.echo("")
        output.emit_panel("Review your report", body, width=70)
        typer.echo("")
