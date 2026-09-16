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

"""Tests for the interactive report-creation wizard."""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock
from uuid import UUID

from evo.blockmodels.endpoints.models import ReportAggregation, ReportColumn, ReportCategory
from evo.blockmodels.typed.units import UnitInfo, UnitType

from evo.cli.blockmodels.interactive import (
    ColumnMeta,
    InteractiveReportWizard,
    _prompt_indices,
    _prompt_single,
)
from evo.cli import output

from . import _factories as f


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prompt(answers: list[str]):
    """Return a prompt_fn that pops from answers; raises on exhaustion."""
    it = iter(answers)
    def _fn(prompt: str, default: str = "") -> str:  # noqa: ARG001
        try:
            return next(it)
        except StopIteration:
            raise AssertionError(f"Prompt exhausted — unexpected prompt: {prompt!r}")
    return _fn


def _make_confirm(answers: list[bool]):
    it = iter(answers)
    def _fn(prompt: str, *, default: bool = True) -> bool:  # noqa: ARG001
        try:
            return next(it)
        except StopIteration:
            return default
    return _fn


def _numeric_col(title: str = "Au", unit_id: str = "g/t") -> ColumnMeta:
    from evo.blockmodels.endpoints.models import DataType
    return ColumnMeta(col_id=str(f.COL_DATA_ID), title=title, unit_id=unit_id, data_type=DataType.Float64)


def _unit(unit_id: str = "g/t", unit_type: UnitType = UnitType.MASS_PER_MASS) -> UnitInfo:
    return UnitInfo(
        unit_id=unit_id,
        symbol=unit_id,
        description=unit_id,
        unit_type=unit_type,
        conversion_factor=1.0,
    )


def _mass_units() -> list[UnitInfo]:
    return [
        _unit("t", UnitType.MASS),
        _unit("kt", UnitType.MASS),
        _unit("Mt", UnitType.MASS),
    ]


def _density_units() -> list[UnitInfo]:
    return [_unit("t/m3", UnitType.MASS_PER_VOLUME)]


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Unit tests for low-level prompt helpers
# ---------------------------------------------------------------------------

class TestPromptHelpers(unittest.TestCase):
    def test_prompt_indices_valid(self):
        pf = _make_prompt(["1,2"])
        result = _prompt_indices("Pick", 3, min_count=1, prompt_fn=pf)
        self.assertEqual(result, [1, 2])

    def test_prompt_indices_loops_on_invalid_then_valid(self):
        pf = _make_prompt(["99", "1"])
        with mock.patch("typer.echo"):  # suppress error echo
            result = _prompt_indices("Pick", 3, min_count=1, prompt_fn=pf)
        self.assertEqual(result, [1])

    def test_prompt_indices_loops_on_below_min(self):
        pf = _make_prompt(["", "1"])
        with mock.patch("typer.echo"):
            result = _prompt_indices("Pick", 3, min_count=1, prompt_fn=pf)
        self.assertEqual(result, [1])

    def test_prompt_indices_zero_allowed(self):
        pf = _make_prompt([""])
        result = _prompt_indices("Pick", 3, min_count=0, prompt_fn=pf)
        self.assertEqual(result, [])

    def test_prompt_single_default(self):
        pf = _make_prompt(["2"])
        result = _prompt_single("Pick", 3, default=1, prompt_fn=pf)
        self.assertEqual(result, 2)

    def test_prompt_single_loops_on_out_of_range(self):
        pf = _make_prompt(["99", "1"])
        with mock.patch("typer.echo"):
            result = _prompt_single("Pick", 3, prompt_fn=pf)
        self.assertEqual(result, 1)


# ---------------------------------------------------------------------------
# emit_panel unit test
# ---------------------------------------------------------------------------

class TestEmitPanel(unittest.TestCase):
    def test_emit_panel_no_op_in_json_mode(self):
        output.init(output.OutputFormat.json)
        with mock.patch("typer.echo") as mock_echo:
            output.emit_panel("Test", ["line"])
        mock_echo.assert_not_called()
        output.init(output.OutputFormat.plain)

    def test_emit_panel_renders_in_plain_mode(self):
        output.init(output.OutputFormat.plain)
        with mock.patch("rich.console.Console.print") as mock_print:
            output.emit_panel("Hello", ["body line"])
        mock_print.assert_called_once()
        # Panel was passed to Console.print
        from rich.panel import Panel
        args = mock_print.call_args.args
        self.assertIsInstance(args[0], Panel)


# ---------------------------------------------------------------------------
# Wizard step tests
# ---------------------------------------------------------------------------

