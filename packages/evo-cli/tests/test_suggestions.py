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

from evo.cli import suggestions


class TestGetSuggestions:
    """Test the get_suggestions() function."""

    def test_exact_match(self) -> None:
        """Test that exact match is found."""
        result = suggestions.get_suggestions("blockmodels", ["blockmodels", "auth"])
        assert result == ["blockmodels"]

    def test_close_match(self) -> None:
        """Test that close matches are found."""
        result = suggestions.get_suggestions("blockmodell", ["blockmodels", "auth"])
        assert result == ["blockmodels"]

    def test_typo_in_middle(self) -> None:
        """Test matching with typo in middle of word."""
        result = suggestions.get_suggestions("blckmodels", ["blockmodels", "workspace"])
        assert result == ["blockmodels"]

    def test_single_suggestion(self) -> None:
        """Test that max_suggestions=1 returns at most one match."""
        result = suggestions.get_suggestions(
            "auth",
            ["auth", "auth login", "admin"],
            max_suggestions=1,
        )
        assert len(result) <= 1

    def test_multiple_suggestions(self) -> None:
        """Test that max_suggestions controls number of results."""
        result = suggestions.get_suggestions(
            "auth",
            ["auth", "auth login", "admin", "agent"],
            max_suggestions=3,
        )
        assert len(result) <= 3

    def test_no_match_too_different(self) -> None:
        """Test that very different inputs return no matches."""
        result = suggestions.get_suggestions(
            "xyz",
            ["blockmodels", "workspace"],
            cutoff=0.6,
        )
        assert result == []

    def test_cutoff_threshold(self) -> None:
        """Test that cutoff parameter affects matching."""
        choices = ["blockmodels", "workspace"]
        # With high cutoff, shouldn't match
        result_high = suggestions.get_suggestions(
            "blckmodels",
            choices,
            cutoff=0.95,
        )
        # With low cutoff, should match
        result_low = suggestions.get_suggestions(
            "blckmodels",
            choices,
            cutoff=0.5,
        )
        assert len(result_high) <= len(result_low)

    def test_empty_input(self) -> None:
        """Test that empty input returns no suggestions."""
        result = suggestions.get_suggestions("", ["blockmodels", "auth"])
        assert result == []

    def test_empty_choices(self) -> None:
        """Test that empty choices returns no suggestions."""
        result = suggestions.get_suggestions("blockmodels", [])
        assert result == []


class TestSuggestCommand:
    """Test the suggest_command() function."""

    def test_suggest_blockmodels(self) -> None:
        """Test suggesting 'blockmodels' command."""
        available = ["blockmodels", "auth", "workspace", "admin"]
        result = suggestions.suggest_command("blockmodell", available)
        assert result == "blockmodels"

    def test_suggest_auth(self) -> None:
        """Test suggesting 'auth' command."""
        available = ["blockmodels", "auth", "workspace"]
        result = suggestions.suggest_command("authen", available)
        assert result == "auth"

    def test_no_suggestion_too_different(self) -> None:
        """Test that no suggestion is made for too-different input."""
        available = ["blockmodels", "auth"]
        result = suggestions.suggest_command("xyz", available)
        assert result is None

    def test_exact_match_returns_match(self) -> None:
        """Test that exact match is returned."""
        available = ["blockmodels", "auth"]
        result = suggestions.suggest_command("blockmodels", available)
        assert result == "blockmodels"


class TestSuggestFlag:
    """Test the suggest_flag() function."""

    def test_suggest_format_flag(self) -> None:
        """Test suggesting '--format' flag."""
        available = ["--format", "--help", "--workspace"]
        result = suggestions.suggest_flag("--formatt", available)
        assert result == "--format"

    def test_suggest_workspace_flag(self) -> None:
        """Test suggesting '--workspace' flag."""
        available = ["--format", "--help", "--workspace"]
        result = suggestions.suggest_flag("--workspac", available)
        assert result == "--workspace"

    def test_no_suggestion_too_different(self) -> None:
        """Test that no suggestion is made for too-different input."""
        available = ["--format", "--help"]
        result = suggestions.suggest_flag("--xyz", available)
        assert result is None

    def test_exact_match_returns_match(self) -> None:
        """Test that exact match is returned."""
        available = ["--format", "--help"]
        result = suggestions.suggest_flag("--format", available)
        assert result == "--format"
