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

"""Tests for Phase 2 (create/update), Phase 3 (run/results), and Phase 4 (compare)."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from typer.testing import CliRunner

from evo.blockmodels.endpoints.models import JobStatus
from evo.cli.__main__ import app

from . import _factories as f

runner = CliRunner()


class _ReportsBase(unittest.TestCase):
    def setUp(self) -> None:
        self._patcher_creds = mock.patch("evo.cli.blockmodels.reports.require_credentials", new_callable=mock.AsyncMock)
        self._patcher_env = mock.patch("evo.cli.blockmodels.reports.make_environment")
        self._patcher_conn = mock.patch("evo.cli.blockmodels.reports.make_connector")
        self._patcher_client = mock.patch("evo.blockmodels.BlockModelAPIClient")

        self.mock_creds = self._patcher_creds.start()
        self.mock_env = self._patcher_env.start()
        self.mock_conn_ctx = self._patcher_conn.start()
        self.MockClient = self._patcher_client.start()

        self.mock_env.return_value = f.ENVIRONMENT

        self.mock_connector = mock.AsyncMock()
        self.mock_connector.__aenter__ = mock.AsyncMock(return_value=self.mock_connector)
        self.mock_connector.__aexit__ = mock.AsyncMock(return_value=False)
        self.mock_conn_ctx.return_value = self.mock_connector

        self.mock_client = mock.MagicMock()
        self.mock_client._reports_api = mock.AsyncMock()
        self.MockClient.return_value = self.mock_client

    def tearDown(self) -> None:
        mock.patch.stopall()


# ---------------------------------------------------------------------------
# Phase 2 — create
# ---------------------------------------------------------------------------


class TestReportsCreate(_ReportsBase):
    def _setup_list_versions(self) -> None:
        self.mock_client.list_versions = mock.AsyncMock(return_value=[f.make_listing_version(version_id=1)])
        self.mock_client.get_version = mock.AsyncMock(return_value=f.make_version(version_id=1))
        self.mock_client._reports_api.create_report_specification = mock.AsyncMock(
            return_value=f.make_report_spec_with_job()
        )

    def test_create_plain(self) -> None:
        self._setup_list_versions()
        result = runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "create",
                str(f.BM_ID),
                "--name",
                "Gold Report",
                "--mass-unit",
                "t",
                "--column",
                "Cu:SUM:t",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Created", result.output)
        self.assertIn("Gold Report", result.output)

    def test_create_json(self) -> None:
        self._setup_list_versions()
        result = runner.invoke(
            app,
            [
                "--format",
                "json",
                "blockmodels",
                "reports",
                "create",
                str(f.BM_ID),
                "--name",
                "Gold Report",
                "--mass-unit",
                "t",
                "--column",
                "Cu:SUM:t",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["name"], "Gold Report")
        self.assertIn("report_specification_uuid", data)

    def test_create_requires_column(self) -> None:
        self._setup_list_versions()
        result = runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "create",
                str(f.BM_ID),
                "--name",
                "Gold Report",
                "--mass-unit",
                "t",
            ],
        )
        self.assertNotEqual(result.exit_code, 0)

    def test_create_unknown_column_title_exits(self) -> None:
        self._setup_list_versions()
        result = runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "create",
                str(f.BM_ID),
                "--name",
                "Gold Report",
                "--mass-unit",
                "t",
                "--column",
                "NONEXISTENT:SUM",
            ],
        )
        self.assertNotEqual(result.exit_code, 0)

    def test_create_calls_api(self) -> None:
        self._setup_list_versions()
        runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "create",
                str(f.BM_ID),
                "--name",
                "Gold Report",
                "--mass-unit",
                "t",
                "--column",
                "Cu:SUM:t",
            ],
        )
        self.mock_client._reports_api.create_report_specification.assert_called_once()
        call_kwargs = self.mock_client._reports_api.create_report_specification.call_args.kwargs
        self.assertEqual(call_kwargs["workspace_id"], str(f.WORKSPACE_ID))
        self.assertEqual(call_kwargs["org_id"], str(f.ORG_ID))
        self.assertEqual(call_kwargs["bm_id"], str(f.BM_ID))
        self.assertTrue(call_kwargs["run_now"])


# ---------------------------------------------------------------------------
# Phase 2 — update
# ---------------------------------------------------------------------------


class TestReportsUpdate(_ReportsBase):
    def _setup(self) -> None:
        self.mock_client._reports_api.get_report_specification = mock.AsyncMock(return_value=f.make_report_spec())
        self.mock_client.list_versions = mock.AsyncMock(return_value=[f.make_listing_version(version_id=1)])
        self.mock_client.get_version = mock.AsyncMock(return_value=f.make_version(version_id=1))
        self.mock_client._reports_api.update_report_specification = mock.AsyncMock(
            return_value=f.make_report_spec_with_job()
        )

    def test_update_plain(self) -> None:
        self._setup()
        result = runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "update",
                str(f.BM_ID),
                str(f.SPEC_ID),
                "--name",
                "Gold Report v2",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Updated", result.output)

    def test_update_preserves_existing_columns_when_none_specified(self) -> None:
        self._setup()
        runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "update",
                str(f.BM_ID),
                str(f.SPEC_ID),
                "--name",
                "Gold Report v2",
            ],
        )
        call_kwargs = self.mock_client._reports_api.update_report_specification.call_args.kwargs
        body = call_kwargs["update_report_specification"]
        # Should use existing columns from get_report_specification response
        self.assertEqual(len(body.columns), 1)
        self.assertEqual(body.columns[0].label, "Au Grade")

    def test_update_with_new_columns_resolves_titles(self) -> None:
        self._setup()
        runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "update",
                str(f.BM_ID),
                str(f.SPEC_ID),
                "--column",
                "Cu:SUM",
            ],
        )
        # list_versions was called to build col_map
        self.mock_client.list_versions.assert_called_once()

    def test_update_json(self) -> None:
        self._setup()
        result = runner.invoke(
            app,
            [
                "--format",
                "json",
                "blockmodels",
                "reports",
                "update",
                str(f.BM_ID),
                str(f.SPEC_ID),
                "--name",
                "New Name",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertIn("report_specification_uuid", data)


# ---------------------------------------------------------------------------
# Phase 3 — run
# ---------------------------------------------------------------------------


class TestReportsRun(_ReportsBase):
    def _setup(self) -> None:
        self.mock_client._reports_api.run_reporting_job = mock.AsyncMock(return_value=f.make_reporting_job_result())
        self.mock_client._reports_api.get_report_result = mock.AsyncMock(return_value=f.make_report_result())
        run_result = f.make_report_run_result()
        completed_job = f.make_job_response(status=JobStatus.COMPLETE, payload=run_result)
        self.mock_client._poll_job_url = mock.AsyncMock(return_value=completed_job)

    def test_run_plain(self) -> None:
        self._setup()
        result = runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "run",
                str(f.BM_ID),
                str(f.SPEC_ID),
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Gold Report", result.output)
        self.assertIn("Mass", result.output)
        self.assertIn("Au Grade", result.output)
        self.assertIn("North", result.output)

    def test_run_json(self) -> None:
        self._setup()
        result = runner.invoke(
            app,
            [
                "--format",
                "json",
                "blockmodels",
                "reports",
                "run",
                str(f.BM_ID),
                str(f.SPEC_ID),
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["report_specification_name"], "Gold Report")
        self.assertEqual(len(data["result_sets"]), 2)

    def test_run_shows_cutoff_in_table(self) -> None:
        self._setup()
        result = runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "run",
                str(f.BM_ID),
                str(f.SPEC_ID),
            ],
        )
        self.assertIn("0", result.output)  # cutoff value 0.0

    def test_run_polls_job(self) -> None:
        self._setup()
        runner.invoke(app, ["blockmodels", "reports", "run", str(f.BM_ID), str(f.SPEC_ID)])
        self.mock_client._poll_job_url.assert_called_once()


# ---------------------------------------------------------------------------
# Phase 3 — results list / get
# ---------------------------------------------------------------------------


class TestReportsResults(_ReportsBase):
    def test_results_list_plain(self) -> None:
        self.mock_client._reports_api.get_report_results_list = mock.AsyncMock(
            return_value=f.make_result_summary_page(f.make_result_summary())
        )
        result = runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "results",
                "list",
                str(f.BM_ID),
                str(f.SPEC_ID),
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(str(f.RESULT_ID), result.output)
        self.assertIn("v5", result.output)

    def test_results_list_empty(self) -> None:
        self.mock_client._reports_api.get_report_results_list = mock.AsyncMock(
            return_value=f.make_result_summary_page()
        )
        result = runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "results",
                "list",
                str(f.BM_ID),
                str(f.SPEC_ID),
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("No results", result.output)

    def test_results_get_plain(self) -> None:
        self.mock_client._reports_api.get_report_result = mock.AsyncMock(return_value=f.make_report_result())
        result = runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "results",
                "get",
                str(f.BM_ID),
                str(f.SPEC_ID),
                str(f.RESULT_ID),
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Gold Report", result.output)
        self.assertIn("Au Grade", result.output)
        self.assertIn("1,250,000", result.output)

    def test_results_get_json(self) -> None:
        self.mock_client._reports_api.get_report_result = mock.AsyncMock(return_value=f.make_report_result())
        result = runner.invoke(
            app,
            [
                "--format",
                "json",
                "blockmodels",
                "reports",
                "results",
                "get",
                str(f.BM_ID),
                str(f.SPEC_ID),
                str(f.RESULT_ID),
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["report_specification_name"], "Gold Report")
        self.assertEqual(len(data["result_sets"]), 2)
        self.assertEqual(data["result_sets"][0]["rows"][0]["categories"], ["North"])


# ---------------------------------------------------------------------------
# Phase 4 — compare
# ---------------------------------------------------------------------------

VERSION_UUID2 = f.UUID("cccccccc-0000-0000-0000-000000000002")


class TestReportsCompare(_ReportsBase):
    def _setup_with_existing_results(self) -> None:
        from evo.blockmodels.endpoints.models import ReportComparisonRequestResult

        self.mock_client._reports_api.request_report_comparison = mock.AsyncMock(
            return_value=ReportComparisonRequestResult(
                from_result_uuid=f.RESULT_ID,
                to_result_uuid=f.RESULT_ID2,
                job_url=None,
            )
        )
        self.mock_client._reports_api.get_report_result_comparison = mock.AsyncMock(
            return_value=f.make_report_comparison()
        )

    def test_compare_plain(self) -> None:
        self._setup_with_existing_results()
        result = runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "compare",
                str(f.BM_ID),
                str(f.SPEC_ID),
                "--from",
                str(f.VERSION_UUID),
                "--to",
                str(VERSION_UUID2),
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Gold Report", result.output)
        self.assertIn("→", result.output)
        self.assertIn("North", result.output)
        self.assertIn("+25.0%", result.output)

    def test_compare_json(self) -> None:
        self._setup_with_existing_results()
        result = runner.invoke(
            app,
            [
                "--format",
                "json",
                "blockmodels",
                "reports",
                "compare",
                str(f.BM_ID),
                str(f.SPEC_ID),
                "--from",
                str(f.VERSION_UUID),
                "--to",
                str(VERSION_UUID2),
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["report_specification_name"], "Gold Report")
        self.assertIn("result_sets", data)

    def test_compare_polls_when_job_required(self) -> None:
        from pydantic import AnyUrl

        from evo.blockmodels.endpoints.models import ReportComparisonJobResult, ReportComparisonRequestResult

        job_id = f.JOB_ID
        self.mock_client._reports_api.request_report_comparison = mock.AsyncMock(
            return_value=ReportComparisonRequestResult(
                from_result_uuid=None,
                to_result_uuid=None,
                job_url=AnyUrl(f"https://acme.api.seequent.com/jobs/{job_id}"),
            )
        )
        comparison_job_result = ReportComparisonJobResult(
            report_specification_uuid=f.SPEC_ID,
            from_result_uuid=f.RESULT_ID,
            to_result_uuid=f.RESULT_ID2,
            from_version_uuid=f.VERSION_UUID,
            to_version_uuid=VERSION_UUID2,
        )
        from evo.blockmodels.endpoints.models import JobResponse

        completed = JobResponse(job_status=JobStatus.COMPLETE, payload=comparison_job_result)
        self.mock_client._poll_job_url = mock.AsyncMock(return_value=completed)
        self.mock_client._reports_api.get_report_result_comparison = mock.AsyncMock(
            return_value=f.make_report_comparison()
        )

        result = runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "compare",
                str(f.BM_ID),
                str(f.SPEC_ID),
                "--from",
                str(f.VERSION_UUID),
                "--to",
                str(VERSION_UUID2),
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client._poll_job_url.assert_called_once()

    def test_compare_calls_api_with_correct_params(self) -> None:
        self._setup_with_existing_results()
        runner.invoke(
            app,
            [
                "blockmodels",
                "reports",
                "compare",
                str(f.BM_ID),
                str(f.SPEC_ID),
                "--from",
                str(f.VERSION_UUID),
                "--to",
                str(VERSION_UUID2),
            ],
        )
        self.mock_client._reports_api.request_report_comparison.assert_called_once()
        self.mock_client._reports_api.get_report_result_comparison.assert_called_once_with(
            rs_id=str(f.SPEC_ID),
            workspace_id=str(f.WORKSPACE_ID),
            org_id=str(f.ORG_ID),
            bm_id=str(f.BM_ID),
            var_from=str(f.RESULT_ID),
            to=str(f.RESULT_ID2),
            decimal_places=None,
        )


if __name__ == "__main__":
    unittest.main()
