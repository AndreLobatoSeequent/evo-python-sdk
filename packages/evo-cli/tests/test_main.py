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

import sys
import unittest
from unittest import mock

from evo.cli import __version__
from evo.cli.__main__ import _handle_version


class TestHandleVersion(unittest.TestCase):
    def test_version_flag_prints_version_and_exits(self):
        original_argv = sys.argv.copy()
        try:
            sys.argv = ["evo", "--version"]
            with mock.patch("typer.echo") as mock_echo:
                with self.assertRaises(SystemExit) as ctx:
                    _handle_version()
                mock_echo.assert_called_once_with(f"evo {__version__}")
                self.assertEqual(ctx.exception.code, 0)
        finally:
            sys.argv = original_argv

    def test_version_flag_not_present_does_nothing(self):
        original_argv = sys.argv.copy()
        try:
            sys.argv = ["evo", "auth", "login"]
            with mock.patch("typer.echo") as mock_echo:
                _handle_version()
                mock_echo.assert_not_called()
        finally:
            sys.argv = original_argv

    def test_version_flag_with_subcommand(self):
        original_argv = sys.argv.copy()
        try:
            sys.argv = ["evo", "blockmodels", "--version"]
            with mock.patch("typer.echo") as mock_echo:
                with self.assertRaises(SystemExit) as ctx:
                    _handle_version()
                mock_echo.assert_called_once_with(f"evo {__version__}")
                self.assertEqual(ctx.exception.code, 0)
        finally:
            sys.argv = original_argv


if __name__ == "__main__":
    unittest.main()
