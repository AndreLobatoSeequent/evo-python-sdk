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

import json
import unittest
from unittest import mock

from typer.testing import CliRunner

from evo.cli.__main__ import app

from . import _factories as f

runner = CliRunner()


class _ReportsBase(unittest.TestCase):
    """Base class that patches connector helpers and BlockModelAPIClient."""

    def setUp(self) -> None:
        self._patcher_creds = mock.patch(
            "evo.cli.blockmodels.reports.require_credentials", new_callable=mock.AsyncMock
        )
        self._patcher_env = mock.patch("evo.cli.blockmodels.reports.make_environment")
        self._patcher_conn = mock.patch("evo.cli.blockmodels.reports.make_connector")
        self._patcher_client = mock.patch("evo.cli.blockmodels.reports.BlockModelAPIClient")

        self.mock_creds = self._patcher_creds.start()
        self.mock_env = self._patcher_env.start()
        self.mock_conn_ctx = self._patcher_conn.start()
        self.MockClient = self._patcher_client.start()

        # Make the env mock return something with workspace_id / org_id attributes
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
# reports list
# ---------------------------------------------------------------------------

class TestReportsList(_ReportsBase):
    def test_list_plain(self) -> None:
        spec = f.make_report_spec()
        self.mock_client._reports_api.list_block_model_report_specifications = mock.AsyncMock(
            return_value=f.make_report_spec_page(spec)
        )

        result = runner.invoke(app, ["blockmodels", "reports", "list", str(f.BM_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Gold Report", result.output)
        self.assertIn(str(f.SPEC_ID), result.output)
        self.assertIn("autorun", result.output)

    def test_list_json(self) -> None:
        spec = f.make_report_spec()
        self.mock_client._reports_api.list_block_model_report_specifications = mock.AsyncMock(
            return_value=f.make_report_spec_page(spec)
        )

        result = runner.invoke(app, ["--format", "json", "blockmodels", "reports", "list", str(f.BM_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        items = json.loads(result.output)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Gold Report")
        self.assertEqual(items[0]["report_specification_uuid"], str(f.SPEC_ID))
        self.assertTrue(items[0]["autorun"])
        self.assertEqual(items[0]["mass_unit_id"], "t")

    def test_list_empty(self) -> None:
        self.mock_client._reports_api.list_block_model_report_specifications = mock.AsyncMock(
            return_value=f.make_report_spec_page()
        )

        result = runner.invoke(app, ["blockmodels", "reports", "list", str(f.BM_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("No report specifications found", result.output)

    def test_list_calls_api_with_correct_ids(self) -> None:
        self.mock_client._reports_api.list_block_model_report_specifications = mock.AsyncMock(
            return_value=f.make_report_spec_page()
        )

        runner.invoke(app, ["blockmodels", "reports", "list", str(f.BM_ID)])

        self.mock_client._reports_api.list_block_model_report_specifications.assert_called_once_with(
            workspace_id=str(f.WORKSPACE_ID),
            org_id=str(f.ORG_ID),
            bm_id=str(f.BM_ID),
        )


# ---------------------------------------------------------------------------
# reports get
# ---------------------------------------------------------------------------

class TestReportsGet(_ReportsBase):
    def test_get_plain(self) -> None:
        spec = f.make_report_spec()
        self.mock_client._reports_api.get_report_specification = mock.AsyncMock(return_value=spec)

        result = runner.invoke(app, ["blockmodels", "reports", "get", str(f.BM_ID), str(f.SPEC_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Gold Report", result.output)
        self.assertIn(str(f.SPEC_ID), result.output)
        self.assertIn("Au Grade", result.output)
        self.assertIn("MASS_AVERAGE", result.output)
        self.assertIn("Domain", result.output)
        self.assertIn("2.7", result.output)
        self.assertIn("v3", result.output)  # last_result_version_id

    def test_get_plain_never_run(self) -> None:
        spec = f.make_report_spec(with_last_run=False)
        self.mock_client._reports_api.get_report_specification = mock.AsyncMock(return_value=spec)

        result = runner.invoke(app, ["blockmodels", "reports", "get", str(f.BM_ID), str(f.SPEC_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("(never)", result.output)

    def test_get_json(self) -> None:
        spec = f.make_report_spec()
        self.mock_client._reports_api.get_report_specification = mock.AsyncMock(return_value=spec)

        result = runner.invoke(
            app, ["--format", "json", "blockmodels", "reports", "get", str(f.BM_ID), str(f.SPEC_ID)]
        )

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["name"], "Gold Report")
        self.assertEqual(data["columns"][0]["label"], "Au Grade")
        self.assertEqual(data["columns"][0]["aggregation"], "MASS_AVERAGE")
        self.assertEqual(data["categories"][0]["label"], "Domain")
        self.assertEqual(data["cutoff_values"], [0.5, 1.0])
        self.assertEqual(data["density_value"], 2.7)

    def test_get_calls_api_with_correct_ids(self) -> None:
        spec = f.make_report_spec()
        self.mock_client._reports_api.get_report_specification = mock.AsyncMock(return_value=spec)

        runner.invoke(app, ["blockmodels", "reports", "get", str(f.BM_ID), str(f.SPEC_ID)])

        self.mock_client._reports_api.get_report_specification.assert_called_once_with(
            rs_id=str(f.SPEC_ID),
            workspace_id=str(f.WORKSPACE_ID),
            org_id=str(f.ORG_ID),
            bm_id=str(f.BM_ID),
        )


if __name__ == "__main__":
    unittest.main()
