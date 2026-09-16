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

from evo.cli.auth.token_store import (
    StoredCredentials,
    delete_credentials,
    load_credentials,
    save_credentials,
)
from evo.oauth.data import AccessToken

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
        creds = _make_creds(hub_code="us")
        restored = StoredCredentials.from_json(creds.to_json())
        self.assertEqual(restored.org_id, creds.org_id)
        self.assertEqual(restored.org_name, creds.org_name)
        self.assertEqual(restored.hub_url, creds.hub_url)
        self.assertEqual(restored.hub_code, "us")
        self.assertEqual(restored.schema_version, 2)
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
        self.assertIn("hub_code", data)
        self.assertIn("schema_version", data)
        self.assertEqual(data["org_id"], str(_ORG_ID))

    def test_v1_payload_without_hub_code_migrates_gracefully(self):
        # Simulates credentials stored by a pre-hub_code version of the CLI.
        v1_data = {
            "token": json.loads(_make_token().model_dump_json(by_alias=True, exclude_unset=True)),
            "org_id": str(_ORG_ID),
            "org_name": _ORG_NAME,
            "hub_url": _HUB_URL,
        }
        restored = StoredCredentials.from_json(json.dumps(v1_data))
        self.assertEqual(restored.hub_code, "")
        self.assertEqual(restored.schema_version, 1)
        self.assertEqual(restored.org_id, _ORG_ID)


class TestSaveCredentials(unittest.TestCase):
    @mock.patch("evo.cli.auth.token_store.keyring.get_password", return_value=None)
    @mock.patch("evo.cli.auth.token_store.keyring.delete_password")
    @mock.patch("evo.cli.auth.token_store.keyring.set_password")
    def test_writes_chunked_payload_with_header(self, mock_set: mock.Mock, _mock_del, _mock_get):
        creds = _make_creds()
        save_credentials(creds)

        calls = {call.args[1]: call.args[2] for call in mock_set.call_args_list}
        self.assertIn("credentials", calls)
        num_chunks = int(calls["credentials"])
        self.assertGreaterEqual(num_chunks, 1)

        reassembled = "".join(calls[f"credentials/chunk/{i}"] for i in range(num_chunks))
        restored = StoredCredentials.from_json(reassembled)
        self.assertEqual(restored.org_id, _ORG_ID)

    @mock.patch("evo.cli.auth.token_store.keyring.get_password", return_value=None)
    @mock.patch("evo.cli.auth.token_store.keyring.delete_password")
    @mock.patch("evo.cli.auth.token_store.keyring.set_password")
    def test_large_token_is_split_into_multiple_chunks(self, mock_set: mock.Mock, _mock_del, _mock_get):
        # A single Windows Credential Manager entry caps out well below this size (see the
        # comment on _CHUNK_SIZE), so a realistically long JWT must span several chunks.
        creds = _make_creds(token=_make_token(access_token="x" * 3000))
        save_credentials(creds)

        num_chunks = int(next(call.args[2] for call in mock_set.call_args_list if call.args[1] == "credentials"))
        self.assertGreater(num_chunks, 1)

    @mock.patch("evo.cli.auth.token_store.keyring.get_password", return_value="2")
    @mock.patch("evo.cli.auth.token_store.keyring.delete_password")
    @mock.patch("evo.cli.auth.token_store.keyring.set_password")
    def test_clears_stale_chunks_from_a_previous_save(self, _mock_set, mock_del: mock.Mock, _mock_get):
        # Simulates a previous save that used 2 chunks; saving again should clear them first.
        save_credentials(_make_creds())
        deleted = {call.args[1] for call in mock_del.call_args_list}
        self.assertEqual(deleted, {"credentials", "credentials/chunk/0", "credentials/chunk/1"})


class TestLoadCredentials(unittest.TestCase):
    @mock.patch("evo.cli.auth.token_store.keyring.get_password", return_value=None)
    def test_returns_none_when_no_credentials(self, _mock):
        self.assertIsNone(load_credentials())

    @mock.patch("evo.cli.auth.token_store.keyring.get_password")
    def test_returns_credentials_from_chunked_storage(self, mock_get: mock.Mock):
        creds = _make_creds()
        data = creds.to_json()
        chunk_size = 10
        chunks = [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]

        def fake_get_password(_service, key):
            if key == "credentials":
                return str(len(chunks))
            index = int(key.rsplit("/", 1)[-1])
            return chunks[index]

        mock_get.side_effect = fake_get_password
        loaded = load_credentials()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.org_id, _ORG_ID)
        self.assertEqual(loaded.hub_url, _HUB_URL)

    @mock.patch("evo.cli.auth.token_store.keyring.get_password")
    def test_returns_credentials_from_legacy_unchunked_storage(self, mock_get: mock.Mock):
        # Credentials stored by a pre-chunking version of the CLI held the full JSON payload
        # directly under the header key, with no chunk count.
        creds = _make_creds()
        mock_get.return_value = creds.to_json()
        loaded = load_credentials()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.org_id, _ORG_ID)
        self.assertEqual(loaded.hub_url, _HUB_URL)

    @mock.patch("evo.cli.auth.token_store.keyring.get_password", return_value="not-valid-json{{{")
    def test_returns_none_on_corrupt_data(self, _mock):
        self.assertIsNone(load_credentials())

    @mock.patch("evo.cli.auth.token_store.keyring.get_password")
    def test_returns_none_when_a_chunk_is_missing(self, mock_get: mock.Mock):
        mock_get.side_effect = lambda _service, key: "2" if key == "credentials" else None
        self.assertIsNone(load_credentials())


class TestDeleteCredentials(unittest.TestCase):
    @mock.patch("evo.cli.auth.token_store.keyring.get_password", return_value=None)
    @mock.patch("evo.cli.auth.token_store.keyring.delete_password")
    def test_deletes_header_when_no_chunks_recorded(self, mock_del: mock.Mock, _mock_get):
        delete_credentials()
        mock_del.assert_called_once_with("seequent-evo-cli", "credentials")

    @mock.patch("evo.cli.auth.token_store.keyring.get_password", return_value="3")
    @mock.patch("evo.cli.auth.token_store.keyring.delete_password")
    def test_deletes_all_chunks_and_header(self, mock_del: mock.Mock, _mock_get):
        delete_credentials()
        deleted = {call.args[1] for call in mock_del.call_args_list}
        self.assertEqual(deleted, {"credentials", "credentials/chunk/0", "credentials/chunk/1", "credentials/chunk/2"})

    @mock.patch("evo.cli.auth.token_store.keyring.get_password", return_value=None)
    @mock.patch(
        "evo.cli.auth.token_store.keyring.delete_password",
        side_effect=keyring.errors.PasswordDeleteError,
    )
    def test_ignores_not_found_error(self, _mock_del, _mock_get):
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
