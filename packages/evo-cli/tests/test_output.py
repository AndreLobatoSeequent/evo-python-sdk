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
from io import StringIO
from unittest import mock

import typer

from evo.cli import output
from evo.cli.output import OutputFormat


def _reset():
    output._format = OutputFormat.plain
    output._interactive = True


class TestOutputInit(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_defaults_to_plain_and_interactive(self):
        output.init()
        self.assertEqual(output.current_format(), OutputFormat.plain)
        self.assertTrue(output.is_interactive())

    def test_format_flag_sets_json(self):
        output.init(OutputFormat.json)
        self.assertEqual(output.current_format(), OutputFormat.json)
        self.assertTrue(output.is_interactive())  # format alone doesn't disable interactivity

    def test_agent_mode_env_sets_json_and_non_interactive(self):
        with mock.patch.dict("os.environ", {"EVO_CLI_AGENT_MODE": "1"}):
            output.init()
        self.assertEqual(output.current_format(), OutputFormat.json)
        self.assertFalse(output.is_interactive())

    def test_format_flag_overrides_agent_mode_format(self):
        with mock.patch.dict("os.environ", {"EVO_CLI_AGENT_MODE": "1"}):
            output.init(OutputFormat.plain)
        self.assertEqual(output.current_format(), OutputFormat.plain)
        self.assertFalse(output.is_interactive())  # still non-interactive

    def test_agent_mode_true_string_variants(self):
        for value in ("true", "True", "TRUE", "yes", "1"):
            with self.subTest(value=value):
                with mock.patch.dict("os.environ", {"EVO_CLI_AGENT_MODE": value}):
                    output.init()
                self.assertFalse(output.is_interactive())
                _reset()

    def test_agent_mode_false_string_variants(self):
        for value in ("0", "false", "no", ""):
            with self.subTest(value=value):
                with mock.patch.dict("os.environ", {"EVO_CLI_AGENT_MODE": value}):
                    output.init()
                self.assertTrue(output.is_interactive())
                _reset()


class TestOutputEmit(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_plain_mode_emits_plain_text(self):
        output.init(OutputFormat.plain)
        with mock.patch("typer.echo") as mock_echo:
            output.emit({"key": "val"}, plain="hello")
            mock_echo.assert_called_once_with("hello")

    def test_plain_mode_falls_back_to_str(self):
        output.init(OutputFormat.plain)
        with mock.patch("typer.echo") as mock_echo:
            output.emit({"key": "val"})
            mock_echo.assert_called_once_with("{'key': 'val'}")

    def test_json_mode_serialises_data(self):
        output.init(OutputFormat.json)
        with mock.patch("typer.echo") as mock_echo:
            output.emit({"status": "ok"}, plain="ignored")
            call_arg = mock_echo.call_args.args[0]
            parsed = json.loads(call_arg)
            self.assertEqual(parsed["status"], "ok")

    def test_json_mode_with_none_data_emits_empty_object(self):
        output.init(OutputFormat.json)
        with mock.patch("typer.echo") as mock_echo:
            output.emit()
            call_arg = mock_echo.call_args.args[0]
            self.assertEqual(json.loads(call_arg), {})


class TestOutputEmitError(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_plain_error_goes_to_stderr(self):
        output.init(OutputFormat.plain)
        with mock.patch("typer.echo") as mock_echo:
            with self.assertRaises(typer.Exit):
                output.emit_error("something went wrong")
            mock_echo.assert_called_once()
            _, kwargs = mock_echo.call_args
            self.assertTrue(kwargs.get("err"))

    def test_json_error_is_valid_json_on_stderr(self):
        output.init(OutputFormat.json)
        import sys
        with mock.patch("typer.echo") as mock_echo:
            with self.assertRaises(typer.Exit):
                output.emit_error("bad input", field="x")
            call_args = mock_echo.call_args
            payload = json.loads(call_args.args[0])
            self.assertEqual(payload["error"], "bad input")
            self.assertEqual(payload["field"], "x")
            self.assertEqual(call_args.kwargs.get("file"), sys.stderr)

    def test_emit_error_exits_with_code_1_by_default(self):
        output.init(OutputFormat.plain)
        with mock.patch("typer.echo"):
            with self.assertRaises(typer.Exit) as ctx:
                output.emit_error("oops")
            self.assertEqual(ctx.exception.exit_code, 1)

    def test_emit_error_custom_exit_code(self):
        output.init(OutputFormat.plain)
        with mock.patch("typer.echo"):
            with self.assertRaises(typer.Exit) as ctx:
                output.emit_error("oops", exit_code=2)
            self.assertEqual(ctx.exception.exit_code, 2)


if __name__ == "__main__":
    unittest.main()