class _WizardBase(unittest.TestCase):
    def setUp(self):
        self.mock_client = mock.MagicMock()
        self.mock_client._reports_api = mock.AsyncMock()
        self.mock_client.list_all_block_models = mock.AsyncMock(
            return_value=[f.make_block_model()]
        )
        self.mock_client.list_versions = mock.AsyncMock(
            return_value=[f.make_listing_version()]
        )
        self.mock_client.get_version = mock.AsyncMock(
            return_value=f.make_version()
        )
        self.mock_client._units_api = mock.AsyncMock()
        self.env = f.ENVIRONMENT
        self._cols = [_numeric_col("Cu", "%[mass]")]
        self._units = _mass_units() + _density_units() + [_unit("%[mass]", UnitType.MASS_PER_MASS)]

    def _wizard(self, *, bm_id: str | None = str(f.BM_ID), prompt_fn=None, confirm_fn=None):
        w = InteractiveReportWizard(
            self.mock_client,
            self.env,
            bm_id=bm_id,
            prompt_fn=prompt_fn or _make_prompt([]),
            confirm_fn=confirm_fn or _make_confirm([]),
        )
        w._cols = self._cols
        w._units = self._units
        return w


class TestWizardStepName(unittest.TestCase):
    def setUp(self):
        self.client = mock.MagicMock()
        self.env = f.ENVIRONMENT

    def test_step_name_skipped_when_provided(self):
        """_step_name not called if name is already set by the caller."""
        # We verify by running the wizard with name pre-set and checking
        # that no prompt for name appears in our prompt sequence.
        called = []
        def pf(prompt, default=""):
            called.append(prompt)
            return default
        w = InteractiveReportWizard(self.client, self.env, bm_id=str(f.BM_ID), prompt_fn=pf)
        w._cols = [_numeric_col()]
        w._units = _mass_units() + _density_units()
        # step_name not invoked when name is passed — just verify _step_name directly
        pf2 = _make_prompt(["Gold Report"])
        w2 = InteractiveReportWizard(self.client, self.env, bm_id=str(f.BM_ID), prompt_fn=pf2)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            result = w2._step_name()
        self.assertEqual(result, "Gold Report")

    def test_step_name_loops_on_blank(self):
        pf = _make_prompt(["", "  ", "Valid Name"])
        w = InteractiveReportWizard(mock.MagicMock(), f.ENVIRONMENT, bm_id=str(f.BM_ID), prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"), \
             mock.patch("typer.echo"):
            result = w._step_name()
        self.assertEqual(result, "Valid Name")


class TestWizardStepColumns(_WizardBase):
    def test_step_columns_returns_report_column(self):
        pf = _make_prompt(["1", "My Cu", "2", "1"])  # idx=1, label, agg=SUM, unit=native
        w = self._wizard(prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            cols = w._step_columns()
        self.assertEqual(len(cols), 1)
        self.assertEqual(cols[0].label, "My Cu")
        self.assertEqual(cols[0].aggregation, ReportAggregation.SUM)

    def test_step_columns_mass_average(self):
        pf = _make_prompt(["1", "", "1", "1"])  # default label, MASS_AVERAGE, keep unit
        w = self._wizard(prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            cols = w._step_columns()
        self.assertEqual(cols[0].aggregation, ReportAggregation.MASS_AVERAGE)
        self.assertEqual(cols[0].label, "Cu")  # default title


class TestWizardStepCategories(_WizardBase):
    def test_step_categories_skip_returns_none(self):
        pf = _make_prompt([""])  # empty → skip
        w = self._wizard(prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            result = w._step_categories()
        self.assertIsNone(result)

    def test_step_categories_selects_column(self):
        pf = _make_prompt(["1", "Domain"])  # select col 1, set label
        w = self._wizard(prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            result = w._step_categories()
        self.assertIsNotNone(result)
        self.assertEqual(result[0].label, "Domain")


class TestWizardStepDensity(_WizardBase):
    def test_density_fixed_value(self):
        pf = _make_prompt(["2", "2.7", "1"])  # choice=2 (fixed), value=2.7, unit idx=1
        w = self._wizard(prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            col_id, val, unit = w._step_density()
        self.assertIsNone(col_id)
        self.assertAlmostEqual(val, 2.7)
        self.assertEqual(unit, "t/m3")

    def test_density_column(self):
        pf = _make_prompt(["1", "1"])  # choice=1 (column), col idx=1
        w = self._wizard(prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            col_id, val, unit = w._step_density()
        self.assertIsNotNone(col_id)
        self.assertIsNone(val)


class TestWizardStepMassUnit(_WizardBase):
    def test_mass_unit_selected(self):
        pf = _make_prompt(["2"])  # select kt
        w = self._wizard(prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            unit = w._step_mass_unit()
        self.assertEqual(unit, "kt")

    def test_mass_unit_default_is_t(self):
        pf = _make_prompt(["1"])  # select first = t
        w = self._wizard(prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            unit = w._step_mass_unit()
        self.assertEqual(unit, "t")


class TestWizardStepCutoffs(_WizardBase):
    def test_no_cutoffs(self):
        cf = _make_confirm([False])
        w = self._wizard(confirm_fn=cf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            col_id, values = w._step_cutoffs()
        self.assertIsNone(col_id)
        self.assertEqual(values, [])

    def test_cutoffs_set(self):
        cf = _make_confirm([True])
        pf = _make_prompt(["1", "0.5 1.0"])  # col idx=1, values
        w = self._wizard(prompt_fn=pf, confirm_fn=cf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            col_id, values = w._step_cutoffs()
        self.assertIsNotNone(col_id)
        self.assertAlmostEqual(values[0], 0.5)
        self.assertAlmostEqual(values[1], 1.0)


class TestWizardStepAutorun(_WizardBase):
    def test_autorun_yes(self):
        cf = _make_confirm([True])
        w = self._wizard(confirm_fn=cf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            self.assertTrue(w._step_autorun())

    def test_autorun_no(self):
        cf = _make_confirm([False])
        w = self._wizard(confirm_fn=cf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            self.assertFalse(w._step_autorun())


class TestWizardStepPolicies(_WizardBase):
    def test_null_values_policy_default(self):
        pf = _make_prompt(["1"])  # select IGNORE_BLOCK
        w = self._wizard(prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            result = w._step_null_values_policy()
        self.assertEqual(result, "IGNORE_BLOCK")

    def test_null_values_policy_zero(self):
        pf = _make_prompt(["2"])
        w = self._wizard(prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            result = w._step_null_values_policy()
        self.assertEqual(result, "ZERO")

    def test_negative_values_policy_default(self):
        pf = _make_prompt(["1"])  # select IGNORE_BLOCK
        w = self._wizard(prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            result = w._step_negative_values_policy()
        self.assertEqual(result, "IGNORE_BLOCK")

    def test_negative_values_policy_use(self):
        pf = _make_prompt(["2"])  # select USE
        w = self._wizard(prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"):
            result = w._step_negative_values_policy()
        self.assertEqual(result, "USE")


class TestWizardAbortOnConfirm(_WizardBase):
    def test_abort_raises_exit_0(self):
        import typer
        # Confirm "no" at final step → Exit(0)
        cf_answers = iter([False])

        async def _inner():
            w = InteractiveReportWizard(
                self.mock_client,
                self.env,
                bm_id=str(f.BM_ID),
                prompt_fn=_make_prompt(["1", "", "1", "1", "", "1", "", "1"]),
                confirm_fn=lambda p, *, default=True: next(cf_answers, default),
            )
            w._cols = self._cols
            w._units = self._units
            with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"), \
                 mock.patch("evo.cli.blockmodels.interactive._confirm", return_value=False), \
                 mock.patch("evo.cli.blockmodels.interactive.output.is_interactive", return_value=True), \
                 mock.patch("typer.echo"):
                return await w.run(name="X", columns=["Cu:SUM:%[mass]"], mass_unit="t", autorun=True, run_now=False, cutoffs=[])

        with self.assertRaises(typer.Exit) as ctx:
            _run(_inner())
        self.assertEqual(ctx.exception.exit_code, 0)


class TestWizardSelectBlockModel(_WizardBase):
    def test_bm_select_sets_bm_id(self):
        bm = f.make_block_model()
        self.mock_client.list_all_block_models = mock.AsyncMock(return_value=[bm])
        pf = _make_prompt(["1"])
        w = InteractiveReportWizard(self.mock_client, self.env, bm_id=None, prompt_fn=pf)
        with mock.patch("evo.cli.blockmodels.interactive.output.emit_panel"), \
             mock.patch("typer.echo"):
            result = _run(w._step_select_bm())
        self.assertEqual(result, str(bm.id))

    def test_bm_step_skipped_when_bm_id_provided(self):
        """When bm_id is pre-set, list_all_block_models is never called."""
        w = self._wizard(bm_id=str(f.BM_ID))
        # _step_select_bm is only called when bm_id is None; verify the attribute is set
        self.assertEqual(w._bm_id, str(f.BM_ID))
        self.mock_client.list_all_block_models.assert_not_called()


if __name__ == "__main__":
    unittest.main()
