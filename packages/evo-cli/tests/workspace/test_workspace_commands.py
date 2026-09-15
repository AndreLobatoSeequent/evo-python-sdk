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
from evo.cli.state import CurrentSelection
from evo.common import Page
from evo.common.data import DependencyStatus, ServiceHealth, ServiceStatus, ServiceUser
from evo.common.exceptions import NotFoundException
from evo.oauth.data import AccessToken
from evo.workspaces import BasicWorkspace, Workspace, WorkspaceRole

runner = CliRunner()

_ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_HUB_URL = "https://us.api.seequent.com"
_WORKSPACE_ID = UUID("11111111-2222-3333-4444-555555555555")
_USER = ServiceUser(id=UUID("22222222-2222-2222-2222-222222222222"), name="Jane Doe", email="jane@acme.com")


def _make_creds(**kwargs) -> StoredCredentials:
    token = AccessToken(
        token_type="Bearer", access_token="access", expires_in=3600, issued_at=datetime.now(timezone.utc)
    )
    defaults = dict(token=token, org_id=_ORG_ID, org_name="ACME Mining", hub_url=_HUB_URL, hub_code="us")
    return StoredCredentials(**{**defaults, **kwargs})


def _make_workspace(**kwargs) -> Workspace:
    defaults = dict(
        id=_WORKSPACE_ID,
        display_name="Exploration Model",
        description="Q3 exploration model",
        user_role=WorkspaceRole.editor,
        org_id=_ORG_ID,
        hub_url=_HUB_URL,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        created_by=_USER,
        updated_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        updated_by=_USER,
        labels=["geology", "q3"],
    )
    return Workspace(**{**defaults, **kwargs})


def _make_connector_cm():
    connector = mock.AsyncMock()
    connector.__aenter__ = mock.AsyncMock(return_value=connector)
    connector.__aexit__ = mock.AsyncMock(return_value=False)
    return connector


