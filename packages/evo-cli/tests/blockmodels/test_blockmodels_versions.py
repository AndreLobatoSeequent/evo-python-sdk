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


class _VersionsBase(unittest.TestCase):
    def setUp(self) -> None:
        self._patcher_creds = mock.patch(
            "evo.cli.blockmodels.versions.require_credentials", new_callable=mock.AsyncMock
        )
        self._patcher_env = mock.patch("evo.cli.blockmodels.versions.make_environment")
        self._patcher_conn = mock.patch("evo.cli.blockmodels.versions.make_connector")
        self._patcher_client = mock.patch("evo.cli.blockmodels.versions.BlockModelAPIClient")

        self.mock_creds = self._patcher_creds.start()
        self.mock_env = self._patcher_env.start()
        self.mock_conn_ctx = self._patcher_conn.start()
        self.MockClient = self._patcher_client.start()

        self.mock_connector = mock.AsyncMock()
        self.mock_connector.__aenter__ = mock.AsyncMock(return_value=self.mock_connector)
        self.mock_connector.__aexit__ = mock.AsyncMock(return_value=False)
        self.mock_conn_ctx.return_value = self.mock_connector

        self.mock_client = mock.AsyncMock()
        self.MockClient.return_value = self.mock_client

    def tearDown(self) -> None:
        mock.patch.stopall()


class TestVersionsList(_VersionsBase):
    def test_list_plain(self) -> None:
        self.mock_client.list_all_versions = mock.AsyncMock(return_value=[f.make_listing_version()])

        result = runner.invoke(app, ["blockmodels", "versions", "list", str(f.BM_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("v1", result.output)
        self.mock_client.list_all_versions.assert_called_once_with(f.BM_ID)

    def test_list_json(self) -> None:
        self.mock_client.list_all_versions = mock.AsyncMock(return_value=[f.make_listing_version()])

        result = runner.invoke(app, ["--format", "json", "blockmodels", "versions", "list", str(f.BM_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        items = json.loads(result.output)
        self.assertEqual(items[0]["version_id"], 1)
        self.assertEqual(items[0]["columns"][0]["title"], "Cu")
        self.assertNotIn("tags", items[0]["columns"][0])

    def test_list_empty(self) -> None:
        self.mock_client.list_all_versions = mock.AsyncMock(return_value=[])
        result = runner.invoke(app, ["blockmodels", "versions", "list", str(f.BM_ID)])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No versions found", result.output)


class TestVersionsGet(_VersionsBase):
    def test_get_plain(self) -> None:
        self.mock_client.get_version = mock.AsyncMock(return_value=f.make_version())

        result = runner.invoke(app, ["blockmodels", "versions", "get", str(f.BM_ID), str(f.VERSION_UUID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.get_version.assert_called_once_with(f.BM_ID, f.VERSION_UUID)

    def test_get_json_includes_tags(self) -> None:
        self.mock_client.get_version = mock.AsyncMock(return_value=f.make_version())

        result = runner.invoke(
            app, ["--format", "json", "blockmodels", "versions", "get", str(f.BM_ID), str(f.VERSION_UUID)]
        )

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertIn("tags", data["columns"][0])
