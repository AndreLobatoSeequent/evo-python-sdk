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

import unittest
from unittest import mock

from typer.testing import CliRunner

from evo.cli.__main__ import app

from . import _factories as f

runner = CliRunner()


class _ColumnsBase(unittest.TestCase):
    def setUp(self) -> None:
        self._patcher_creds = mock.patch("evo.cli.blockmodels.columns.require_credentials", new_callable=mock.AsyncMock)
        self._patcher_env = mock.patch("evo.cli.blockmodels.columns.make_environment")
        self._patcher_conn = mock.patch("evo.cli.blockmodels.columns.make_connector")
        self._patcher_client = mock.patch("evo.blockmodels.BlockModelAPIClient")
        self._patcher_cache = mock.patch("evo.cli.blockmodels.columns.make_cache")

        self.mock_creds = self._patcher_creds.start()
        self.mock_env = self._patcher_env.start()
        self.mock_conn_ctx = self._patcher_conn.start()
        self.MockClient = self._patcher_client.start()
        self.mock_cache = self._patcher_cache.start()

        self.mock_connector = mock.AsyncMock()
        self.mock_connector.__aenter__ = mock.AsyncMock(return_value=self.mock_connector)
        self.mock_connector.__aexit__ = mock.AsyncMock(return_value=False)
        self.mock_conn_ctx.return_value = self.mock_connector

        self.mock_client = mock.AsyncMock()
        self.MockClient.return_value = self.mock_client

    def tearDown(self) -> None:
        mock.patch.stopall()


class TestColumnsRename(_ColumnsBase):
    def test_rename(self) -> None:
        self.mock_client.rename_block_model_columns = mock.AsyncMock(return_value=f.make_version())

        result = runner.invoke(app, ["blockmodels", "columns", "rename", str(f.BM_ID), "--rename", "Cu=Copper"])

        self.assertEqual(result.exit_code, 0, result.output)
        args, kwargs = self.mock_client.rename_block_model_columns.call_args
        self.assertEqual(args[0], f.BM_ID)
        self.assertEqual(args[1], {"Cu": "Copper"})

    def test_rename_requires_at_least_one(self) -> None:
        result = runner.invoke(app, ["blockmodels", "columns", "rename", str(f.BM_ID)])
        self.assertNotEqual(result.exit_code, 0)

    def test_rename_malformed_entry(self) -> None:
        result = runner.invoke(app, ["blockmodels", "columns", "rename", str(f.BM_ID), "--rename", "no-equals-sign"])
        self.assertNotEqual(result.exit_code, 0)


class TestColumnsDelete(_ColumnsBase):
    def test_delete(self) -> None:
        self.mock_client.delete_block_model_columns = mock.AsyncMock(return_value=f.make_version())

        result = runner.invoke(
            app, ["blockmodels", "columns", "delete", str(f.BM_ID), "--column", "Cu", "--column", "Au"]
        )

        self.assertEqual(result.exit_code, 0, result.output)
        args, _ = self.mock_client.delete_block_model_columns.call_args
        self.assertEqual(args[0], f.BM_ID)
        self.assertEqual(args[1], ["Cu", "Au"])

    def test_delete_requires_at_least_one_column(self) -> None:
        result = runner.invoke(app, ["blockmodels", "columns", "delete", str(f.BM_ID)])
        self.assertNotEqual(result.exit_code, 0)


class TestColumnsUpdateMetadata(_ColumnsBase):
    def test_set_and_clear_unit(self) -> None:
        self.mock_client.update_column_metadata = mock.AsyncMock(return_value=f.make_version())

        result = runner.invoke(
            app,
            [
                "blockmodels",
                "columns",
                "update-metadata",
                str(f.BM_ID),
                "--set-unit",
                "Cu=%[mass]",
                "--clear-unit",
                "Au",
            ],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        args, _ = self.mock_client.update_column_metadata.call_args
        self.assertEqual(args[0], f.BM_ID)
        self.assertEqual(args[1], {"Cu": "%[mass]", "Au": None})

    def test_requires_at_least_one_update(self) -> None:
        result = runner.invoke(app, ["blockmodels", "columns", "update-metadata", str(f.BM_ID)])
        self.assertNotEqual(result.exit_code, 0)

    def test_rejects_column_in_both_set_and_clear(self) -> None:
        result = runner.invoke(
            app,
            [
                "blockmodels",
                "columns",
                "update-metadata",
                str(f.BM_ID),
                "--set-unit",
                "Cu=%[mass]",
                "--clear-unit",
                "Cu",
            ],
        )
        self.assertNotEqual(result.exit_code, 0)


def _write_sample_table(tmp_path):
    import pyarrow
    import pyarrow.parquet

    path = tmp_path / "data.parquet"
    table = pyarrow.table({"i": [1], "j": [2], "k": [3], "grade": [1.5]})
    pyarrow.parquet.write_table(table, path)
    return path


class TestColumnsAdd(_ColumnsBase):
    def test_add_regular(self) -> None:
        import tempfile
        from pathlib import Path

        self.mock_client.add_new_columns = mock.AsyncMock(return_value=f.make_version())

        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = _write_sample_table(Path(tmpdir))
            result = runner.invoke(
                app,
                ["blockmodels", "columns", "add", str(f.BM_ID), "--data", str(data_path), "--units", "grade=g/t"],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        args, kwargs = self.mock_client.add_new_columns.call_args
        self.assertEqual(args[0], f.BM_ID)
        self.assertEqual(kwargs["units"], {"grade": "g/t"})

    def test_add_subblocked(self) -> None:
        import tempfile
        from pathlib import Path

        self.mock_client.add_new_subblocked_columns = mock.AsyncMock(return_value=f.make_version())

        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = _write_sample_table(Path(tmpdir))
            result = runner.invoke(
                app,
                ["blockmodels", "columns", "add", str(f.BM_ID), "--data", str(data_path), "--subblocked"],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.add_new_subblocked_columns.assert_called_once()


class TestColumnsUpdate(_ColumnsBase):
    def test_update_regular(self) -> None:
        import tempfile
        from pathlib import Path

        self.mock_client.update_block_model_columns = mock.AsyncMock(return_value=f.make_version())

        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = _write_sample_table(Path(tmpdir))
            result = runner.invoke(
                app,
                [
                    "blockmodels",
                    "columns",
                    "update",
                    str(f.BM_ID),
                    "--data",
                    str(data_path),
                    "--new-column",
                    "grade",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        args, kwargs = self.mock_client.update_block_model_columns.call_args
        self.assertEqual(args[2], ["grade"])

    def test_update_subblocked_with_geometry_change(self) -> None:
        import tempfile
        from pathlib import Path

        self.mock_client.update_subblocked_columns = mock.AsyncMock(return_value=f.make_version())

        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = _write_sample_table(Path(tmpdir))
            result = runner.invoke(
                app,
                [
                    "blockmodels",
                    "columns",
                    "update",
                    str(f.BM_ID),
                    "--data",
                    str(data_path),
                    "--new-column",
                    "grade",
                    "--subblocked",
                    "--geometry-change",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        _, kwargs = self.mock_client.update_subblocked_columns.call_args
        self.assertTrue(kwargs["geometry_change"])

    def test_geometry_change_without_subblocked_exits(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = _write_sample_table(Path(tmpdir))
            result = runner.invoke(
                app,
                [
                    "blockmodels",
                    "columns",
                    "update",
                    str(f.BM_ID),
                    "--data",
                    str(data_path),
                    "--new-column",
                    "grade",
                    "--geometry-change",
                ],
            )

        self.assertNotEqual(result.exit_code, 0)
