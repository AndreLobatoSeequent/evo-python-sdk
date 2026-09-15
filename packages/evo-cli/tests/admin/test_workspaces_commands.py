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
from datetime import datetime, timezone
from unittest import mock
from uuid import UUID

from typer.testing import CliRunner

from evo.cli.__main__ import app
from evo.cli.auth.token_store import StoredCredentials
from evo.common import Page
from evo.common.data import ServiceUser
from evo.oauth.data import AccessToken
from evo.workspaces import User, Workspace, WorkspaceRole

runner = CliRunner()

_ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_HUB_URL = "https://us.api.seequent.com"
_WORKSPACE_ID = UUID("11111111-2222-3333-4444-555555555555")
_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
_USER = ServiceUser(id=_USER_ID, name="Jane Doe", email="jane@acme.com")


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


def _make_workspace(**kwargs) -> Workspace:
    defaults = dict(
        id=_WORKSPACE_ID,
        display_name="Other User's Workspace",
        description=None,
        user_role=WorkspaceRole.viewer,
        org_id=_ORG_ID,
        hub_url=_HUB_URL,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        created_by=_USER,
        updated_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        updated_by=_USER,
        labels=[],
    )
    return Workspace(**{**defaults, **kwargs})


class TestAdminWorkspacesList(unittest.TestCase):
    @mock.patch("evo.cli.admin.workspaces.WorkspaceAPIClient")
    @mock.patch("evo.cli.admin.workspaces.build_connector")
    @mock.patch("evo.cli.admin.workspaces.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.admin.workspaces.require_login", return_value=_make_creds())
    def test_list_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        page = Page(offset=0, limit=50, total=1, items=[_make_workspace()])
        MockClient.return_value.list_workspaces_admin = mock.AsyncMock(return_value=page)

        result = runner.invoke(app, ["admin", "workspaces", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Other User's Workspace", result.output)
        self.assertIn("admin view", result.output)

    @mock.patch("evo.cli.admin.workspaces.WorkspaceAPIClient")
    @mock.patch("evo.cli.admin.workspaces.build_connector")
    @mock.patch("evo.cli.admin.workspaces.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.admin.workspaces.require_login", return_value=_make_creds())
    def test_list_all_paginates(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        page1 = Page(offset=0, limit=1, total=2, items=[_make_workspace()])
        page2 = Page(offset=1, limit=1, total=2, items=[_make_workspace(id=UUID(int=99), display_name="Second")])
        MockClient.return_value.list_workspaces_admin = mock.AsyncMock(side_effect=[page1, page2])

        result = runner.invoke(app, ["admin", "workspaces", "list", "--all", "--limit", "1"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(MockClient.return_value.list_workspaces_admin.call_count, 2)
        self.assertIn("Second", result.output)

    @mock.patch("evo.cli.admin.workspaces.WorkspaceAPIClient")
    @mock.patch("evo.cli.admin.workspaces.build_connector")
    @mock.patch("evo.cli.admin.workspaces.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.admin.workspaces.require_login", return_value=_make_creds())
    def test_list_empty(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        page = Page(offset=0, limit=50, total=0, items=[])
        MockClient.return_value.list_workspaces_admin = mock.AsyncMock(return_value=page)

        result = runner.invoke(app, ["admin", "workspaces", "list"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No workspaces found", result.output)


class TestAdminWorkspacesMembers(unittest.TestCase):
    @mock.patch("evo.cli.admin.workspaces.WorkspaceAPIClient")
    @mock.patch("evo.cli.admin.workspaces.build_connector")
    @mock.patch("evo.cli.admin.workspaces.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.admin.workspaces.require_login", return_value=_make_creds())
    def test_members_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        users = [User(user_id=_USER_ID, role=WorkspaceRole.owner, email="jane@acme.com", full_name="Jane Doe")]
        MockClient.return_value.list_user_roles_admin = mock.AsyncMock(return_value=users)

        result = runner.invoke(app, ["admin", "workspaces", "members", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("jane@acme.com", result.output)
        MockClient.return_value.list_user_roles_admin.assert_called_once_with(_WORKSPACE_ID, filter_user_id=None)


if __name__ == "__main__":
    unittest.main()
