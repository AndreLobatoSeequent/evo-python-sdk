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
from pathlib import Path
from unittest import mock
from uuid import UUID

from typer.testing import CliRunner

from evo.cli.__main__ import app

runner = CliRunner()

_FILE_ID = UUID("bbbbbbbb-0000-0000-0000-000000000001")
_VERSION_ID = "v-file-001"
_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_mock_meta(
    *,
    file_id: UUID = _FILE_ID,
    name: str = "survey.dat",
    parent: str = "/surveys",
    version_id: str = _VERSION_ID,
    size: int = 1024,
    modified_at: datetime = _NOW,
) -> mock.Mock:
    meta = mock.Mock()
    meta.id = file_id
    meta.name = name
    meta.parent = parent
    meta.path = f"{parent}/{name}"
    meta.version_id = version_id
    meta.size = size
    meta.modified_at = modified_at
    meta.modified_by = None
    meta.environment = mock.Mock()
    return meta


def _make_mock_version(*, version_id: str = _VERSION_ID, created_at: datetime = _NOW) -> mock.Mock:
    v = mock.Mock()
    v.version_id = version_id
    v.created_at = created_at
    v.created_by = None
    return v


class _FilesBase(unittest.TestCase):
    def setUp(self) -> None:
        self._patcher_creds = mock.patch("evo.cli.files.commands.require_credentials", new_callable=mock.AsyncMock)
        self._patcher_env = mock.patch("evo.cli.files.commands.make_environment")
        self._patcher_conn = mock.patch("evo.cli.files.commands.make_connector")
        self._patcher_transport = mock.patch("evo.cli.files.commands.make_transport")
        self._patcher_client = mock.patch("evo.files.FileAPIClient")

        self.mock_creds = self._patcher_creds.start()
        self.mock_env = self._patcher_env.start()
        self.mock_conn_ctx = self._patcher_conn.start()
        self.mock_transport = self._patcher_transport.start()
        self.MockClient = self._patcher_client.start()

        self.mock_connector = mock.AsyncMock()
        self.mock_connector.__aenter__ = mock.AsyncMock(return_value=self.mock_connector)
        self.mock_connector.__aexit__ = mock.AsyncMock(return_value=False)
        self.mock_conn_ctx.return_value = self.mock_connector

        self.mock_client = mock.AsyncMock()
        self.MockClient.return_value = self.mock_client

    def tearDown(self) -> None:
        mock.patch.stopall()


# ---------------------------------------------------------------------------
# files list
# ---------------------------------------------------------------------------


