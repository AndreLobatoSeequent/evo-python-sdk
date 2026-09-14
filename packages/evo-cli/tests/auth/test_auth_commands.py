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


def _expired_creds() -> StoredCredentials:
    expired_token = AccessToken(
        token_type="Bearer",
        access_token="old",
        expires_in=1,
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    return StoredCredentials(token=expired_token, org_id=_ORG_ID, org_name=_ORG_NAME, hub_url=_HUB_URL)


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


class TestAuthLogout(unittest.TestCase):
    @mock.patch("evo.cli.auth.commands.delete_credentials")
    def test_logout_calls_delete_and_confirms(self, mock_del: mock.Mock):
        result = runner.invoke(app, ["auth", "logout"])
        self.assertEqual(result.exit_code, 0)
        mock_del.assert_called_once()
        self.assertIn("Logged out", result.output)


class TestAuthLogin(unittest.TestCase):
    @mock.patch("evo.cli.auth.commands.load_credentials")
    def test_login_skips_browser_when_already_authenticated(self, mock_load: mock.Mock):
        mock_load.return_value = _make_creds()
        result = runner.invoke(app, ["auth", "login"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Already logged in", result.output)

    @mock.patch("evo.cli.auth.commands.save_credentials")
    @mock.patch("evo.cli.auth.commands.load_credentials", return_value=None)
    @mock.patch("evo.cli.auth.commands.DiscoveryAPIClient")
    @mock.patch("evo.cli.auth.commands.APIConnector")
    @mock.patch("evo.cli.auth.commands.OAuthConnector")
    @mock.patch("evo.cli.auth.commands.AioTransport")
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
    ):
        env = {"EVO_CLIENT_ID": "client-id", "EVO_REDIRECT_URI": "http://localhost:8888/callback"}

        mock_authorizer = MockAuthorizer.return_value
        mock_authorizer.login = mock.AsyncMock()
        mock_authorizer._captured_token = _make_token()

        mock_hub = mock.Mock()
        mock_hub.url = _HUB_URL
        mock_hub.display_name = "ACME Hub"

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

        result = runner.invoke(app, ["auth", "login"], env=env)

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Logged in", result.output)
        mock_save.assert_called_once()
        saved: StoredCredentials = mock_save.call_args.args[0]
        self.assertEqual(saved.org_id, _ORG_ID)
        self.assertEqual(saved.hub_url, _HUB_URL)

    def test_login_fails_without_client_id_env(self):
        result = runner.invoke(app, ["auth", "login"], env={"EVO_CLIENT_ID": "", "EVO_REDIRECT_URI": ""})
        self.assertNotEqual(result.exit_code, 0)

    @mock.patch("evo.cli.auth.commands.load_credentials", return_value=None)
    def test_login_fails_when_redirect_uri_missing(self, _mock):
        result = runner.invoke(app, ["auth", "login"], env={"EVO_CLIENT_ID": "id", "EVO_REDIRECT_URI": ""})
        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
