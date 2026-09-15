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
from evo.cli.config import EvoEnvironment
from evo.cli.state import CurrentSelection
from evo.discovery import CentralInstance, Hub, Organization
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
    @mock.patch("evo.cli.instance.commands.load_selection", return_value=CurrentSelection())
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_select_with_flags(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, _mock_load_selection, mock_save_selection
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
    @mock.patch("evo.cli.instance.commands.load_selection", return_value=CurrentSelection())
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_select_interactive_single_option_auto_selects(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, _mock_load_selection, mock_save_selection
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
    @mock.patch("evo.cli.instance.commands.load_selection", return_value=CurrentSelection())
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_select_interactive_prompt(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, _mock_load_selection, mock_save_selection
    ):
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB, _AU_HUB), central=None)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])

        result = runner.invoke(app, ["instance", "select"], input="2\n")

        self.assertEqual(result.exit_code, 0, result.output)
        saved: CurrentSelection = mock_save_selection.call_args.args[0]
        self.assertEqual(saved.hub_code, "au")

    @mock.patch("evo.cli.instance.commands.save_selection")
    @mock.patch("evo.cli.instance.commands.load_selection")
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_select_same_org_and_hub_preserves_workspace_selection(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, mock_load_selection, mock_save_selection
    ):
        workspace_id = UUID("11111111-2222-3333-4444-555555555555")
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB,), central=None)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])
        mock_load_selection.return_value = CurrentSelection(
            org_id=_ORG_ID, hub_code="us", workspace_id=workspace_id, workspace_name="Existing Workspace"
        )

        result = runner.invoke(app, ["instance", "select", "--org-id", str(_ORG_ID), "--hub-code", "us"])

        self.assertEqual(result.exit_code, 0, result.output)
        saved: CurrentSelection = mock_save_selection.call_args.args[0]
        self.assertEqual(saved.workspace_id, workspace_id)
        self.assertEqual(saved.workspace_name, "Existing Workspace")

    @mock.patch("evo.cli.instance.commands.save_selection")
    @mock.patch("evo.cli.instance.commands.load_selection")
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_select_different_hub_clears_workspace_selection(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, mock_load_selection, mock_save_selection
    ):
        workspace_id = UUID("11111111-2222-3333-4444-555555555555")
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB, _AU_HUB), central=None)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])
        mock_load_selection.return_value = CurrentSelection(
            org_id=_ORG_ID, hub_code="us", workspace_id=workspace_id, workspace_name="Existing Workspace"
        )

        result = runner.invoke(app, ["instance", "select", "--org-id", str(_ORG_ID), "--hub-code", "au"])

        self.assertEqual(result.exit_code, 0, result.output)
        saved: CurrentSelection = mock_save_selection.call_args.args[0]
        self.assertIsNone(saved.workspace_id)
        self.assertIsNone(saved.workspace_name)


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


class TestInstanceJson(unittest.TestCase):
    @mock.patch("evo.cli.instance.commands.load_selection")
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_list_json(self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, mock_load_selection):
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB, _AU_HUB), central=None)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])
        mock_load_selection.return_value = CurrentSelection(org_id=_ORG_ID, hub_code="au")

        result = runner.invoke(app, ["--format", "json", "instance", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(len(data["organizations"]), 1)
        hubs = data["organizations"][0]["hubs"]
        self.assertEqual({h["hub_code"]: h["current"] for h in hubs}, {"us": False, "au": True})

    @mock.patch("evo.cli.instance.commands.save_selection")
    @mock.patch("evo.cli.instance.commands.load_selection", return_value=CurrentSelection())
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_select_json(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, _mock_load_selection, _mock_save
    ):
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB, _AU_HUB), central=None)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])

        result = runner.invoke(
            app, ["--format", "json", "instance", "select", "--org-id", str(_ORG_ID), "--hub-code", "au"]
        )

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["org_id"], str(_ORG_ID))
        self.assertEqual(data["hub_code"], "au")

    @mock.patch("evo.cli.instance.commands.load_selection", return_value=CurrentSelection())
    def test_status_json_no_selection(self, _mock):
        result = runner.invoke(app, ["--format", "json", "instance", "status"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertIsNone(data["org_id"])

    @mock.patch("evo.cli._session.load_credentials", return_value=None)
    def test_list_not_logged_in_json(self, _mock):
        result = runner.invoke(app, ["--format", "json", "instance", "list"])
        self.assertNotEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertIn("Not logged in", data["error"])

    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_select_with_invalid_org_id_json(self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery):
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB,), central=None)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])

        other_org_id = UUID("99999999-9999-9999-9999-999999999999")
        result = runner.invoke(
            app, ["--format", "json", "instance", "select", "--org-id", str(other_org_id), "--hub-code", "us"]
        )

        self.assertNotEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertIn("not found", data["error"])
        self.assertEqual(data["org_id"], str(other_org_id))


