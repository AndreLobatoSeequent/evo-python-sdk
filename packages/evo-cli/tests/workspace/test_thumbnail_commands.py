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

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from uuid import UUID

from typer.testing import CliRunner

from evo.cli.__main__ import app
from evo.cli.auth.token_store import StoredCredentials
from evo.common.exceptions import NotFoundException
from evo.oauth.data import AccessToken

runner = CliRunner()

_ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_HUB_URL = "https://us.api.seequent.com"
_WORKSPACE_ID = UUID("11111111-2222-3333-4444-555555555555")


def _make_creds(**kwargs) -> StoredCredentials:
    token = AccessToken(
        token_type="Bearer", access_token="access", expires_in=3600, issued_at=datetime.now(timezone.utc)
    )
    defaults = dict(token=token, org_id=_ORG_ID, org_name="ACME Mining", hub_url=_HUB_URL, hub_code="us")
    return StoredCredentials(**{**defaults, **kwargs})


def _make_connector_cm():
    connector = mock.AsyncMock()
    connector.__aenter__ = mock.AsyncMock(return_value=connector)
    connector.__aexit__ = mock.AsyncMock(return_value=False)
    return connector


class TestThumbnailGet(unittest.TestCase):
    @mock.patch("evo.workspaces.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.thumbnail.build_connector")
    @mock.patch("evo.cli.workspace.thumbnail.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.thumbnail.require_login", return_value=_make_creds())
    def test_get_writes_file(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.get_thumbnail = mock.AsyncMock(return_value=bytearray(b"\x89PNG\r\n"))

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "thumb.png"
            result = runner.invoke(app, ["workspace", "thumbnail", "get", str(_WORKSPACE_ID), "--file", str(out_path)])

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue(out_path.exists())
            self.assertEqual(out_path.read_bytes(), b"\x89PNG\r\n")

    @mock.patch("evo.workspaces.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.thumbnail.build_connector")
    @mock.patch("evo.cli.workspace.thumbnail.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.thumbnail.require_login", return_value=_make_creds())
    def test_get_not_found(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.get_thumbnail = mock.AsyncMock(
            side_effect=NotFoundException(status=404, reason="Not Found", content=None, headers=None)
        )

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "thumb.png"
            result = runner.invoke(app, ["workspace", "thumbnail", "get", str(_WORKSPACE_ID), "--file", str(out_path)])

        self.assertEqual(result.exit_code, 4)
        self.assertIn("no thumbnail", result.output)


class TestThumbnailSet(unittest.TestCase):
    @mock.patch("evo.workspaces.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.thumbnail.build_connector")
    @mock.patch("evo.cli.workspace.thumbnail.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.thumbnail.require_login", return_value=_make_creds())
    def test_set_uploads_file_contents(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.put_thumbnail = mock.AsyncMock(return_value=None)

        with tempfile.TemporaryDirectory() as tmp:
            in_path = Path(tmp) / "thumb.png"
            in_path.write_bytes(b"\x89PNG\r\n")
            result = runner.invoke(app, ["workspace", "thumbnail", "set", str(_WORKSPACE_ID), "--file", str(in_path)])

        self.assertEqual(result.exit_code, 0, result.output)
        MockClient.return_value.put_thumbnail.assert_called_once()
        call_args = MockClient.return_value.put_thumbnail.call_args
        self.assertEqual(call_args.args[0], _WORKSPACE_ID)
        self.assertEqual(bytes(call_args.args[1]), b"\x89PNG\r\n")

    def test_set_missing_file_errors(self):
        with mock.patch("evo.cli.workspace.thumbnail.require_login", return_value=_make_creds()):
            result = runner.invoke(
                app, ["workspace", "thumbnail", "set", str(_WORKSPACE_ID), "--file", "/no/such/file.png"]
            )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("File not found", result.output)


class TestThumbnailDelete(unittest.TestCase):
    @mock.patch("evo.workspaces.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.thumbnail.build_connector")
    @mock.patch("evo.cli.workspace.thumbnail.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.thumbnail.require_login", return_value=_make_creds())
    def test_delete_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.delete_thumbnail = mock.AsyncMock(return_value=None)

        result = runner.invoke(app, ["workspace", "thumbnail", "delete", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        MockClient.return_value.delete_thumbnail.assert_called_once_with(_WORKSPACE_ID)


if __name__ == "__main__":
    unittest.main()
