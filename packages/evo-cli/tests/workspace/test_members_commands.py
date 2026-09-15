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
from unittest import mock
from uuid import UUID

from typer.testing import CliRunner

from evo.cli.__main__ import app
from evo.cli.auth.token_store import StoredCredentials
from evo.common.exceptions import NotFoundException
from evo.oauth.data import AccessToken
from evo.workspaces import User, UserRole, WorkspaceRole

runner = CliRunner()

_ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_HUB_URL = "https://us.api.seequent.com"
_WORKSPACE_ID = UUID("11111111-2222-3333-4444-555555555555")
_USER_ID = UUID("22222222-2222-2222-2222-222222222222")


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


class TestMembersList(unittest.TestCase):
    @mock.patch("evo.cli.workspace.members.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.members.build_connector")
    @mock.patch("evo.cli.workspace.members.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.members.require_login", return_value=_make_creds())
    def test_list_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        users = [User(user_id=_USER_ID, role=WorkspaceRole.owner, email="jane@acme.com", full_name="Jane Doe")]
        MockClient.return_value.list_user_roles = mock.AsyncMock(return_value=users)

        result = runner.invoke(app, ["workspace", "members", "list", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("jane@acme.com", result.output)
        self.assertIn("owner", result.output)

    @mock.patch("evo.cli.workspace.members.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.members.build_connector")
    @mock.patch("evo.cli.workspace.members.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.members.require_login", return_value=_make_creds())
    def test_list_empty(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.list_user_roles = mock.AsyncMock(return_value=[])

        result = runner.invoke(app, ["workspace", "members", "list", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No members found", result.output)

    @mock.patch("evo.cli.workspace.members.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.members.build_connector")
    @mock.patch("evo.cli.workspace.members.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.members.require_login", return_value=_make_creds())
    def test_list_json(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        users = [User(user_id=_USER_ID, role=WorkspaceRole.editor, email="jane@acme.com", full_name="Jane Doe")]
        MockClient.return_value.list_user_roles = mock.AsyncMock(return_value=users)

        result = runner.invoke(app, ["--format", "json", "workspace", "members", "list", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["members"], [{"user_id": str(_USER_ID), "email": "jane@acme.com", "full_name": "Jane Doe", "role": "editor"}])

    @mock.patch("evo.cli.workspace.members.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.members.build_connector")
    @mock.patch("evo.cli.workspace.members.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.members.require_login", return_value=_make_creds())
    def test_list_not_found(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.list_user_roles = mock.AsyncMock(
            side_effect=NotFoundException(status=404, reason="Not Found", content=None, headers=None)
        )

        result = runner.invoke(app, ["workspace", "members", "list", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 4)
        self.assertIn("not found", result.output)


class TestMembersGet(unittest.TestCase):
    @mock.patch("evo.cli.workspace.members.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.members.build_connector")
    @mock.patch("evo.cli.workspace.members.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.members.require_login", return_value=_make_creds())
    def test_get_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.get_current_user_role = mock.AsyncMock(
            return_value=UserRole(user_id=_USER_ID, role=WorkspaceRole.viewer)
        )

        result = runner.invoke(app, ["workspace", "members", "get", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("viewer", result.output)


class TestMembersSet(unittest.TestCase):
    @mock.patch("evo.cli.workspace.members.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.members.build_connector")
    @mock.patch("evo.cli.workspace.members.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.members.require_login", return_value=_make_creds())
    def test_set_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.assign_user_role = mock.AsyncMock(
            return_value=UserRole(user_id=_USER_ID, role=WorkspaceRole.editor)
        )

        result = runner.invoke(app, ["workspace", "members", "set", str(_WORKSPACE_ID), str(_USER_ID), "editor"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("editor", result.output)
        MockClient.return_value.assign_user_role.assert_called_once_with(_WORKSPACE_ID, _USER_ID, WorkspaceRole.editor)

    def test_set_invalid_role(self):
        with mock.patch("evo.cli.workspace.members.require_login", return_value=_make_creds()):
            result = runner.invoke(app, ["workspace", "members", "set", str(_WORKSPACE_ID), str(_USER_ID), "bogus"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid role", result.output)


class TestMembersRemove(unittest.TestCase):
    @mock.patch("evo.cli.workspace.members.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.members.build_connector")
    @mock.patch("evo.cli.workspace.members.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.members.require_login", return_value=_make_creds())
    def test_remove_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.delete_user_role = mock.AsyncMock(return_value=None)

        result = runner.invoke(app, ["workspace", "members", "remove", str(_WORKSPACE_ID), str(_USER_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Removed", result.output)
        MockClient.return_value.delete_user_role.assert_called_once_with(_WORKSPACE_ID, _USER_ID)


if __name__ == "__main__":
    unittest.main()