class TestInstanceCentral(unittest.TestCase):
    @mock.patch("evo.cli.instance.commands.load_selection")
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_list_surfaces_central_instance(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, mock_load_selection
    ):
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        central = CentralInstance(
            id=UUID("33333333-3333-3333-3333-333333333333"),
            display_name="ACME Central",
            name="acme-central",
            host="acme.central.seequent.com",
            organization_name=_ORG_NAME,
        )
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB,), central=central)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])
        mock_load_selection.return_value = CurrentSelection()

        result = runner.invoke(app, ["instance", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("ACME Central", result.output)
        self.assertIn("acme.central.seequent.com", result.output)

    @mock.patch("evo.cli.instance.commands.load_selection")
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_list_central_json(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, mock_load_selection
    ):
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        central = CentralInstance(
            id=UUID("33333333-3333-3333-3333-333333333333"),
            display_name="ACME Central",
            name="acme-central",
            host="acme.central.seequent.com",
            organization_name=_ORG_NAME,
        )
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB,), central=central)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])
        mock_load_selection.return_value = CurrentSelection()

        result = runner.invoke(app, ["--format", "json", "instance", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(
            data["organizations"][0]["central"],
            {"id": "33333333-3333-3333-3333-333333333333", "display_name": "ACME Central", "host": "acme.central.seequent.com"},
        )

    @mock.patch("evo.cli.instance.commands.load_selection")
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_list_no_central_instance_is_none(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery, mock_load_selection
    ):
        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        org = Organization(id=_ORG_ID, display_name=_ORG_NAME, hubs=(_US_HUB,), central=None)
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(return_value=[org])
        mock_load_selection.return_value = CurrentSelection()

        result = runner.invoke(app, ["--format", "json", "instance", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertIsNone(data["organizations"][0]["central"])


class TestInstanceDiscoveryErrorHandling(unittest.TestCase):
    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_list_unauthorized_discovery_call_emits_clean_error(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery
    ):
        from evo.common.exceptions import UnauthorizedException

        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(
            side_effect=UnauthorizedException(status=401, reason="Unauthorized", content=None, headers=None)
        )

        result = runner.invoke(app, ["instance", "list"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Access denied", result.output)

    @mock.patch("evo.cli.instance.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.instance.commands.build_connector")
    @mock.patch("evo.cli.instance.commands.get_environment", return_value=_TEST_ENV)
    @mock.patch("evo.cli.instance.commands.require_login")
    def test_select_unauthorized_discovery_call_emits_clean_error(
        self, mock_require_login, _mock_env, mock_build_connector, MockDiscovery
    ):
        from evo.common.exceptions import UnauthorizedException

        mock_require_login.return_value = _make_creds()
        mock_build_connector.return_value = _make_connector_cm()
        MockDiscovery.return_value.list_organizations = mock.AsyncMock(
            side_effect=UnauthorizedException(status=401, reason="Unauthorized", content=None, headers=None)
        )

        result = runner.invoke(app, ["instance", "select"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Access denied", result.output)


if __name__ == "__main__":
    unittest.main()
