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

import pytest
import typer

from evo.cli import output


class TestEmitErrorWithSuggestions:
    """Test emit_error() with suggestions parameter."""

    def test_plain_mode_with_suggestion(self, capsys, monkeypatch) -> None:
        """Test that plain mode shows suggestion in 'Did you mean' format."""
        output.init(output.OutputFormat.plain)

        with pytest.raises(typer.Exit):
            output.emit_error(
                "Unknown command 'blockmodell'",
                code="unknown_command",
                suggestions=["blockmodels"],
            )

        captured = capsys.readouterr()
        assert "Error: Unknown command 'blockmodell'" in captured.err
        assert "Did you mean: blockmodels?" in captured.err

    def test_plain_mode_without_suggestion(self, capsys) -> None:
        """Test that plain mode without suggestion shows no suggestion line."""
        output.init(output.OutputFormat.plain)

        with pytest.raises(typer.Exit):
            output.emit_error("Some error")

        captured = capsys.readouterr()
        assert "Error: Some error" in captured.err
        assert "Did you mean" not in captured.err

    def test_json_mode_with_suggestion(self, capsys) -> None:
        """Test that JSON mode includes suggestions field."""
        output.init(output.OutputFormat.json)

        with pytest.raises(typer.Exit):
            output.emit_error(
                "Unknown command 'blockmodell'",
                code="unknown_command",
                suggestions=["blockmodels"],
            )

        captured = capsys.readouterr()
        data = json.loads(captured.err)
        assert data["error"] == "Unknown command 'blockmodell'"
        assert data["code"] == "unknown_command"
        assert data["suggestions"] == ["blockmodels"]

    def test_json_mode_without_suggestion(self, capsys) -> None:
        """Test that JSON mode omits suggestions field when empty."""
        output.init(output.OutputFormat.json)

        with pytest.raises(typer.Exit):
            output.emit_error("Some error", code="test_code")

        captured = capsys.readouterr()
        data = json.loads(captured.err)
        assert data["error"] == "Some error"
        assert data["code"] == "test_code"
        assert "suggestions" not in data

    def test_multiple_suggestions_shows_first(self, capsys) -> None:
        """Test that multiple suggestions shows only the first in plain mode."""
        output.init(output.OutputFormat.plain)

        with pytest.raises(typer.Exit):
            output.emit_error(
                "Unknown option '--fmt'",
                code="unknown_option",
                suggestions=["--format", "--from"],
            )

        captured = capsys.readouterr()
        # Should show first suggestion
        assert "Did you mean: --format?" in captured.err

    def test_code_exit_with_suggestions(self, capsys) -> None:
        """Test that exit code is properly resolved when suggestions are present."""
        output.init(output.OutputFormat.plain)

        with pytest.raises(typer.Exit) as exc_info:
            output.emit_error(
                "not_found",
                code="not_found",
                suggestions=["blockmodels"],
            )

        # not_found should map to exit code 4
        assert exc_info.value.exit_code == 4
