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

from evo.cli._connector import require_credentials
from evo.cli.auth.token_store import StoredCredentials
from evo.oauth.data import AccessToken

_ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_HUB_URL = "https://us.api.seequent.com"


def _make_token(*, expires_in: int = 3600, refresh_token: str | None = "refresh-token") -> AccessToken:
    return AccessToken(
        token_type="Bearer",
        access_token="access",
        refresh_token=refresh_token,
        expires_in=expires_in,
        issued_at=datetime.now(timezone.utc),
    )


def _expired_token() -> AccessToken:
    # A fixed past issued_at, unlike expires_in=1 with issued_at=now(), is unambiguously expired
    # regardless of how much wall-clock time the test takes to reach the assertion.
    return AccessToken(
        token_type="Bearer",
        access_token="access",
        refresh_token="refresh-token",
        expires_in=1,
        issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _expired_creds(**kwargs) -> StoredCredentials:
    expired_token = _expired_token()
    defaults = dict(
        token=expired_token,
        org_id=_ORG_ID,
        org_name="ACME Mining",
        hub_url=_HUB_URL,
        hub_code="us",
        client_id="client-id",
        ims_url="https://ims.example.com",
    )
    return StoredCredentials(**{**defaults, **kwargs})


class TestRequireCredentialsNotConfigured(unittest.IsolatedAsyncioTestCase):
    @mock.patch("evo.cli._connector.get_client_id", return_value=None)
    @mock.patch("evo.cli._connector.load_credentials", return_value=None)
    async def test_missing_client_id_reports_not_configured(self, _mock_load, _mock_client_id):
        import io
        from contextlib import redirect_stderr

        from evo.cli import output

        output.init()
        buf = io.StringIO()
        with self.assertRaises(Exception), redirect_stderr(buf):
            await require_credentials()
        self.assertIn("not_configured", buf.getvalue())

    @mock.patch("evo.cli._connector.get_client_id", return_value="client-id")
    @mock.patch("evo.cli._connector.load_credentials", return_value=None)
    async def test_configured_but_not_logged_in_reports_not_logged_in(self, _mock_load, _mock_client_id):
        import io
        from contextlib import redirect_stderr

        from evo.cli import output

        output.init()
        buf = io.StringIO()
        with self.assertRaises(Exception), redirect_stderr(buf):
            await require_credentials()
        self.assertIn("not_logged_in", buf.getvalue())
        self.assertNotIn("not_configured", buf.getvalue())


class TestRequireCredentialsRefresh(unittest.IsolatedAsyncioTestCase):
    @mock.patch("evo.cli._connector.save_credentials")
    @mock.patch("evo.cli._connector.OAuthConnector")
    @mock.patch("evo.cli._connector.load_credentials")
    async def test_refresh_preserves_hub_code(self, mock_load, MockOAuthConnector, mock_save):
        # Regression test: a silent refresh must not drop hub_code, or _session.resolve_org_and_hub's
        # fallback to stored credentials (when no state-file selection exists) would break.
        expired = _expired_creds()
        mock_load.return_value = expired

        mock_connector_instance = mock.AsyncMock()
        mock_connector_instance.__aenter__ = mock.AsyncMock(return_value=mock_connector_instance)
        mock_connector_instance.__aexit__ = mock.AsyncMock(return_value=False)
        mock_connector_instance.fetch_token = mock.AsyncMock(return_value=_make_token(expires_in=3600))
        MockOAuthConnector.return_value = mock_connector_instance

        result = await require_credentials()

        self.assertEqual(result.hub_code, "us")
        mock_save.assert_called_once()
        saved: StoredCredentials = mock_save.call_args.args[0]
        self.assertEqual(saved.hub_code, "us")
        self.assertEqual(saved.hub_url, _HUB_URL)
        self.assertEqual(saved.client_id, "client-id")

    @mock.patch("evo.cli._connector.load_credentials")
    async def test_no_refresh_token_falls_through_to_session_expired_error(self, mock_load):
        from evo.cli import output

        expired = _expired_creds(client_id="", ims_url="")
        mock_load.return_value = expired

        output.init()
        with self.assertRaises(Exception):
            await require_credentials()


if __name__ == "__main__":
    unittest.main()
