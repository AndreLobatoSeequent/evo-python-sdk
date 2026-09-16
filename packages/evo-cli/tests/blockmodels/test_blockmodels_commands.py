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


class _BlockModelsBase(unittest.TestCase):
    """Base class that patches the shared connector helpers and BlockModelAPIClient."""

    def setUp(self) -> None:
        self._patcher_creds = mock.patch(
            "evo.cli.blockmodels.commands.require_credentials", new_callable=mock.AsyncMock
        )
        self._patcher_env = mock.patch("evo.cli.blockmodels.commands.make_environment")
        self._patcher_conn = mock.patch("evo.cli.blockmodels.commands.make_connector")
        self._patcher_client = mock.patch("evo.cli.blockmodels.commands.BlockModelAPIClient")
        self._patcher_cache = mock.patch("evo.cli.blockmodels.commands.make_cache")

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


# ---------------------------------------------------------------------------
# blockmodels list
# ---------------------------------------------------------------------------

class TestBlockModelsList(_BlockModelsBase):
    def test_list_plain_output(self) -> None:
        bm = f.make_block_model()
        self.mock_client.list_all_block_models = mock.AsyncMock(return_value=[bm])

        result = runner.invoke(app, ["blockmodels", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("my_block_model", result.output)

    def test_list_json_output(self) -> None:
        bm = f.make_block_model()
        self.mock_client.list_all_block_models = mock.AsyncMock(return_value=[bm])

        result = runner.invoke(app, ["--format", "json", "blockmodels", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        items = json.loads(result.output)
        self.assertEqual(items[0]["id"], str(f.BM_ID))
        self.assertEqual(items[0]["grid_definition"]["type"], "regular")
        self.assertEqual(items[0]["grid_definition"]["n_blocks"], [10, 10, 10])

    def test_list_empty_plain(self) -> None:
        self.mock_client.list_all_block_models = mock.AsyncMock(return_value=[])
        result = runner.invoke(app, ["blockmodels", "list"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No block models found", result.output)

    def test_list_deleted_flag(self) -> None:
        self.mock_client.list_all_block_models = mock.AsyncMock(return_value=[])
        runner.invoke(app, ["blockmodels", "list", "--deleted"])
        _, kwargs = self.mock_client.list_all_block_models.call_args
        self.assertTrue(kwargs["deleted"])


# ---------------------------------------------------------------------------
# blockmodels get
# ---------------------------------------------------------------------------

class TestBlockModelsGet(_BlockModelsBase):
    def test_get_plain(self) -> None:
        bm = f.make_block_model()
        self.mock_client.get_block_model = mock.AsyncMock(return_value=bm)

        result = runner.invoke(app, ["blockmodels", "get", str(f.BM_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("my_block_model", result.output)
        self.mock_client.get_block_model.assert_called_once_with(f.BM_ID)

    def test_get_json(self) -> None:
        bm = f.make_block_model()
        self.mock_client.get_block_model = mock.AsyncMock(return_value=bm)

        result = runner.invoke(app, ["--format", "json", "blockmodels", "get", str(f.BM_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["coordinate_reference_system"], "EPSG:3395")
        self.assertEqual(data["bbox"]["x"], [0.0, 10.0])


# ---------------------------------------------------------------------------
# blockmodels create
# ---------------------------------------------------------------------------

class TestBlockModelsCreate(_BlockModelsBase):
    def test_create_regular_grid(self) -> None:
        bm = f.make_block_model()
        version = f.make_version()
        self.mock_client.create_block_model = mock.AsyncMock(return_value=(bm, version))

        result = runner.invoke(
            app,
            [
                "blockmodels",
                "create",
                "my_block_model",
                "--grid-type",
                "regular",
                "--origin",
                "0",
                "0",
                "0",
                "--n-blocks",
                "10",
                "10",
                "10",
                "--block-size",
                "1",
                "1",
                "1",
            ],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.create_block_model.assert_called_once()
        args, kwargs = self.mock_client.create_block_model.call_args
        self.assertEqual(args[0], "my_block_model")
        grid_definition = args[1]
        self.assertEqual(grid_definition.n_blocks, [10, 10, 10])
        self.assertEqual(grid_definition.block_size, [1.0, 1.0, 1.0])

    def test_create_fully_sub_blocked_grid(self) -> None:
        bm = f.make_block_model()
        version = f.make_version()
        self.mock_client.create_block_model = mock.AsyncMock(return_value=(bm, version))

        result = runner.invoke(
            app,
            [
                "blockmodels",
                "create",
                "my_sub_blocked_model",
                "--grid-type",
                "fully-sub-blocked",
                "--origin",
                "0",
                "0",
                "0",
                "--n-parent-blocks",
                "5",
                "5",
                "5",
                "--n-subblocks",
                "2",
                "2",
                "2",
                "--parent-block-size",
                "2",
                "2",
                "2",
            ],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        args, _ = self.mock_client.create_block_model.call_args
        grid_definition = args[1]
        self.assertEqual(grid_definition.n_parent_blocks, [5, 5, 5])
        self.assertEqual(grid_definition.n_subblocks_per_parent, [2, 2, 2])

    def test_create_regular_missing_required_options(self) -> None:
        result = runner.invoke(
            app,
            ["blockmodels", "create", "my_block_model", "--grid-type", "regular", "--origin", "0", "0", "0"],
        )
        self.assertNotEqual(result.exit_code, 0)

    def test_create_invalid_grid_type(self) -> None:
        result = runner.invoke(
            app,
            ["blockmodels", "create", "my_block_model", "--grid-type", "bogus", "--origin", "0", "0", "0"],
        )
        self.assertNotEqual(result.exit_code, 0)

    def test_create_with_rotation(self) -> None:
        bm = f.make_block_model()
        version = f.make_version()
        self.mock_client.create_block_model = mock.AsyncMock(return_value=(bm, version))

        result = runner.invoke(
            app,
            [
                "blockmodels",
                "create",
                "my_block_model",
                "--grid-type",
                "regular",
                "--origin",
                "0",
                "0",
                "0",
                "--n-blocks",
                "10",
                "10",
                "10",
                "--block-size",
                "1",
                "1",
                "1",
                "--rotation",
                "z:45",
            ],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        args, _ = self.mock_client.create_block_model.call_args
        grid_definition = args[1]
        self.assertEqual(grid_definition.rotations[0][1], 45.0)

    def test_create_invalid_rotation(self) -> None:
        result = runner.invoke(
            app,
            [
                "blockmodels",
                "create",
                "my_block_model",
                "--grid-type",
                "regular",
                "--origin",
                "0",
                "0",
                "0",
                "--n-blocks",
                "10",
                "10",
                "10",
                "--block-size",
                "1",
                "1",
                "1",
                "--rotation",
                "bad-format",
            ],
        )
        self.assertNotEqual(result.exit_code, 0)


# ---------------------------------------------------------------------------
# blockmodels update
# ---------------------------------------------------------------------------

class TestBlockModelsUpdate(_BlockModelsBase):
    def test_update_name(self) -> None:
        bm = f.make_block_model(name="renamed")
        self.mock_client.update_block_model_metadata = mock.AsyncMock(return_value=bm)

        result = runner.invoke(app, ["blockmodels", "update", str(f.BM_ID), "--name", "renamed"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("renamed", result.output)
        args, _ = self.mock_client.update_block_model_metadata.call_args
        self.assertEqual(args[0], f.BM_ID)
        self.assertEqual(args[1].name, "renamed")

    def test_update_requires_a_field(self) -> None:
        result = runner.invoke(app, ["blockmodels", "update", str(f.BM_ID)])
        self.assertNotEqual(result.exit_code, 0)

    def test_update_data_defaults_to_updating_non_geometry_columns(self) -> None:
        import pyarrow as pa
        import tempfile
        bm = f.make_block_model()
        version = f.make_version(version_id=7)
        self.mock_client.get_block_model = mock.AsyncMock(return_value=bm)
        self.mock_client.update_block_model_columns = mock.AsyncMock(return_value=version)

        # Simulate a queried table: geometry columns + one data column
        mock_table = pa.table({
            "x": pa.array([0.0], type=pa.float64()),
            "y": pa.array([0.0], type=pa.float64()),
            "Bamovuda": pa.array(["a"], type=pa.string()),
        })
        with mock.patch("evo.cli.blockmodels.commands.read_table_file", return_value=mock_table):
            with tempfile.NamedTemporaryFile(suffix=".csv") as tmp:
                result = runner.invoke(app, ["blockmodels", "update", str(f.BM_ID), "--data", tmp.name])

        self.assertEqual(result.exit_code, 0, result.output)
        _, kwargs = self.mock_client.update_block_model_columns.call_args
        self.assertEqual(kwargs["new_columns"], [])
        self.assertEqual(kwargs["update_columns"], {"Bamovuda"})
        self.assertIn("v7", result.output)

    def test_update_data_with_explicit_column_categories(self) -> None:
        import tempfile
        bm = f.make_block_model()
        version = f.make_version(version_id=8)
        self.mock_client.get_block_model = mock.AsyncMock(return_value=bm)
        self.mock_client.update_block_model_columns = mock.AsyncMock(return_value=version)

        with mock.patch("evo.cli.blockmodels.commands.read_table_file") as mock_read:
            mock_table = mock.MagicMock()
            mock_read.return_value = mock_table
            with tempfile.NamedTemporaryFile(suffix=".csv") as tmp:
                result = runner.invoke(
                    app,
                    [
                        "blockmodels", "update", str(f.BM_ID),
                        "--data", tmp.name,
                        "--new-column", "Lithology",
                        "--update-column", "Density",
                    ],
                )

        self.assertEqual(result.exit_code, 0, result.output)
        _, kwargs = self.mock_client.update_block_model_columns.call_args
        self.assertEqual(kwargs["new_columns"], ["Lithology"])
        self.assertEqual(kwargs["update_columns"], {"Density"})
        self.assertIn("v8", result.output)

    def test_update_delete_column_only(self) -> None:
        bm = f.make_block_model()
        version = f.make_version(version_id=9)
        self.mock_client.get_block_model = mock.AsyncMock(return_value=bm)
        self.mock_client.delete_block_model_columns = mock.AsyncMock(return_value=version)

        result = runner.invoke(
            app, ["blockmodels", "update", str(f.BM_ID), "--delete-column", "OldColumn"]
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.delete_block_model_columns.assert_called_once_with(f.BM_ID, ["OldColumn"])
        self.assertIn("v9", result.output)


# ---------------------------------------------------------------------------
# blockmodels delete
# ---------------------------------------------------------------------------

class TestBlockModelsDelete(_BlockModelsBase):
    def test_delete_with_yes(self) -> None:
        self.mock_client.delete_block_model = mock.AsyncMock(return_value=None)

        result = runner.invoke(app, ["blockmodels", "delete", str(f.BM_ID), "--yes"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.delete_block_model.assert_called_once_with(f.BM_ID)

    def test_delete_json_output(self) -> None:
        self.mock_client.delete_block_model = mock.AsyncMock(return_value=None)

        result = runner.invoke(app, ["--format", "json", "blockmodels", "delete", str(f.BM_ID), "--yes"])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "deleted")


# ---------------------------------------------------------------------------
# error cases: not logged in
# ---------------------------------------------------------------------------

class TestBlockModelsHealth(_BlockModelsBase):
    def test_health_plain(self) -> None:
        health = mock.Mock(service="blockmodel", status=mock.Mock(value="pass"), status_code=200, version="1.2.3")
        self.mock_client.get_service_health = mock.AsyncMock(return_value=health)

        result = runner.invoke(app, ["blockmodels", "health"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("blockmodel", result.output)
        self.assertIn("pass", result.output)

    def test_health_json(self) -> None:
        health = mock.Mock(service="blockmodel", status=mock.Mock(value="pass"), status_code=200, version="1.2.3")
        self.mock_client.get_service_health = mock.AsyncMock(return_value=health)

        result = runner.invoke(app, ["--format", "json", "blockmodels", "health"])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "pass")
        self.assertEqual(data["status_code"], 200)


class TestBlockModelsCreateWithData(_BlockModelsBase):
    def test_create_with_data(self) -> None:
        import tempfile
        from pathlib import Path

        import pyarrow.parquet

        bm = f.make_block_model()
        version = f.make_version()
        self.mock_client.create_block_model = mock.AsyncMock(return_value=(bm, version))

        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = Path(tmpdir) / "data.parquet"
            table = pyarrow.table({"i": [1], "j": [2], "k": [3], "grade": [1.5]})
            pyarrow.parquet.write_table(table, data_path)

            result = runner.invoke(
                app,
                [
                    "blockmodels",
                    "create",
                    "my_block_model",
                    "--grid-type",
                    "regular",
                    "--origin",
                    "0",
                    "0",
                    "0",
                    "--n-blocks",
                    "10",
                    "10",
                    "10",
                    "--block-size",
                    "1",
                    "1",
                    "1",
                    "--data",
                    str(data_path),
                    "--units",
                    "grade=g/t",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.create_block_model.assert_called_once()
        _, kwargs = self.mock_client.create_block_model.call_args
        self.assertEqual(kwargs["units"], {"grade": "g/t"})
        self.assertIsNotNone(kwargs["initial_data"])
        self.mock_cache.assert_called_once()


class TestBlockModelsQuery(_BlockModelsBase):
    def test_query_writes_output_file(self) -> None:
        import tempfile
        from pathlib import Path

        import pyarrow

        table = pyarrow.table({"grade": [1.0, 2.0]})
        self.mock_client.query_block_model_as_table = mock.AsyncMock(return_value=table)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "out.parquet"
            result = runner.invoke(
                app,
                ["blockmodels", "query", str(f.BM_ID), "--column", "grade", "--output", str(out_path)],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue(out_path.exists())

        args, kwargs = self.mock_client.query_block_model_as_table.call_args
        self.assertEqual(args[0], f.BM_ID)
        self.assertEqual(args[1], ["grade"])
        self.assertTrue(kwargs["exclude_null_rows"])

    def test_query_both_bbox_options_exits(self) -> None:
        result = runner.invoke(
            app,
            [
                "blockmodels",
                "query",
                str(f.BM_ID),
                "--column",
                "grade",
                "--output",
                "out.parquet",
                "--bbox-ijk",
                "0,1,0,1,0,1",
                "--bbox-xyz",
                "0,1,0,1,0,1",
            ],
        )
        self.assertNotEqual(result.exit_code, 0)


class TestBlockModelsErrorCases(unittest.TestCase):
    @mock.patch(
        "evo.cli.blockmodels.commands.require_credentials",
        new_callable=mock.AsyncMock,
        side_effect=SystemExit(1),
    )
    def test_list_not_logged_in_exits(self, _mock) -> None:
        result = runner.invoke(app, ["blockmodels", "list"])
        self.assertNotEqual(result.exit_code, 0)
