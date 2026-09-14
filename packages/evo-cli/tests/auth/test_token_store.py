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

import keyring.errors

from evo.oauth.data import AccessToken

from evo.cli.auth.token_store import (
    StoredCredentials,
    delete_credentials,
    load_credentials,
    save_credentials,
)

_ORG_ID = UUID("12345678-1234-5678-1234-567812345678")
_ORG_NAME = "Test Org"
_HUB_URL = "https://test.api.seequent.com"

def _make_token(*, expires_in: int = 3600, access_token: str = "test-token") -> AccessToken:
    return AccessToken(
        token_type="Bearer",
        access_token=access_token,
        refresh_token="test-refresh",
        expires_in=expires_in,
        issued_at=datetime.now(timezone.utc),
    )


def _make_creds(**kwargs) -> StoredCredentials:
    defaults = dict(token=_make_token(), org_id=_ORG_ID, org_name=_ORG_NAME, hub_url=_HUB_URL)
    return StoredCredentials(**{**defaults, **kwargs})


class TestStoredCredentialsSerialization(unittest.TestCase):
    def test_round_trip(self):
        creds = _make_creds()
        restored = StoredCredentials.from_json(creds.to_json())
        self.assertEqual(restored.org_id, creds.org_id)
        self.assertEqual(restored.org_name, creds.org_name)
        self.assertEqual(restored.hub_url, creds.hub_url)
        self.assertEqual(restored.token.access_token, creds.token.access_token)
        self.assertEqual(restored.token.refresh_token, creds.token.refresh_token)
        self.assertEqual(restored.token.expires_in, creds.token.expires_in)

    def test_json_contains_expected_keys(self):
        creds = _make_creds()
        data = json.loads(creds.to_json())
        self.assertIn("token", data)
        self.assertIn("org_id", data)
        self.assertIn("org_name", data)
        self.assertIn("hub_url", data)
        self.assertEqual(data["org_id"], str(_ORG_ID))


class TestSaveCredentials(unittest.TestCase):
    @mock.patch("evo.cli.auth.token_store.keyring.set_password")
    def test_calls_keyring_set_password(self, mock_set: mock.Mock):
        creds = _make_creds()
        save_credentials(creds)
        mock_set.assert_called_once()
        service, key, value = mock_set.call_args.args
        self.assertEqual(service, "seequent-evo-cli")
        self.assertEqual(key, "credentials")
        restored = StoredCredentials.from_json(value)
        self.assertEqual(restored.org_id, _ORG_ID)


class TestLoadCredentials(unittest.TestCase):
    @mock.patch("evo.cli.auth.token_store.keyring.get_password", return_value=None)
    def test_returns_none_when_no_credentials(self, _mock):
        self.assertIsNone(load_credentials())

    @mock.patch("evo.cli.auth.token_store.keyring.get_password")
    def test_returns_credentials_when_present(self, mock_get: mock.Mock):
        creds = _make_creds()
        mock_get.return_value = creds.to_json()
        loaded = load_credentials()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.org_id, _ORG_ID)
        self.assertEqual(loaded.hub_url, _HUB_URL)

    @mock.patch("evo.cli.auth.token_store.keyring.get_password", return_value="not-valid-json{{{")
    def test_returns_none_on_corrupt_data(self, _mock):
        self.assertIsNone(load_credentials())


class TestDeleteCredentials(unittest.TestCase):
    @mock.patch("evo.cli.auth.token_store.keyring.delete_password")
    def test_deletes_password(self, mock_del: mock.Mock):
        delete_credentials()
        mock_del.assert_called_once_with("seequent-evo-cli", "credentials")

    @mock.patch(
        "evo.cli.auth.token_store.keyring.delete_password",
        side_effect=keyring.errors.PasswordDeleteError,
    )
    def test_ignores_not_found_error(self, _mock):
        delete_credentials()  # should not raise


class TestTokenExpiry(unittest.TestCase):
    def test_valid_token_is_not_expired(self):
        token = _make_token(expires_in=3600)
        self.assertFalse(token.is_expired)

    def test_expired_token_is_detected(self):
        # expires_in=1 second, issued 2024 — already expired
        token = AccessToken(
            token_type="Bearer",
            access_token="old-token",
            expires_in=1,
            issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        self.assertTrue(token.is_expired)


if __name__ == "__main__":
    unittest.main()
