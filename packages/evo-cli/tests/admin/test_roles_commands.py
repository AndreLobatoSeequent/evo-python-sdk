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
from evo.oauth.data import AccessToken
from evo.workspaces import InstanceRoleWithPermissions

runner = CliRunner()

_ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_HUB_URL = "https://us.api.seequent.com"
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


class TestAdminRolesList(unittest.TestCase):
    @mock.patch("evo.workspaces.WorkspaceAPIClient")
    @mock.patch("evo.cli.admin.roles.build_connector")
    @mock.patch("evo.cli.admin.roles.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.admin.roles.require_login", return_value=_make_creds())
    def test_list_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        role = InstanceRoleWithPermissions(
            role_id=_ROLE_ID, name="Evo admin", description="Full access", permissions=["admin:read", "admin:write"]
        )
        MockClient.return_value.list_instance_roles = mock.AsyncMock(return_value=[role])

        result = runner.invoke(app, ["admin", "roles", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Evo admin", result.output)
        self.assertIn(str(_ROLE_ID), result.output)

    @mock.patch("evo.workspaces.WorkspaceAPIClient")
    @mock.patch("evo.cli.admin.roles.build_connector")
    @mock.patch("evo.cli.admin.roles.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.admin.roles.require_login", return_value=_make_creds())
    def test_list_empty(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.list_instance_roles = mock.AsyncMock(return_value=[])

        result = runner.invoke(app, ["admin", "roles", "list"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No instance roles found", result.output)


if __name__ == "__main__":
    unittest.main()
