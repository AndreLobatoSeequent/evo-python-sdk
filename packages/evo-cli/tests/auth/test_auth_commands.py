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
from evo.cli.config import CliConfig, load_config, save_config
from evo.cli.state import CurrentSelection
from evo.oauth.data import AccessToken

runner = CliRunner()

_ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_ORG_NAME = "ACME Mining"
_HUB_URL = "https://acme.api.seequent.com"


def _make_token(*, expires_in: int = 3600) -> AccessToken:
    return AccessToken(
        token_type="Bearer",
        access_token="access",
        refresh_token="refresh",
        expires_in=expires_in,
        issued_at=datetime.now(timezone.utc),
    )


def _make_creds(*, expires_in: int = 3600) -> StoredCredentials:
    return StoredCredentials(
        token=_make_token(expires_in=expires_in),
        org_id=_ORG_ID,
        org_name=_ORG_NAME,
        hub_url=_HUB_URL,
    )


def _configure(*, client_id: str = "client-id", redirect_uri: str = "http://localhost:8888/callback") -> None:
    save_config(CliConfig(client_id=client_id, redirect_uri=redirect_uri))


def _expired_creds() -> StoredCredentials:
    expired_token = AccessToken(
        token_type="Bearer",
        access_token="old",
        expires_in=1,
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    return StoredCredentials(token=expired_token, org_id=_ORG_ID, org_name=_ORG_NAME, hub_url=_HUB_URL)


# ---------------------------------------------------------------------------
# auth status — plain mode
# ---------------------------------------------------------------------------


class TestAuthStatus(unittest.TestCase):
    @mock.patch("evo.cli.auth.commands.load_credentials", return_value=None)
    def test_status_not_logged_in(self, _mock):
        result = runner.invoke(app, ["auth", "status"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Not logged in", result.output)

    @mock.patch("evo.cli.auth.commands.load_credentials")
    def test_status_expired_session(self, mock_load: mock.Mock):
        mock_load.return_value = _expired_creds()
        result = runner.invoke(app, ["auth", "status"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("expired", result.output.lower())

    @mock.patch("evo.cli.auth.commands.load_credentials")
    def test_status_logged_in(self, mock_load: mock.Mock):
        mock_load.return_value = _make_creds()
        result = runner.invoke(app, ["auth", "status"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn(_ORG_NAME, result.output)
        self.assertIn(_HUB_URL, result.output)


# ---------------------------------------------------------------------------
# auth status — json mode
# ---------------------------------------------------------------------------


class TestAuthStatusJson(unittest.TestCase):
    @mock.patch("evo.cli.auth.commands.load_credentials", return_value=None)
    def test_status_not_logged_in_json(self, _mock):
        result = runner.invoke(app, ["--format", "json", "auth", "status"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "not_logged_in")

    @mock.patch("evo.cli.auth.commands.load_credentials")
    def test_status_logged_in_json(self, mock_load: mock.Mock):
        mock_load.return_value = _make_creds()
        result = runner.invoke(app, ["--format", "json", "auth", "status"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "logged_in")
        self.assertEqual(data["org_name"], _ORG_NAME)
        self.assertEqual(data["hub_url"], _HUB_URL)
        self.assertIn("expires_at", data)

    @mock.patch("evo.cli.auth.commands.load_credentials")
    def test_status_expired_json(self, mock_load: mock.Mock):
        mock_load.return_value = _expired_creds()
        result = runner.invoke(app, ["--format", "json", "auth", "status"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "expired")


# ---------------------------------------------------------------------------
# auth logout
# ---------------------------------------------------------------------------


class TestAuthLogout(unittest.TestCase):
    @mock.patch("evo.cli.auth.commands.delete_credentials")
    def test_logout_calls_delete_and_confirms(self, mock_del: mock.Mock):
        result = runner.invoke(app, ["auth", "logout"])
        self.assertEqual(result.exit_code, 0)
        mock_del.assert_called_once()
        self.assertIn("Logged out", result.output)

    @mock.patch("evo.cli.auth.commands.delete_credentials")
    def test_logout_json(self, mock_del: mock.Mock):
        result = runner.invoke(app, ["--format", "json", "auth", "logout"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "logged_out")


# ---------------------------------------------------------------------------
# auth login
# ---------------------------------------------------------------------------


class TestAuthLogin(unittest.TestCase):
    @mock.patch("evo.cli.auth.commands.load_credentials")
    def test_login_skips_browser_when_already_authenticated(self, mock_load: mock.Mock):
        mock_load.return_value = _make_creds()
        result = runner.invoke(app, ["auth", "login"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Already logged in", result.output)

    @mock.patch("evo.cli.auth.commands.load_credentials")
    def test_login_already_authenticated_json(self, mock_load: mock.Mock):
        mock_load.return_value = _make_creds()
        result = runner.invoke(app, ["--format", "json", "auth", "login"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "already_logged_in")
        self.assertEqual(data["org_name"], _ORG_NAME)

    @mock.patch("evo.cli.auth.commands.save_selection")
    @mock.patch("evo.cli.auth.commands.load_selection")
    @mock.patch("evo.cli.auth.commands.save_credentials")
    @mock.patch("evo.cli.auth.commands.load_credentials", return_value=None)
    @mock.patch("evo.discovery.DiscoveryAPIClient")
    @mock.patch("evo.common.APIConnector")
    @mock.patch("evo.oauth.OAuthConnector")
    @mock.patch("evo.aio.transport.AioTransport")
    @mock.patch("evo.cli.auth.commands._CapturingAuthorizer")
    def test_login_with_single_org_and_hub_auto_selects(
        self,
        MockAuthorizer,
        MockTransport,
        MockOAuth,
        MockConnector,
        MockDiscovery,
        _mock_load,
        mock_save,
        mock_load_selection,
        mock_save_selection,
    ):
        _configure()

        mock_authorizer = MockAuthorizer.return_value
        mock_authorizer.login = mock.AsyncMock()
        mock_authorizer._captured_token = _make_token()

        mock_hub = mock.Mock()
        mock_hub.url = _HUB_URL
        mock_hub.display_name = "ACME Hub"
        mock_hub.code = "us"

        mock_org = mock.Mock()
        mock_org.id = _ORG_ID
        mock_org.display_name = _ORG_NAME
        mock_org.hubs = [mock_hub]

        mock_discovery_instance = mock.AsyncMock()
        mock_discovery_instance.list_organizations = mock.AsyncMock(return_value=[mock_org])
        MockDiscovery.return_value = mock_discovery_instance

        mock_connector_instance = mock.AsyncMock()
        mock_connector_instance.__aenter__ = mock.AsyncMock(return_value=mock_connector_instance)
        mock_connector_instance.__aexit__ = mock.AsyncMock(return_value=False)
        MockConnector.return_value = mock_connector_instance

        mock_load_selection.return_value = CurrentSelection()

        result = runner.invoke(app, ["auth", "login"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Logged in", result.output)
        mock_save.assert_called_once()
        saved: StoredCredentials = mock_save.call_args.args[0]
        self.assertEqual(saved.org_id, _ORG_ID)
        self.assertEqual(saved.hub_url, _HUB_URL)
        self.assertEqual(saved.hub_code, "us")
        mock_save_selection.assert_called_once()
        seeded: CurrentSelection = mock_save_selection.call_args.args[0]
        self.assertEqual(seeded.org_id, _ORG_ID)
        self.assertEqual(seeded.hub_code, "us")

    @mock.patch("evo.cli.auth.commands.load_credentials", return_value=None)
    def test_login_fails_without_client_id_configured(self, _mock):
        result = runner.invoke(app, ["auth", "login"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("evo auth configure", result.output)

    @mock.patch("evo.cli.auth.commands.save_credentials")
    @mock.patch("evo.cli.auth.commands.load_credentials", return_value=None)
    @mock.patch("evo.discovery.DiscoveryAPIClient")
    @mock.patch("evo.common.APIConnector")
    @mock.patch("evo.oauth.OAuthConnector")
    @mock.patch("evo.aio.transport.AioTransport")
    @mock.patch("evo.cli.auth.commands._CapturingAuthorizer")
    def test_login_uses_default_redirect_uri_when_not_configured(
        self,
        MockAuthorizer,
        MockTransport,
        MockOAuth,
        MockConnector,
        MockDiscovery,
        _mock_load,
        _mock_save,
    ):
        from evo.cli.config import DEFAULT_REDIRECT_URI

        save_config(CliConfig(client_id="client-id"))

        mock_authorizer = MockAuthorizer.return_value
        mock_authorizer.login = mock.AsyncMock()
        mock_authorizer._captured_token = _make_token()

        mock_hub = mock.Mock()
        mock_hub.url = _HUB_URL
        mock_hub.display_name = "ACME Hub"
        mock_hub.code = "us"
        mock_org = mock.Mock()
        mock_org.id = _ORG_ID
        mock_org.display_name = _ORG_NAME
        mock_org.hubs = [mock_hub]

        mock_discovery_instance = mock.AsyncMock()
        mock_discovery_instance.list_organizations = mock.AsyncMock(return_value=[mock_org])
        MockDiscovery.return_value = mock_discovery_instance

        mock_connector_instance = mock.AsyncMock()
        mock_connector_instance.__aenter__ = mock.AsyncMock(return_value=mock_connector_instance)
        mock_connector_instance.__aexit__ = mock.AsyncMock(return_value=False)
        MockConnector.return_value = mock_connector_instance

        result = runner.invoke(app, ["auth", "login"])

        self.assertEqual(result.exit_code, 0, result.output)
        MockAuthorizer.assert_called_once()
        self.assertEqual(MockAuthorizer.call_args.kwargs["redirect_url"], DEFAULT_REDIRECT_URI)

    @mock.patch("evo.cli.auth.commands.save_credentials")
    @mock.patch("evo.cli.auth.commands.load_credentials", return_value=None)
    @mock.patch("evo.discovery.DiscoveryAPIClient")
    @mock.patch("evo.common.APIConnector")
    @mock.patch("evo.oauth.OAuthConnector")
    @mock.patch("evo.aio.transport.AioTransport")
    @mock.patch("evo.cli.auth.commands._CapturingAuthorizer")
    def test_login_agent_mode_multiple_orgs_emits_structured_error(
        self,
        MockAuthorizer,
        MockTransport,
        MockOAuth,
        MockConnector,
        MockDiscovery,
        _mock_load,
        _mock_save,
    ):
        _configure()
        env = {"EVO_CLI_AGENT_MODE": "1"}

        mock_authorizer = MockAuthorizer.return_value
        mock_authorizer.login = mock.AsyncMock()
        mock_authorizer._captured_token = _make_token()

        def _make_mock_org(name, hub_url, hub_code, org_id):
            hub = mock.Mock()
            hub.url = hub_url
            hub.display_name = f"{name} Hub"
            hub.code = hub_code
            org = mock.Mock()
            org.id = org_id
            org.display_name = name
            org.hubs = [hub]
            return org

        mock_discovery_instance = mock.AsyncMock()
        mock_discovery_instance.list_organizations = mock.AsyncMock(
            return_value=[
                _make_mock_org(
                    "Org A", "https://a.api.seequent.com", "orga", UUID("aaaaaaaa-0000-0000-0000-000000000001")
                ),
                _make_mock_org(
                    "Org B", "https://b.api.seequent.com", "orgb", UUID("aaaaaaaa-0000-0000-0000-000000000002")
                ),
            ]
        )
        MockDiscovery.return_value = mock_discovery_instance

        mock_connector_instance = mock.AsyncMock()
        mock_connector_instance.__aenter__ = mock.AsyncMock(return_value=mock_connector_instance)
        mock_connector_instance.__aexit__ = mock.AsyncMock(return_value=False)
        MockConnector.return_value = mock_connector_instance

        result = runner.invoke(app, ["auth", "login"], env=env)

        self.assertNotEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["error"], "multiple_orgs")
        self.assertEqual(len(data["orgs"]), 2)


# ---------------------------------------------------------------------------
# auth configure
# ---------------------------------------------------------------------------


class TestAuthConfigure(unittest.TestCase):
    def test_show_when_unset(self):
        result = runner.invoke(app, ["auth", "configure", "--show"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("(not set)", result.output)
        self.assertIn("prod", result.output)

    def test_show_after_setting_client_id(self):
        _configure(client_id="abc123")
        result = runner.invoke(app, ["auth", "configure", "--show"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("abc123", result.output)

    @mock.patch("evo.cli.auth.commands.webbrowser.open")
    def test_no_args_prints_guidance_and_opens_browser(self, mock_open: mock.Mock):
        result = runner.invoke(app, ["auth", "configure"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("https://developer.seequent.com/docs/guides/getting-started/apps-and-tokens", result.output)
        self.assertIn("evo auth configure --client-id", result.output)
        mock_open.assert_called_once_with("https://developer.seequent.com/docs/guides/getting-started/apps-and-tokens")
        self.assertIsNone(load_config().client_id)

    @mock.patch("evo.cli.auth.commands.webbrowser.open")
    def test_no_args_agent_mode_does_not_open_browser(self, mock_open: mock.Mock):
        result = runner.invoke(app, ["auth", "configure"], env={"EVO_CLI_AGENT_MODE": "1"})
        self.assertEqual(result.exit_code, 0)
        mock_open.assert_not_called()
        data = json.loads(result.output)
        self.assertEqual(data["status"], "setup_required")
        self.assertIn("guide_url", data)

    def test_no_args_uses_qa_guide_when_qa_configured(self):
        save_config(CliConfig(env="qa"))
        result = runner.invoke(app, ["auth", "configure"], env={"EVO_CLI_AGENT_MODE": "1"})
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(
            data["guide_url"], "https://developer.int.seequent.com/docs/guides/getting-started/apps-and-tokens"
        )

    @mock.patch("evo.cli.auth.commands.webbrowser.open")
    def test_no_args_when_configured_shows_config_without_opening_browser(self, mock_open: mock.Mock):
        _configure(client_id="abc123")
        result = runner.invoke(app, ["auth", "configure"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("abc123", result.output)
        self.assertIn("--client-id", result.output)
        mock_open.assert_not_called()

    def test_sets_client_id(self):
        result = runner.invoke(app, ["auth", "configure", "--client-id", "my-id"])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(load_config().client_id, "my-id")
        self.assertIn("evo auth login", result.output)

    def test_sets_redirect_uri(self):
        result = runner.invoke(app, ["auth", "configure", "--redirect-uri", "http://localhost:1/cb"])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(load_config().redirect_uri, "http://localhost:1/cb")

    @mock.patch("evo.cli.auth.commands.delete_credentials")
    def test_switching_env_clears_credentials(self, mock_delete: mock.Mock):
        result = runner.invoke(app, ["auth", "configure", "--env", "qa"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(load_config().env, "qa")
        mock_delete.assert_called_once()
        self.assertIn("logged out", result.output.lower())

    @mock.patch("evo.cli.auth.commands.delete_credentials")
    def test_setting_same_env_does_not_clear_credentials(self, mock_delete: mock.Mock):
        result = runner.invoke(app, ["auth", "configure", "--env", "prod"])
        self.assertEqual(result.exit_code, 0, result.output)
        mock_delete.assert_not_called()

    def test_unknown_env_errors(self):
        result = runner.invoke(app, ["auth", "configure", "--env", "staging"])
        self.assertNotEqual(result.exit_code, 0)

    def test_env_flag_hidden_from_help(self):
        result = runner.invoke(app, ["auth", "configure", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--env", result.output)

    @mock.patch("evo.cli.auth.commands.delete_credentials")
    def test_reset_restores_defaults_and_clears_credentials(self, mock_delete: mock.Mock):
        _configure(client_id="abc123", redirect_uri="http://localhost:1/cb")
        save_config(CliConfig(client_id="abc123", redirect_uri="http://localhost:1/cb", env="qa"))

        result = runner.invoke(app, ["auth", "configure", "--reset"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(load_config(), CliConfig())
        mock_delete.assert_called_once()
        self.assertIn("reset", result.output.lower())
        self.assertIn("logged out", result.output.lower())

    def test_reset_combined_with_other_options_errors(self):
        result = runner.invoke(app, ["auth", "configure", "--reset", "--client-id", "abc"])
        self.assertNotEqual(result.exit_code, 0)


# ---------------------------------------------------------------------------
# output formatter
# ---------------------------------------------------------------------------


class TestOutputFormatter(unittest.TestCase):
    @mock.patch("evo.cli.auth.commands.load_credentials", return_value=None)
    def test_agent_mode_env_produces_json(self, _mock):
        result = runner.invoke(
            app,
            ["auth", "status"],
            env={"EVO_CLI_AGENT_MODE": "1"},
        )
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertIn("status", data)

    @mock.patch("evo.cli.auth.commands.load_credentials", return_value=None)
    def test_format_flag_overrides_agent_mode(self, _mock):
        result = runner.invoke(
            app,
            ["--format", "plain", "auth", "status"],
            env={"EVO_CLI_AGENT_MODE": "1"},
        )
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Not logged in", result.output)


if __name__ == "__main__":
    unittest.main()
