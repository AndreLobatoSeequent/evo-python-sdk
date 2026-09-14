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

import tempfile
import unittest
from pathlib import Path
from unittest import mock
from uuid import UUID

from evo.cli.state import CurrentSelection, clear_selection, load_selection, save_selection

_ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_WORKSPACE_ID = UUID("11111111-2222-3333-4444-555555555555")


class TestState(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._state_file = Path(self._tmpdir.name) / "cli-state.json"
        patcher = mock.patch("evo.cli.state._STATE_FILE", self._state_file)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmpdir.cleanup)

    def test_load_selection_missing_file_returns_default(self):
        selection = load_selection()
        self.assertEqual(selection, CurrentSelection())

    def test_round_trip(self):
        selection = CurrentSelection(
            org_id=_ORG_ID,
            org_name="ACME Mining",
            hub_code="us",
            hub_url="https://us.api.seequent.com",
            hub_display_name="US Hub",
            workspace_id=_WORKSPACE_ID,
            workspace_name="Exploration Model",
        )
        save_selection(selection)
        loaded = load_selection()
        self.assertEqual(loaded, selection)

    def test_load_selection_corrupt_file_returns_default(self):
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text("not-valid-json{{{")
        self.assertEqual(load_selection(), CurrentSelection())

    def test_clear_selection_removes_file(self):
        save_selection(CurrentSelection(org_id=_ORG_ID))
        self.assertTrue(self._state_file.exists())
        clear_selection()
        self.assertFalse(self._state_file.exists())

    def test_clear_selection_missing_file_does_not_raise(self):
        clear_selection()  # should not raise


if __name__ == "__main__":
    unittest.main()
