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
from datetime import datetime, timezone
from typing import Any
from unittest import mock
from uuid import UUID

from typer.testing import CliRunner

from evo.cli.__main__ import app

runner = CliRunner()

_ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_HUB_URL = "https://acme.api.seequent.com"
_WORKSPACE_ID = UUID("11111111-2222-3333-4444-555555555555")
_OBJECT_ID = UUID("aaaaaaaa-0000-0000-0000-000000000001")
_VERSION_ID = "v-abc123"
_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_mock_metadata(
    *,
    obj_id: UUID = _OBJECT_ID,
    name: str = "my_model",
    parent: str = "/models",
    schema_str: str = "PointSet",
    version_id: str = _VERSION_ID,
    modified_at: datetime = _NOW,
) -> mock.Mock:
    meta = mock.Mock()
    meta.id = obj_id
    meta.name = name
    meta.parent = parent
    meta.path = f"{parent}/{name}"
    meta.schema_id = schema_str
    meta.version_id = version_id
    meta.modified_at = modified_at
    meta.modified_by = None
    return meta


def _make_mock_version(*, version_id: str = _VERSION_ID, created_at: datetime = _NOW) -> mock.Mock:
    v = mock.Mock()
    v.version_id = version_id
    v.created_at = created_at
    v.created_by = None
    return v


def _make_mock_downloaded(meta: mock.Mock) -> mock.Mock:
    dl = mock.Mock()
    dl.metadata = meta
    return dl


class _ObjectsBase(unittest.TestCase):
    """Base class that patches the three shared helpers and ObjectAPIClient."""

    def setUp(self) -> None:
        self._patcher_creds = mock.patch("evo.cli.objects.commands.require_credentials", new_callable=mock.AsyncMock)
        self._patcher_env = mock.patch("evo.cli.objects.commands.make_environment")
        self._patcher_conn = mock.patch("evo.cli.objects.commands.make_connector")
        self._patcher_client = mock.patch("evo.cli.objects.commands.ObjectAPIClient")

        self.mock_creds = self._patcher_creds.start()
        self.mock_env = self._patcher_env.start()
        self.mock_conn_ctx = self._patcher_conn.start()
        self.MockClient = self._patcher_client.start()

        # make_connector returns an async context manager
        self.mock_connector = mock.AsyncMock()
        self.mock_connector.__aenter__ = mock.AsyncMock(return_value=self.mock_connector)
        self.mock_connector.__aexit__ = mock.AsyncMock(return_value=False)
        self.mock_conn_ctx.return_value = self.mock_connector

        # ObjectAPIClient instance returned by constructor
        self.mock_client = mock.AsyncMock()
        self.MockClient.return_value = self.mock_client

    def tearDown(self) -> None:
        mock.patch.stopall()


# ---------------------------------------------------------------------------
# objects list
# ---------------------------------------------------------------------------

