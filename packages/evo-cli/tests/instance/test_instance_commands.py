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
from evo.cli.config import EvoEnvironment
from evo.cli.state import CurrentSelection
from evo.discovery import Hub, Organization
from evo.oauth.data import AccessToken

runner = CliRunner()

_ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_ORG_NAME = "ACME Mining"
_US_HUB = Hub(url="https://us.api.seequent.com", code="us", display_name="US Hub", services=("evo",))
_AU_HUB = Hub(url="https://au.api.seequent.com", code="au", display_name="AU Hub", services=("evo",))
_TEST_ENV = EvoEnvironment(name="prod", ims_url="https://ims.example.com", discovery_url="https://discover.example.com")


def _make_creds(**kwargs) -> StoredCredentials:
    token = AccessToken(
        token_type="Bearer", access_token="access", expires_in=3600, issued_at=datetime.now(timezone.utc)
    )
    defaults = dict(token=token, org_id=_ORG_ID, org_name=_ORG_NAME, hub_url=_US_HUB.url, hub_code=_US_HUB.code)
    return StoredCredentials(**{**defaults, **kwargs})


def _make_connector_cm():
    connector = mock.AsyncMock()
    connector.__aenter__ = mock.AsyncMock(return_value=connector)
    connector.__aexit__ = mock.AsyncMock(return_value=False)
    return connector


class TestInstanceList(unittest.TestCase):
    @mock.patch("evo.cli.instance.commands.load_selection")
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_list_marks_current_selection(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, mock_load_selection
    ):
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB, _AU_HUB), central=None)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])
        mock_load_selection.return_value = CurrentSelection(org_id=_ORG_ID, hub_code="au")

        result = runner.invoke(app, ["instance", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("US Hub", result.output)
        self.assertIn("AU Hub", result.output)
        au_line = next(line for line in result.output.splitlines() if "AU Hub" in line)
        self.assertIn("[current]", au_line)
        us_line = next(line for line in result.output.splitlines() if "US Hub" in line)
        self.assertNotIn("[current]", us_line)

    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_list_no_organizations(self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery):
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[])

        result = runner.invoke(app, ["instance", "list"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No Evo organizations found", result.output)

    @mock.patch("evo.cli._session.load_credentials", return_value=None)
    def test_list_not_logged_in(self, _mock):
        result = runner.invoke(app, ["instance", "list"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Not logged in", result.output)


class TestInstanceSelect(unittest.TestCase):
    @mock.patch("evo.cli.instance.commands.save_selection")
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_select_with_flags(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, mock_save_selection
    ):
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB, _AU_HUB), central=None)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])

        result = runner.invoke(app, ["instance", "select", "--org-id", str(_ORG_ID), "--hub-code", "au"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Selected", result.output)
        mock_save_selection.assert_called_once()
        saved: CurrentSelection = mock_save_selection.call_args.args[0]
        self.assertEqual(saved.org_id, _ORG_ID)
        self.assertEqual(saved.hub_code, "au")

    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_select_with_invalid_org_id(self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery):
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB,), central=None)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])

        other_org_id = UUID("99999999-9999-9999-9999-999999999999")
        result = runner.invoke(app, ["instance", "select", "--org-id", str(other_org_id), "--hub-code", "us"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("not found", result.output)

    @mock.patch("evo.cli.instance.commands.save_selection")
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_select_interactive_single_option_auto_selects(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, mock_save_selection
    ):
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB,), central=None)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])

        result = runner.invoke(app, ["instance", "select"])

        self.assertEqual(result.exit_code, 0, result.output)
        mock_save_selection.assert_called_once()
        saved: CurrentSelection = mock_save_selection.call_args.args[0]
        self.assertEqual(saved.hub_code, "us")

    @mock.patch("evo.cli.instance.commands.save_selection")
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_select_interactive_prompt(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, mock_save_selection
    ):
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB, _AU_HUB), central=None)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])

        result = runner.invoke(app, ["instance", "select"], input="2\n")

        self.assertEqual(result.exit_code, 0, result.output)
        saved: CurrentSelection = mock_save_selection.call_args.args[0]
        self.assertEqual(saved.hub_code, "au")


class TestInstanceStatus(unittest.TestCase):
    @mock.patch("evo.cli.instance.commands.load_selection", return_value=CurrentSelection())
    def test_status_no_selection(self, _mock):
        result = runner.invoke(app, ["instance", "status"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No organization/hub selected", result.output)

    @mock.patch("evo.cli.instance.commands.load_selection")
    def test_status_with_selection_no_workspace(self, mock_load: mock.Mock):
        mock_load.return_value = CurrentSelection(
            org_id=_ORG_ID, org_name=_ORG_NAME, hub_code="us", hub_url=_US_HUB.url, hub_display_name="US Hub"
        )
        result = runner.invoke(app, ["instance", "status"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn(_ORG_NAME, result.output)
        self.assertIn("No workspace selected", result.output)

    @mock.patch("evo.cli.instance.commands.load_selection")
    def test_status_with_workspace(self, mock_load: mock.Mock):
        workspace_id = UUID("11111111-2222-3333-4444-555555555555")
        mock_load.return_value = CurrentSelection(
            org_id=_ORG_ID,
            org_name=_ORG_NAME,
            hub_code="us",
            hub_url=_US_HUB.url,
            hub_display_name="US Hub",
            workspace_id=workspace_id,
            workspace_name="Exploration Model",
        )
        result = runner.invoke(app, ["instance", "status"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Exploration Model", result.output)


if __name__ == "__main__":
    unittest.main()