class TestFilesList(_FilesBase):
    def test_list_plain_output(self) -> None:
        self.mock_client.list_all_files = mock.AsyncMock(return_value=[_make_mock_meta()])
        result = runner.invoke(app, ["files", "list"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("survey.dat", result.output)

    def test_list_json_output(self) -> None:
        self.mock_client.list_all_files = mock.AsyncMock(return_value=[_make_mock_meta()])
        result = runner.invoke(app, ["--format", "json", "files", "list"])
        self.assertEqual(result.exit_code, 0, result.output)
        items = json.loads(result.output)
        self.assertEqual(items[0]["name"], "survey.dat")
        self.assertEqual(items[0]["size"], 1024)

    def test_list_empty(self) -> None:
        self.mock_client.list_all_files = mock.AsyncMock(return_value=[])
        result = runner.invoke(app, ["files", "list"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No files found", result.output)

    def test_list_name_filter_passed(self) -> None:
        self.mock_client.list_all_files = mock.AsyncMock(return_value=[])
        runner.invoke(app, ["files", "list", "--name", "survey.dat"])
        _, kwargs = self.mock_client.list_all_files.call_args
        self.assertEqual(kwargs["name"], "survey.dat")

    def test_list_deleted_flag(self) -> None:
        self.mock_client.list_all_files = mock.AsyncMock(return_value=[])
        runner.invoke(app, ["files", "list", "--deleted"])
        _, kwargs = self.mock_client.list_all_files.call_args
        self.assertTrue(kwargs["deleted"])


# ---------------------------------------------------------------------------
# files get
# ---------------------------------------------------------------------------


class TestFilesGet(_FilesBase):
    def test_get_by_path(self) -> None:
        meta = _make_mock_meta()
        self.mock_client.get_file_by_path = mock.AsyncMock(return_value=meta)
        result = runner.invoke(app, ["files", "get", "--path", "/surveys/survey.dat"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("survey.dat", result.output)
        self.mock_client.get_file_by_path.assert_called_once_with("/surveys/survey.dat", version_id=None)

    def test_get_by_id(self) -> None:
        meta = _make_mock_meta()
        self.mock_client.get_file_by_id = mock.AsyncMock(return_value=meta)
        result = runner.invoke(app, ["files", "get", "--id", str(_FILE_ID)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.get_file_by_id.assert_called_once_with(_FILE_ID, version_id=None)

    def test_get_json_has_size(self) -> None:
        meta = _make_mock_meta()
        self.mock_client.get_file_by_path = mock.AsyncMock(return_value=meta)
        result = runner.invoke(app, ["--format", "json", "files", "get", "--path", "/surveys/survey.dat"])
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["size"], 1024)

    def test_get_requires_path_or_id(self) -> None:
        result = runner.invoke(app, ["files", "get"])
        self.assertNotEqual(result.exit_code, 0)

    def test_get_rejects_both(self) -> None:
        result = runner.invoke(app, ["files", "get", "--path", "/x", "--id", str(_FILE_ID)])
        self.assertNotEqual(result.exit_code, 0)

    def test_get_with_version(self) -> None:
        meta = _make_mock_meta()
        self.mock_client.get_file_by_path = mock.AsyncMock(return_value=meta)
        runner.invoke(app, ["files", "get", "--path", "/surveys/survey.dat", "--version", "v-xyz"])
        self.mock_client.get_file_by_path.assert_called_once_with("/surveys/survey.dat", version_id="v-xyz")


# ---------------------------------------------------------------------------
# files versions
# ---------------------------------------------------------------------------


class TestFilesVersions(_FilesBase):
    def test_versions_by_path(self) -> None:
        v = _make_mock_version()
        self.mock_client.list_versions_by_path = mock.AsyncMock(return_value=[v])
        result = runner.invoke(app, ["files", "versions", "--path", "/surveys/survey.dat"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(_VERSION_ID, result.output)

    def test_versions_by_id_json(self) -> None:
        v = _make_mock_version()
        self.mock_client.list_versions_by_id = mock.AsyncMock(return_value=[v])
        result = runner.invoke(app, ["--format", "json", "files", "versions", "--id", str(_FILE_ID)])
        self.assertEqual(result.exit_code, 0, result.output)
        items = json.loads(result.output)
        self.assertEqual(items[0]["version_id"], _VERSION_ID)

    def test_versions_requires_path_or_id(self) -> None:
        result = runner.invoke(app, ["files", "versions"])
        self.assertNotEqual(result.exit_code, 0)


# ---------------------------------------------------------------------------
# files upload
# ---------------------------------------------------------------------------


class TestFilesUpload(_FilesBase):
    def test_upload_new_file(self, tmp_path=None) -> None:
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".dat") as f:
            f.write(b"data")
            src = f.name
        try:
            # get_file_by_path raises → new file
            self.mock_client.get_file_by_path = mock.AsyncMock(side_effect=Exception("not found"))
            upload_ctx = mock.AsyncMock()
            upload_ctx.file_id = _FILE_ID
            upload_ctx.version_id = _VERSION_ID
            upload_ctx.upload_from_path = mock.AsyncMock()
            self.mock_client.prepare_upload_by_path = mock.AsyncMock(return_value=upload_ctx)

            result = runner.invoke(app, ["files", "upload", "--src", src, "--dest", "/surveys/survey.dat"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Uploaded", result.output)
            self.assertNotIn("new version", result.output.lower())
        finally:
            os.unlink(src)

    def test_upload_new_version_detected(self) -> None:
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".dat") as f:
            f.write(b"data")
            src = f.name
        try:
            # get_file_by_path succeeds → existing file → new version
            self.mock_client.get_file_by_path = mock.AsyncMock(return_value=_make_mock_meta())
            upload_ctx = mock.AsyncMock()
            upload_ctx.file_id = _FILE_ID
            upload_ctx.version_id = "v-002"
            upload_ctx.upload_from_path = mock.AsyncMock()
            self.mock_client.prepare_upload_by_path = mock.AsyncMock(return_value=upload_ctx)

            result = runner.invoke(app, ["files", "upload", "--src", src, "--dest", "/surveys/survey.dat"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("New version", result.output)
        finally:
            os.unlink(src)

    def test_upload_new_version_json(self) -> None:
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".dat") as f:
            f.write(b"data")
            src = f.name
        try:
            self.mock_client.get_file_by_path = mock.AsyncMock(return_value=_make_mock_meta())
            upload_ctx = mock.AsyncMock()
            upload_ctx.file_id = _FILE_ID
            upload_ctx.version_id = "v-002"
            upload_ctx.upload_from_path = mock.AsyncMock()
            self.mock_client.prepare_upload_by_path = mock.AsyncMock(return_value=upload_ctx)

            result = runner.invoke(
                app, ["--format", "json", "files", "upload", "--src", src, "--dest", "/surveys/survey.dat"]
            )
            self.assertEqual(result.exit_code, 0, result.output)
            data = json.loads(result.output)
            self.assertEqual(data["status"], "new_version")
            self.assertEqual(data["version_id"], "v-002")
        finally:
            os.unlink(src)

    def test_upload_missing_src_exits(self) -> None:
        result = runner.invoke(app, ["files", "upload", "--src", "/nonexistent.dat", "--dest", "/surveys/x.dat"])
        self.assertNotEqual(result.exit_code, 0)


# ---------------------------------------------------------------------------
# files download
# ---------------------------------------------------------------------------


class TestFilesDownload(_FilesBase):
    def test_download_by_path_to_explicit_output(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = str(Path(tmpdir) / "out.dat")
            meta = _make_mock_meta()
            dl = mock.AsyncMock()
            dl.metadata = meta
            dl.download_to_path = mock.AsyncMock()
            self.mock_client.prepare_download_by_path = mock.AsyncMock(return_value=dl)

            result = runner.invoke(app, ["files", "download", "--path", "/surveys/survey.dat", "--output", dest])
            self.assertEqual(result.exit_code, 0, result.output)
            dl.download_to_path.assert_called_once()

    def test_download_existing_file_agent_mode_fails(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as f:
            existing = f.name
        try:
            meta = _make_mock_meta()
            dl = mock.AsyncMock()
            dl.metadata = meta
            dl.download_to_path = mock.AsyncMock()
            self.mock_client.prepare_download_by_path = mock.AsyncMock(return_value=dl)

            result = runner.invoke(
                app,
                ["files", "download", "--path", "/surveys/survey.dat", "--output", existing],
                env={"EVO_CLI_AGENT_MODE": "1"},
            )
            self.assertNotEqual(result.exit_code, 0)
        finally:
            import os

            os.unlink(existing)

    def test_download_overwrite_flag_skips_check(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as f:
            existing = f.name
        try:
            meta = _make_mock_meta()
            dl = mock.AsyncMock()
            dl.metadata = meta
            dl.download_to_path = mock.AsyncMock()
            self.mock_client.prepare_download_by_path = mock.AsyncMock(return_value=dl)

            result = runner.invoke(
                app,
                ["files", "download", "--path", "/surveys/survey.dat", "--output", existing, "--overwrite"],
                env={"EVO_CLI_AGENT_MODE": "1"},
            )
            self.assertEqual(result.exit_code, 0, result.output)
        finally:
            import os

            os.unlink(existing)

    def test_download_requires_path_or_id(self) -> None:
        result = runner.invoke(app, ["files", "download"])
        self.assertNotEqual(result.exit_code, 0)

    def test_download_json_output(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = str(Path(tmpdir) / "out.dat")
            meta = _make_mock_meta()
            dl = mock.AsyncMock()
            dl.metadata = meta
            dl.download_to_path = mock.AsyncMock()
            self.mock_client.prepare_download_by_path = mock.AsyncMock(return_value=dl)

            result = runner.invoke(
                app,
                ["--format", "json", "files", "download", "--path", "/surveys/survey.dat", "--output", dest],
            )
            self.assertEqual(result.exit_code, 0, result.output)
            data = json.loads(result.output)
            self.assertEqual(data["status"], "downloaded")
            self.assertIn("size", data)


# ---------------------------------------------------------------------------
# files delete
# ---------------------------------------------------------------------------


class TestFilesDelete(_FilesBase):
    def test_delete_by_path_with_yes(self) -> None:
        self.mock_client.delete_file_by_path = mock.AsyncMock()
        result = runner.invoke(app, ["files", "delete", "--path", "/surveys/survey.dat", "--yes"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.delete_file_by_path.assert_called_once_with("/surveys/survey.dat")

    def test_delete_by_id_with_yes(self) -> None:
        self.mock_client.delete_file_by_id = mock.AsyncMock()
        result = runner.invoke(app, ["files", "delete", "--id", str(_FILE_ID), "--yes"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.delete_file_by_id.assert_called_once_with(_FILE_ID)

    def test_delete_json(self) -> None:
        self.mock_client.delete_file_by_path = mock.AsyncMock()
        result = runner.invoke(app, ["--format", "json", "files", "delete", "--path", "/surveys/survey.dat", "--yes"])
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "deleted")

    def test_delete_requires_path_or_id(self) -> None:
        result = runner.invoke(app, ["files", "delete", "--yes"])
        self.assertNotEqual(result.exit_code, 0)


# ---------------------------------------------------------------------------
# files restore
# ---------------------------------------------------------------------------


class TestFilesRestore(_FilesBase):
    def test_restore_no_rename(self) -> None:
        self.mock_client.restore_file_by_id = mock.AsyncMock(return_value=None)
        result = runner.invoke(app, ["files", "restore", str(_FILE_ID)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_client.restore_file_by_id.assert_called_once_with(_FILE_ID)

    def test_restore_with_rename(self) -> None:
        meta = _make_mock_meta(name="survey_restored.dat")
        self.mock_client.restore_file_by_id = mock.AsyncMock(return_value=meta)
        result = runner.invoke(app, ["files", "restore", str(_FILE_ID)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("survey_restored.dat", result.output)

    def test_restore_json(self) -> None:
        self.mock_client.restore_file_by_id = mock.AsyncMock(return_value=None)
        result = runner.invoke(app, ["--format", "json", "files", "restore", str(_FILE_ID)])
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "restored")


if __name__ == "__main__":
    unittest.main()