class TestObjectsList(_ObjectsBase):
    def test_list_plain_output(self) -> None:
        meta = _make_mock_metadata()
        self.mock_client.list_all_objects = mock.AsyncMock(return_value=[meta])

        result = runner.invoke(app, ["objects", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("my_model", result.output)

    def test_list_json_output(self) -> None:
        meta = _make_mock_metadata()
        self.mock_client.list_all_objects = mock.AsyncMock(return_value=[meta])

        result = runner.invoke(app, ["--format", "json", "objects", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        items = json.loads(result.output)
        self.assertIsInstance(items, list)
        self.assertEqual(items[0]["id"], str(_OBJECT_ID))
        self.assertEqual(items[0]["name"], "my_model")
        self.assertEqual(items[0]["path"], "/models/my_model")

    def test_list_empty_plain(self) -> None:
        self.mock_client.list_all_objects = mock.AsyncMock(return_value=[])
        result = runner.invoke(app, ["objects", "list"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No objects found", result.output)

    def test_list_empty_json(self) -> None:
        self.mock_client.list_all_objects = mock.AsyncMock(return_value=[])
        result = runner.invoke(app, ["--format", "json", "objects", "list"])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(json.loads(result.output), [])

    def test_list_type_filter_passed_to_client(self) -> None:
        self.mock_client.list_all_objects = mock.AsyncMock(return_value=[])
        runner.invoke(app, ["objects", "list", "--type", "PointSet"])
        self.mock_client.list_all_objects.assert_called_once()
        _, kwargs = self.mock_client.list_all_objects.call_args
        self.assertEqual(kwargs["schema_id"], ["PointSet"])

    def test_list_deleted_flag(self) -> None:
        self.mock_client.list_all_objects = mock.AsyncMock(return_value=[])
        runner.invoke(app, ["objects", "list", "--deleted"])
        _, kwargs = self.mock_client.list_all_objects.call_args
        self.assertTrue(kwargs["deleted"])


# ---------------------------------------------------------------------------
# objects get
# ---------------------------------------------------------------------------

class TestObjectsGet(_ObjectsBase):
    def test_get_by_path_plain(self) -> None:
        meta = _make_mock_metadata()
        dl = _make_mock_downloaded(meta)
        self.mock_client.download_object_by_path = mock.AsyncMock(return_value=dl)

        result = runner.invoke(app, ["objects", "get", "--path", "/models/my_model"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("my_model", result.output)
        self.mock_client.download_object_by_path.assert_called_once_with("/models/my_model", version=None)

    def test_get_by_id_plain(self) -> None:
        meta = _make_mock_metadata()
        dl = _make_mock_downloaded(meta)
        self.mock_client.download_object_by_id = mock.AsyncMock(return_value=dl)

        result = runner.invoke(app, ["objects", "get", "--id", str(_OBJECT_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.download_object_by_id.assert_called_once_with(_OBJECT_ID, version=None)

    def test_get_json_output(self) -> None:
        meta = _make_mock_metadata()
        dl = _make_mock_downloaded(meta)
        self.mock_client.download_object_by_path = mock.AsyncMock(return_value=dl)

        result = runner.invoke(app, ["--format", "json", "objects", "get", "--path", "/models/my_model"])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["id"], str(_OBJECT_ID))
        self.assertEqual(data["version_id"], _VERSION_ID)

    def test_get_requires_path_or_id(self) -> None:
        result = runner.invoke(app, ["objects", "get"])
        self.assertNotEqual(result.exit_code, 0)

    def test_get_rejects_both_path_and_id(self) -> None:
        result = runner.invoke(app, ["objects", "get", "--path", "/x", "--id", str(_OBJECT_ID)])
        self.assertNotEqual(result.exit_code, 0)

    def test_get_with_version(self) -> None:
        meta = _make_mock_metadata()
        dl = _make_mock_downloaded(meta)
        self.mock_client.download_object_by_path = mock.AsyncMock(return_value=dl)

        runner.invoke(app, ["objects", "get", "--path", "/models/m", "--version", "v-xyz"])

        self.mock_client.download_object_by_path.assert_called_once_with("/models/m", version="v-xyz")


# ---------------------------------------------------------------------------
# objects versions
# ---------------------------------------------------------------------------

class TestObjectsVersions(_ObjectsBase):
    def test_versions_by_path_plain(self) -> None:
        v = _make_mock_version()
        self.mock_client.list_versions_by_path = mock.AsyncMock(return_value=[v])

        result = runner.invoke(app, ["objects", "versions", "--path", "/models/my_model"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(_VERSION_ID, result.output)

    def test_versions_by_id_json(self) -> None:
        v = _make_mock_version()
        self.mock_client.list_versions_by_id = mock.AsyncMock(return_value=[v])

        result = runner.invoke(app, ["--format", "json", "objects", "versions", "--id", str(_OBJECT_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        items = json.loads(result.output)
        self.assertEqual(items[0]["version_id"], _VERSION_ID)

    def test_versions_requires_path_or_id(self) -> None:
        result = runner.invoke(app, ["objects", "versions"])
        self.assertNotEqual(result.exit_code, 0)


# ---------------------------------------------------------------------------
# objects delete
# ---------------------------------------------------------------------------

class TestObjectsDelete(_ObjectsBase):
    def test_delete_by_path_with_yes_flag(self) -> None:
        self.mock_client.delete_object_by_path = mock.AsyncMock(return_value=None)

        result = runner.invoke(app, ["objects", "delete", "--path", "/models/m", "--yes"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.delete_object_by_path.assert_called_once_with("/models/m")

    def test_delete_by_id_with_yes_flag(self) -> None:
        self.mock_client.delete_object_by_id = mock.AsyncMock(return_value=None)

        result = runner.invoke(app, ["objects", "delete", "--id", str(_OBJECT_ID), "--yes"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.delete_object_by_id.assert_called_once_with(_OBJECT_ID)

    def test_delete_json_output(self) -> None:
        self.mock_client.delete_object_by_path = mock.AsyncMock(return_value=None)

        result = runner.invoke(
            app, ["--format", "json", "objects", "delete", "--path", "/models/m", "--yes"]
        )

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "deleted")

    def test_delete_requires_path_or_id(self) -> None:
        result = runner.invoke(app, ["objects", "delete", "--yes"])
        self.assertNotEqual(result.exit_code, 0)


# ---------------------------------------------------------------------------
# objects restore
# ---------------------------------------------------------------------------

class TestObjectsRestore(_ObjectsBase):
    def test_restore_no_rename(self) -> None:
        self.mock_client.restore_geoscience_object = mock.AsyncMock(return_value=None)

        result = runner.invoke(app, ["objects", "restore", str(_OBJECT_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.restore_geoscience_object.assert_called_once_with(_OBJECT_ID)

    def test_restore_with_rename_plain(self) -> None:
        meta = _make_mock_metadata(name="my_model_restored")
        self.mock_client.restore_geoscience_object = mock.AsyncMock(return_value=meta)

        result = runner.invoke(app, ["objects", "restore", str(_OBJECT_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("my_model_restored", result.output)

    def test_restore_json_output(self) -> None:
        self.mock_client.restore_geoscience_object = mock.AsyncMock(return_value=None)

        result = runner.invoke(app, ["--format", "json", "objects", "restore", str(_OBJECT_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "restored")
        self.assertEqual(data["id"], str(_OBJECT_ID))


# ---------------------------------------------------------------------------
# error cases: not logged in / no workspace
# ---------------------------------------------------------------------------

class TestObjectsErrorCases(unittest.TestCase):
    @mock.patch(
        "evo.cli.objects.commands.require_credentials",
        new_callable=mock.AsyncMock,
        side_effect=SystemExit(1),
    )
    def test_list_not_logged_in_exits(self, _mock) -> None:
        result = runner.invoke(app, ["objects", "list"])
        self.assertNotEqual(result.exit_code, 0)

    @mock.patch("evo.cli.objects.commands.require_credentials", new_callable=mock.AsyncMock)
    @mock.patch(
        "evo.cli.objects.commands.make_environment",
        side_effect=SystemExit(1),
    )
    def test_list_no_workspace_exits(self, _mock_env, _mock_creds) -> None:
        result = runner.invoke(app, ["objects", "list"])
        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
