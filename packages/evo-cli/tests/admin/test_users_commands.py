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
from evo.common import Page
from evo.oauth.data import AccessToken
from evo.workspaces import AddedInstanceUsers, InstanceRole, InstanceUser, InstanceUserWithEmail

runner = CliRunner()

_ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_HUB_URL = "https://us.api.seequent.com"
_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
_ROLE_ID = UUID("33333333-3333-3333-3333-333333333333")


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


class TestAdminUsersList(unittest.TestCase):
    @mock.patch("evo.cli.admin.users.WorkspaceAPIClient")
    @mock.patch("evo.cli.admin.users.build_connector")
    @mock.patch("evo.cli.admin.users.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.admin.users.require_login", return_value=_make_creds())
    def test_list_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        user = InstanceUserWithEmail(
            user_id=_USER_ID,
            email="jane@acme.com",
            full_name="Jane Doe",
            roles=[InstanceRole(role_id=_ROLE_ID, name="Evo user", description="Base role")],
        )
        page = Page(offset=0, limit=50, total=1, items=[user])
        MockClient.return_value.list_instance_users = mock.AsyncMock(return_value=page)

        result = runner.invoke(app, ["admin", "users", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("jane@acme.com", result.output)
        self.assertIn("Evo user", result.output)

    @mock.patch("evo.cli.admin.users.WorkspaceAPIClient")
    @mock.patch("evo.cli.admin.users.build_connector")
    @mock.patch("evo.cli.admin.users.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.admin.users.require_login", return_value=_make_creds())
    def test_list_all_uses_list_all_instance_users(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        user = InstanceUserWithEmail(user_id=_USER_ID, email="jane@acme.com", full_name="Jane Doe", roles=[])
        MockClient.return_value.list_all_instance_users = mock.AsyncMock(return_value=[user])

        result = runner.invoke(app, ["admin", "users", "list", "--all"])

        self.assertEqual(result.exit_code, 0, result.output)
        MockClient.return_value.list_all_instance_users.assert_called_once()

    @mock.patch("evo.cli.admin.users.WorkspaceAPIClient")
    @mock.patch("evo.cli.admin.users.build_connector")
    @mock.patch("evo.cli.admin.users.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.admin.users.require_login", return_value=_make_creds())
    def test_list_json(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        user = InstanceUserWithEmail(
            user_id=_USER_ID,
            email="jane@acme.com",
            full_name="Jane Doe",
            roles=[InstanceRole(role_id=_ROLE_ID, name="Evo user", description="Base role")],
        )
        page = Page(offset=0, limit=50, total=1, items=[user])
        MockClient.return_value.list_instance_users = mock.AsyncMock(return_value=page)

        result = runner.invoke(app, ["--format", "json", "admin", "users", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["users"][0]["email"], "jane@acme.com")
        self.assertEqual(data["users"][0]["roles"], [{"role_id": str(_ROLE_ID), "name": "Evo user"}])

    @mock.patch("evo.cli.admin.users.WorkspaceAPIClient")
    @mock.patch("evo.cli.admin.users.build_connector")
    @mock.patch("evo.cli.admin.users.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.admin.users.require_login", return_value=_make_creds())
    def test_list_empty(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        page = Page(offset=0, limit=50, total=0, items=[])
        MockClient.return_value.list_instance_users = mock.AsyncMock(return_value=page)

        result = runner.invoke(app, ["admin", "users", "list"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No instance users found", result.output)


class TestAdminUsersRemove(unittest.TestCase):
    @mock.patch("evo.cli.admin.users.WorkspaceAPIClient")
    @mock.patch("evo.cli.admin.users.build_connector")
    @mock.patch("evo.cli.admin.users.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.admin.users.require_login", return_value=_make_creds())
    def test_remove_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.remove_instance_user = mock.AsyncMock(return_value=None)

        result = runner.invoke(app, ["admin", "users", "remove", str(_USER_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        MockClient.return_value.remove_instance_user.assert_called_once_with(_USER_ID)


class TestAdminUsersSetRoles(unittest.TestCase):
    @mock.patch("evo.cli.admin.users.WorkspaceAPIClient")
    @mock.patch("evo.cli.admin.users.build_connector")
    @mock.patch("evo.cli.admin.users.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.admin.users.require_login", return_value=_make_creds())
    def test_set_roles_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        updated = InstanceUser(user_id=_USER_ID, roles=[InstanceRole(role_id=_ROLE_ID, name="Evo admin", description="")])
        MockClient.return_value.update_instance_user_roles = mock.AsyncMock(return_value=updated)

        result = runner.invoke(app, ["admin", "users", "set-roles", str(_USER_ID), str(_ROLE_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Evo admin", result.output)
        MockClient.return_value.update_instance_user_roles.assert_called_once_with(_USER_ID, [_ROLE_ID])


class TestAdminUsersInvite(unittest.TestCase):
    @mock.patch("evo.cli.admin.users.WorkspaceAPIClient")
    @mock.patch("evo.cli.admin.users.build_connector")
    @mock.patch("evo.cli.admin.users.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.admin.users.require_login", return_value=_make_creds())
    def test_invite_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        result_obj = AddedInstanceUsers(
            members=[InstanceUserWithEmail(user_id=_USER_ID, email="jane@acme.com", full_name="Jane Doe", roles=[])],
            invitations=[],
        )
        MockClient.return_value.add_users_to_instance = mock.AsyncMock(return_value=result_obj)

        result = runner.invoke(app, ["admin", "users", "invite", "--user", f"jane@acme.com:{_ROLE_ID}"])

        self.assertEqual(result.exit_code, 0, result.output)
        MockClient.return_value.add_users_to_instance.assert_called_once_with({"jane@acme.com": [_ROLE_ID]})

    def test_invite_invalid_format_errors(self):
        with mock.patch("evo.cli.admin.users.require_login", return_value=_make_creds()):
            result = runner.invoke(app, ["admin", "users", "invite", "--user", "no-colon-here"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid --user", result.output)


if __name__ == "__main__":
    unittest.main()
