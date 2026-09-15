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
from uuid import UUID

import typer

from evo.cli._session import resolve_org_and_hub
from evo.cli.auth.token_store import StoredCredentials
from evo.cli.state import CurrentSelection
from evo.oauth.data import AccessToken

_STATE_ORG_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_STATE_HUB_URL = "https://state.api.seequent.com"
_CREDS_ORG_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_CREDS_HUB_URL = "https://creds.api.seequent.com"
_FLAG_ORG_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_FLAG_HUB_URL = "https://flag.api.seequent.com"


def _creds() -> StoredCredentials:
    token = AccessToken(
        token_type="Bearer", access_token="access", expires_in=3600, issued_at=datetime.now(timezone.utc)
    )
    return StoredCredentials(
        token=token, org_id=_CREDS_ORG_ID, org_name="Creds Org", hub_url=_CREDS_HUB_URL, hub_code="creds-hub"
    )


def _selection() -> CurrentSelection:
    return CurrentSelection(org_id=_STATE_ORG_ID, hub_code="state-hub", hub_url=_STATE_HUB_URL)


class TestResolveOrgAndHub(unittest.TestCase):
    def test_state_file_selection_wins_over_credentials(self):
        org_id, hub_code, hub_url = resolve_org_and_hub(None, None, _creds(), _selection())
        self.assertEqual(org_id, _STATE_ORG_ID)
        self.assertEqual(hub_code, "state-hub")
        self.assertEqual(hub_url, _STATE_HUB_URL)

    def test_credentials_used_when_no_state_selection(self):
        org_id, hub_code, hub_url = resolve_org_and_hub(None, None, _creds(), CurrentSelection())
        self.assertEqual(org_id, _CREDS_ORG_ID)
        self.assertEqual(hub_code, "creds-hub")
        self.assertEqual(hub_url, _CREDS_HUB_URL)

    def test_explicit_flags_override_state_selection_when_matching_credentials(self):
        # The flags match what's in stored credentials, so they should resolve even though
        # the persisted selection points elsewhere.
        org_id, hub_code, hub_url = resolve_org_and_hub(_CREDS_ORG_ID, "creds-hub", _creds(), _selection())
        self.assertEqual(org_id, _CREDS_ORG_ID)
        self.assertEqual(hub_code, "creds-hub")
        self.assertEqual(hub_url, _CREDS_HUB_URL)

    def test_explicit_flags_override_state_selection_when_matching_it(self):
        org_id, _hub_code, hub_url = resolve_org_and_hub(_STATE_ORG_ID, "state-hub", _creds(), _selection())
        self.assertEqual(org_id, _STATE_ORG_ID)
        self.assertEqual(hub_url, _STATE_HUB_URL)

    def test_explicit_flags_not_matching_any_cached_source_errors(self):
        with self.assertRaises(typer.Exit):
            resolve_org_and_hub(_FLAG_ORG_ID, "unknown-hub", _creds(), _selection())

    def test_only_org_id_flag_without_hub_code_errors(self):
        with self.assertRaises(typer.Exit):
            resolve_org_and_hub(_FLAG_ORG_ID, None, _creds(), _selection())

    def test_no_selection_and_no_credentials_hub_errors(self):
        empty_creds = StoredCredentials(
            token=_creds().token, org_id=_CREDS_ORG_ID, org_name="Creds Org", hub_url="", hub_code=""
        )
        with self.assertRaises(typer.Exit):
            resolve_org_and_hub(None, None, empty_creds, CurrentSelection())


if __name__ == "__main__":
    unittest.main()