class TestWorkspaceList(unittest.TestCase):
    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_list_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        page = Page(offset=0, limit=50, total=1, items=[_make_workspace()])
        MockClient.return_value.list_workspaces = mock.AsyncMock(return_value=page)

        result = runner.invoke(app, ["workspace", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Exploration Model", result.output)
        self.assertIn(str(_WORKSPACE_ID), result.output)

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_list_all_uses_list_all_workspaces(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.list_all_workspaces = mock.AsyncMock(return_value=[_make_workspace()])

        result = runner.invoke(app, ["workspace", "list", "--all"])

        self.assertEqual(result.exit_code, 0, result.output)
        MockClient.return_value.list_all_workspaces.assert_called_once()
        self.assertIn("Exploration Model", result.output)

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_list_empty(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        page = Page(offset=0, limit=50, total=0, items=[])
        MockClient.return_value.list_workspaces = mock.AsyncMock(return_value=page)

        result = runner.invoke(app, ["workspace", "list"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("No workspaces found", result.output)

    @mock.patch("evo.cli._connector.load_credentials", return_value=None)
    def test_list_not_logged_in(self, _mock):
        result = runner.invoke(app, ["workspace", "list"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("not_logged_in", result.output)

    def test_list_org_id_and_hub_code_must_be_given_together(self):
        # No mocking needed: this should fail before any network call is made.
        with mock.patch("evo.cli.workspace.commands.require_login", return_value=_make_creds()):
            result = runner.invoke(app, ["workspace", "list", "--org-id", str(_ORG_ID)])
        self.assertNotEqual(result.exit_code, 0)


class TestWorkspaceGet(unittest.TestCase):
    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_get_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.get_workspace = mock.AsyncMock(return_value=_make_workspace())

        result = runner.invoke(app, ["workspace", "get", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Exploration Model", result.output)
        self.assertIn("Q3 exploration model", result.output)
        self.assertIn("geology, q3", result.output)

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_get_not_found(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.get_workspace = mock.AsyncMock(
            side_effect=NotFoundException(status=404, reason="Not Found", content=None, headers=None)
        )

        result = runner.invoke(app, ["workspace", "get", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("not found", result.output)


class TestWorkspaceHealth(unittest.TestCase):
    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_health_healthy(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        health = ServiceHealth(
            service="workspace",
            status_code=200,
            status=ServiceStatus.HEALTHY,
            version="2026.9.1",
            dependencies={"postgres": DependencyStatus.HEALTHY},
        )
        MockClient.return_value.get_service_health = mock.AsyncMock(return_value=health)

        result = runner.invoke(app, ["workspace", "health"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("pass", result.output)
        self.assertIn("2026.9.1", result.output)

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_health_unhealthy_exits_nonzero(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        health = ServiceHealth(
            service="workspace", status_code=503, status=ServiceStatus.UNHEALTHY, version="2026.9.1", dependencies=None
        )
        MockClient.return_value.get_service_health = mock.AsyncMock(return_value=health)

        result = runner.invoke(app, ["workspace", "health"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("fail", result.output)

    def test_health_invalid_check_type(self):
        with mock.patch("evo.cli.workspace.commands.require_login", return_value=_make_creds()):
            result = runner.invoke(app, ["workspace", "health", "--check-type", "bogus"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("invalid --check-type", result.output)


class TestWorkspaceSelect(unittest.TestCase):
    @mock.patch("evo.cli.workspace.commands.save_selection")
    @mock.patch("evo.cli.workspace.commands.load_selection", return_value=CurrentSelection())
    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_select_happy_path(self, _req, _res, mock_build_connector, MockClient, _mock_load, mock_save):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.get_workspace = mock.AsyncMock(return_value=_make_workspace())

        result = runner.invoke(app, ["workspace", "select", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        mock_save.assert_called_once()
        saved: CurrentSelection = mock_save.call_args.args[0]
        self.assertEqual(saved.workspace_id, _WORKSPACE_ID)
        self.assertEqual(saved.workspace_name, "Exploration Model")

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_select_not_found(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.get_workspace = mock.AsyncMock(
            side_effect=NotFoundException(status=404, reason="Not Found", content=None, headers=None)
        )

        result = runner.invoke(app, ["workspace", "select", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("not found", result.output)


class TestWorkspaceCreate(unittest.TestCase):
    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_create_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        created = _make_workspace(display_name="New Workspace", description="A test workspace", labels=["geology"])
        MockClient.return_value.create_workspace = mock.AsyncMock(return_value=created)

        result = runner.invoke(
            app, ["workspace", "create", "New Workspace", "--description", "A test workspace", "--labels", "geology"]
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Created workspace: New Workspace", result.output)
        self.assertIn("A test workspace", result.output)
        self.assertIn("geology", result.output)
        MockClient.return_value.create_workspace.assert_called_once_with(
            name="New Workspace",
            description="A test workspace",
            labels=["geology"],
            default_coordinate_system=None,
            bounding_box_coordinates=None,
        )

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_create_without_optional_flags(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.create_workspace = mock.AsyncMock(return_value=_make_workspace())

        result = runner.invoke(app, ["workspace", "create", "Exploration Model"])

        self.assertEqual(result.exit_code, 0, result.output)
        MockClient.return_value.create_workspace.assert_called_once_with(
            name="Exploration Model",
            description=None,
            labels=None,
            default_coordinate_system=None,
            bounding_box_coordinates=None,
        )

    @mock.patch("evo.cli._connector.load_credentials", return_value=None)
    def test_create_not_logged_in(self, _mock):
        result = runner.invoke(app, ["workspace", "create", "New Workspace"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("not_logged_in", result.output)


class TestWorkspaceJson(unittest.TestCase):
    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_list_json(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        page = Page(offset=0, limit=50, total=1, items=[_make_workspace()])
        MockClient.return_value.list_workspaces = mock.AsyncMock(return_value=page)

        result = runner.invoke(app, ["--format", "json", "workspace", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(len(data["workspaces"]), 1)
        self.assertEqual(data["workspaces"][0]["id"], str(_WORKSPACE_ID))
        self.assertEqual(data["workspaces"][0]["display_name"], "Exploration Model")

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_get_json(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.get_workspace = mock.AsyncMock(return_value=_make_workspace())

        result = runner.invoke(app, ["--format", "json", "workspace", "get", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["id"], str(_WORKSPACE_ID))
        self.assertEqual(data["labels"], ["geology", "q3"])

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_get_not_found_json(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.get_workspace = mock.AsyncMock(
            side_effect=NotFoundException(status=404, reason="Not Found", content=None, headers=None)
        )

        result = runner.invoke(app, ["--format", "json", "workspace", "get", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 1)
        data = json.loads(result.output)
        self.assertIn("not found", data["error"])

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_health_json(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        health = ServiceHealth(
            service="workspace",
            status_code=200,
            status=ServiceStatus.HEALTHY,
            version="2026.9.1",
            dependencies={"postgres": DependencyStatus.HEALTHY},
        )
        MockClient.return_value.get_service_health = mock.AsyncMock(return_value=health)

        result = runner.invoke(app, ["--format", "json", "workspace", "health"])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "pass")
        self.assertEqual(data["dependencies"], {"postgres": "pass"})

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_health_unhealthy_json_still_emits_data(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        health = ServiceHealth(
            service="workspace", status_code=503, status=ServiceStatus.UNHEALTHY, version="2026.9.1", dependencies=None
        )
        MockClient.return_value.get_service_health = mock.AsyncMock(return_value=health)

        result = runner.invoke(app, ["--format", "json", "workspace", "health"])

        self.assertEqual(result.exit_code, 1)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "fail")

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_create_json(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        created = _make_workspace(display_name="New Workspace", description="A test workspace", labels=["geology"])
        MockClient.return_value.create_workspace = mock.AsyncMock(return_value=created)

        result = runner.invoke(app, ["--format", "json", "workspace", "create", "New Workspace"])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["display_name"], "New Workspace")
        self.assertEqual(data["labels"], ["geology"])

    @mock.patch("evo.cli.workspace.commands.save_selection")
    @mock.patch("evo.cli.workspace.commands.load_selection", return_value=CurrentSelection())
    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_select_json(self, _req, _res, mock_build_connector, MockClient, _mock_load, _mock_save):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.get_workspace = mock.AsyncMock(return_value=_make_workspace())

        result = runner.invoke(app, ["--format", "json", "workspace", "select", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["id"], str(_WORKSPACE_ID))

    @mock.patch("evo.cli._connector.load_credentials", return_value=None)
    def test_list_not_logged_in_json(self, _mock):
        result = runner.invoke(app, ["--format", "json", "workspace", "list"])
        self.assertNotEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["error"], "not_logged_in")

    def test_health_invalid_check_type_json(self):
        with mock.patch("evo.cli.workspace.commands.require_login", return_value=_make_creds()):
            result = runner.invoke(app, ["--format", "json", "workspace", "health", "--check-type", "bogus"])
        self.assertNotEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertIn("invalid --check-type", data["error"])


class TestWorkspaceListSummary(unittest.TestCase):
    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_summary_uses_summary_endpoint(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        basic = BasicWorkspace(id=_WORKSPACE_ID, display_name="Exploration Model")
        page = Page(offset=0, limit=50, total=1, items=[basic])
        MockClient.return_value.list_workspaces_summary = mock.AsyncMock(return_value=page)

        result = runner.invoke(app, ["workspace", "list", "--summary"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("summary", result.output)
        self.assertIn("Exploration Model", result.output)
        MockClient.return_value.list_workspaces_summary.assert_called_once()

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_summary_json(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        basic = BasicWorkspace(id=_WORKSPACE_ID, display_name="Exploration Model")
        page = Page(offset=0, limit=50, total=1, items=[basic])
        MockClient.return_value.list_workspaces_summary = mock.AsyncMock(return_value=page)

        result = runner.invoke(app, ["--format", "json", "workspace", "list", "--summary"])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["workspaces"], [{"id": str(_WORKSPACE_ID), "display_name": "Exploration Model"}])


class TestBoundingBoxRoundTrip(unittest.TestCase):
    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_create_parses_bounding_box_and_coordinate_system(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.create_workspace = mock.AsyncMock(return_value=_make_workspace())

        result = runner.invoke(
            app,
            [
                "workspace",
                "create",
                "New Workspace",
                "--default-coordinate-system",
                "EPSG:2134",
                "--bounding-box",
                "0,0;10,0;10,10;0,10",
            ],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        MockClient.return_value.create_workspace.assert_called_once_with(
            name="New Workspace",
            description=None,
            labels=None,
            default_coordinate_system="EPSG:2134",
            bounding_box_coordinates=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
        )

    def test_create_invalid_bounding_box_errors(self):
        with mock.patch("evo.cli.workspace.commands.require_login", return_value=_make_creds()):
            result = runner.invoke(app, ["workspace", "create", "X", "--bounding-box", "not-a-coordinate"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Invalid --bounding-box", result.output)

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_get_displays_bounding_box_and_coordinate_system(self, _req, _res, mock_build_connector, MockClient):
        from evo.workspaces import BoundingBox, Coordinate

        mock_build_connector.return_value = _make_connector_cm()
        bbox = BoundingBox(
            coordinates=[[Coordinate(latitude=0.0, longitude=0.0), Coordinate(latitude=10.0, longitude=10.0)]],
            type="Polygon",
        )
        ws = _make_workspace(default_coordinate_system="EPSG:2134", bounding_box=bbox)
        MockClient.return_value.get_workspace = mock.AsyncMock(return_value=ws)

        result = runner.invoke(app, ["workspace", "get", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("EPSG:2134", result.output)
        self.assertIn("0.0", result.output)
        self.assertIn("10.0", result.output)


class TestWorkspaceUpdate(unittest.TestCase):
    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_update_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        updated = _make_workspace(display_name="Renamed", description="New description")
        MockClient.return_value.update_workspace = mock.AsyncMock(return_value=updated)

        result = runner.invoke(
            app,
            [
                "workspace",
                "update",
                str(_WORKSPACE_ID),
                "--name",
                "Renamed",
                "--description",
                "New description",
            ],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Updated workspace: Renamed", result.output)
        MockClient.return_value.update_workspace.assert_called_once_with(
            _WORKSPACE_ID,
            name="Renamed",
            description="New description",
            labels=None,
            default_coordinate_system=None,
            bounding_box_coordinates=None,
        )

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_update_not_found(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.update_workspace = mock.AsyncMock(
            side_effect=NotFoundException(status=404, reason="Not Found", content=None, headers=None)
        )

        result = runner.invoke(app, ["workspace", "update", str(_WORKSPACE_ID), "--name", "X"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("not found", result.output)


class TestWorkspaceDelete(unittest.TestCase):
    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_delete_with_yes_skips_confirmation(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.delete_workspace = mock.AsyncMock(return_value=None)

        result = runner.invoke(app, ["workspace", "delete", str(_WORKSPACE_ID), "--yes"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Deleted workspace", result.output)
        MockClient.return_value.delete_workspace.assert_called_once_with(_WORKSPACE_ID)

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_delete_not_found(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.delete_workspace = mock.AsyncMock(
            side_effect=NotFoundException(status=404, reason="Not Found", content=None, headers=None)
        )

        result = runner.invoke(app, ["workspace", "delete", str(_WORKSPACE_ID), "--yes"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("not found", result.output)

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_delete_agent_mode_skips_confirmation_prompt(self, _req, _res, mock_build_connector, MockClient):
        # In agent mode (EVO_CLI_AGENT_MODE=1), output.is_interactive() is False, so the CLI must
        # not block on a confirmation prompt even without --yes.
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.delete_workspace = mock.AsyncMock(return_value=None)

        result = runner.invoke(
            app, ["workspace", "delete", str(_WORKSPACE_ID)], env={"EVO_CLI_AGENT_MODE": "1"}
        )

        self.assertEqual(result.exit_code, 0, result.output)
        MockClient.return_value.delete_workspace.assert_called_once_with(_WORKSPACE_ID)


class TestWorkspaceRestore(unittest.TestCase):
    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_restore_happy_path(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.restore_deleted_workspace = mock.AsyncMock(return_value=None)

        result = runner.invoke(app, ["workspace", "restore", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Restored workspace", result.output)
        MockClient.return_value.restore_deleted_workspace.assert_called_once_with(_WORKSPACE_ID)

    @mock.patch("evo.cli.workspace.commands.WorkspaceAPIClient")
    @mock.patch("evo.cli.workspace.commands.build_connector")
    @mock.patch("evo.cli.workspace.commands.resolve_org_and_hub", return_value=(_ORG_ID, "us", _HUB_URL))
    @mock.patch("evo.cli.workspace.commands.require_login", new_callable=mock.AsyncMock, return_value=_make_creds())
    def test_restore_not_found(self, _req, _res, mock_build_connector, MockClient):
        mock_build_connector.return_value = _make_connector_cm()
        MockClient.return_value.restore_deleted_workspace = mock.AsyncMock(
            side_effect=NotFoundException(status=404, reason="Not Found", content=None, headers=None)
        )

        result = runner.invoke(app, ["workspace", "restore", str(_WORKSPACE_ID)])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("not found", result.output)


if __name__ == "__main__":
    unittest.main()
