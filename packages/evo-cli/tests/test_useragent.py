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

"""Unit tests for agent detection and user-agent generation."""

import os
from unittest import mock

import pytest

from evo.cli.useragent import AgentInfo, detect_agent_info, get_user_agent, is_agent_mode


def _clear_agent_env_vars() -> None:
    """Clear all agent-related environment variables."""
    # Clear agent detectors
    for var in [
        "CLAUDECODE",
        "CLAUDE_CODE",
        "CURSOR_AGENT",
        "CURSOR",
        "CLINE",
        "GITHUB_COPILOT",
        "GH_COPILOT",
        "AMAZON_Q",
        "AWS_Q",
        "GEMINI_CODE",
        "AIDER",
        "CODEX",
        "WINDSURF",
        "CODY",
        "DEVIN_SESSION_ID",
    ]:
        os.environ.pop(var, None)

    # Clear control flags
    for var in ["EVO_FORCE_AGENT_MODE", "EVO_NO_AGENT_MODE", "EVO_CLI_AGENT_MODE"]:
        os.environ.pop(var, None)


class TestAgentDetection:
    """Test auto-detection of AI agents."""

    def test_no_agent_detected_by_default(self) -> None:
        """Test that no agent is detected when no env vars are set."""
        with mock.patch.dict(os.environ, clear=True):
            info = detect_agent_info()
            assert not info.detected
            assert info.name == ""
            assert info.user_agent_suffix == ""

    def test_claude_code_detection_uppercase(self) -> None:
        """Test detection of Claude Code with uppercase env var."""
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}, clear=True):
            info = detect_agent_info()
            assert info.detected
            assert info.name == "claude-code"
            assert info.user_agent_suffix == "(agent=claude-code)"

    def test_claude_code_detection_lowercase(self) -> None:
        """Test detection of Claude Code with lowercase env var."""
        with mock.patch.dict(os.environ, {"CLAUDE_CODE": "true"}, clear=True):
            info = detect_agent_info()
            assert info.detected
            assert info.name == "claude-code"
            assert info.user_agent_suffix == "(agent=claude-code)"

    def test_cursor_detection(self) -> None:
        """Test detection of Cursor."""
        with mock.patch.dict(os.environ, {"CURSOR_AGENT": "1"}, clear=True):
            info = detect_agent_info()
            assert info.detected
            assert info.name == "cursor"
            assert info.user_agent_suffix == "(agent=cursor)"

    def test_cline_detection(self) -> None:
        """Test detection of Cline."""
        with mock.patch.dict(os.environ, {"CLINE": "1"}, clear=True):
            info = detect_agent_info()
            assert info.detected
            assert info.name == "cline"

    def test_github_copilot_detection(self) -> None:
        """Test detection of GitHub Copilot."""
        with mock.patch.dict(os.environ, {"GITHUB_COPILOT": "1"}, clear=True):
            info = detect_agent_info()
            assert info.detected
            assert info.name == "github-copilot"

    def test_amazon_q_detection(self) -> None:
        """Test detection of Amazon Q."""
        with mock.patch.dict(os.environ, {"AMAZON_Q": "1"}, clear=True):
            info = detect_agent_info()
            assert info.detected
            assert info.name == "amazon-q"

    def test_gemini_code_detection(self) -> None:
        """Test detection of Gemini Code."""
        with mock.patch.dict(os.environ, {"GEMINI_CODE": "1"}, clear=True):
            info = detect_agent_info()
            assert info.detected
            assert info.name == "gemini-code"

    def test_devin_detection_via_session_id(self) -> None:
        """Test detection of Devin via DEVIN_SESSION_ID."""
        with mock.patch.dict(os.environ, {"DEVIN_SESSION_ID": "abc123"}, clear=True):
            info = detect_agent_info()
            assert info.detected
            assert info.name == "devin"

    def test_priority_order_when_multiple_agents(self) -> None:
        """Test that first agent in detector list is returned when multiple are set."""
        env = {
            "CLAUDE_CODE": "1",  # First in detector list
            "CURSOR_AGENT": "1",  # Second
            "CLINE": "1",  # Third
        }
        with mock.patch.dict(os.environ, env, clear=True):
            info = detect_agent_info()
            assert info.name == "claude-code"  # Should be the first match

    def test_devin_takes_precedence_in_detection(self) -> None:
        """Test that Devin is checked first (before other detectors)."""
        env = {
            "DEVIN_SESSION_ID": "session123",
            "CLAUDE_CODE": "1",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            info = detect_agent_info()
            assert info.name == "devin"

    def test_env_var_case_insensitive(self) -> None:
        """Test that env var values are case-insensitive."""
        test_values = ["1", "true", "True", "TRUE", "yes", "YES"]
        for value in test_values:
            with mock.patch.dict(os.environ, {"CLAUDE_CODE": value}, clear=True):
                info = detect_agent_info()
                assert info.detected, f"Should detect with value={value}"

    def test_env_var_false_not_detected(self) -> None:
        """Test that 'false' or other non-truthy values don't trigger detection."""
        for value in ["0", "false", "False", "no", ""]:
            with mock.patch.dict(os.environ, {"CLAUDE_CODE": value}, clear=True):
                info = detect_agent_info()
                assert not info.detected, f"Should not detect with value={value!r}"


class TestAgentModePriority:
    """Test is_agent_mode() priority resolution."""

    def test_default_no_agent_mode(self) -> None:
        """Test default behavior with no env vars set."""
        with mock.patch.dict(os.environ, clear=True):
            assert not is_agent_mode()

    def test_force_agent_mode_priority_1(self) -> None:
        """Test that EVO_FORCE_AGENT_MODE=1 enables agent mode (priority 1)."""
        with mock.patch.dict(os.environ, {"EVO_FORCE_AGENT_MODE": "1"}, clear=True):
            assert is_agent_mode()

    def test_force_agent_mode_overrides_all(self) -> None:
        """Test that EVO_FORCE_AGENT_MODE=1 overrides everything including NO flag."""
        env = {"EVO_FORCE_AGENT_MODE": "1", "EVO_NO_AGENT_MODE": "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert is_agent_mode()

    def test_no_agent_mode_priority_2(self) -> None:
        """Test that EVO_NO_AGENT_MODE=1 disables agent mode (priority 2)."""
        with mock.patch.dict(os.environ, {"EVO_NO_AGENT_MODE": "1"}, clear=True):
            assert not is_agent_mode()

    def test_no_agent_mode_overrides_legacy_and_detection(self) -> None:
        """Test that NO flag overrides EVO_CLI_AGENT_MODE and auto-detection."""
        env = {
            "EVO_NO_AGENT_MODE": "1",
            "EVO_CLI_AGENT_MODE": "1",
            "CLAUDE_CODE": "1",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            assert not is_agent_mode()

    def test_legacy_agent_mode_priority_3(self) -> None:
        """Test that EVO_CLI_AGENT_MODE=1 enables agent mode (priority 3, backward compat)."""
        with mock.patch.dict(os.environ, {"EVO_CLI_AGENT_MODE": "1"}, clear=True):
            assert is_agent_mode()

    def test_legacy_agent_mode_overridden_by_no_flag(self) -> None:
        """Test that NO flag overrides legacy agent mode."""
        env = {"EVO_CLI_AGENT_MODE": "1", "EVO_NO_AGENT_MODE": "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert not is_agent_mode()

    def test_auto_detection_priority_4(self) -> None:
        """Test that auto-detection enables agent mode when no force flags set."""
        with mock.patch.dict(os.environ, {"CLAUDE_CODE": "1"}, clear=True):
            assert is_agent_mode()

    def test_auto_detection_disabled_by_no_flag(self) -> None:
        """Test that NO flag disables auto-detection."""
        env = {"CLAUDE_CODE": "1", "EVO_NO_AGENT_MODE": "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert not is_agent_mode()

    def test_priority_resolution_full_chain(self) -> None:
        """Test full priority chain with all levels."""
        # Priority 1: FORCE wins
        with mock.patch.dict(os.environ, {"EVO_FORCE_AGENT_MODE": "1"}, clear=True):
            assert is_agent_mode()

        # Priority 2: NO wins over LEGACY
        env = {"EVO_NO_AGENT_MODE": "1", "EVO_CLI_AGENT_MODE": "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert not is_agent_mode()

        # Priority 3: LEGACY wins over AUTO
        env = {"EVO_CLI_AGENT_MODE": "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert is_agent_mode()

        # Priority 4: AUTO wins when no FORCE/NO/LEGACY
        with mock.patch.dict(os.environ, {"CLAUDE_CODE": "1"}, clear=True):
            assert is_agent_mode()

        # Priority 5: DEFAULT is False
        with mock.patch.dict(os.environ, clear=True):
            assert not is_agent_mode()


class TestUserAgent:
    """Test user-agent string generation."""

    def test_base_user_agent_without_agent(self) -> None:
        """Test base user-agent string when no agent is detected."""
        with mock.patch.dict(os.environ, clear=True):
            ua = get_user_agent()
            assert ua == "evo-cli/0.1.0"

    def test_user_agent_with_claude_code(self) -> None:
        """Test user-agent string with Claude Code detected."""
        with mock.patch.dict(os.environ, {"CLAUDE_CODE": "1"}, clear=True):
            ua = get_user_agent()
            assert ua == "evo-cli/0.1.0 (agent=claude-code)"

    def test_user_agent_with_cursor(self) -> None:
        """Test user-agent string with Cursor detected."""
        with mock.patch.dict(os.environ, {"CURSOR_AGENT": "1"}, clear=True):
            ua = get_user_agent()
            assert ua == "evo-cli/0.1.0 (agent=cursor)"

    def test_user_agent_with_github_copilot(self) -> None:
        """Test user-agent string with GitHub Copilot detected."""
        with mock.patch.dict(os.environ, {"GITHUB_COPILOT": "1"}, clear=True):
            ua = get_user_agent()
            assert ua == "evo-cli/0.1.0 (agent=github-copilot)"

    def test_user_agent_with_devin(self) -> None:
        """Test user-agent string with Devin detected."""
        with mock.patch.dict(os.environ, {"DEVIN_SESSION_ID": "xyz"}, clear=True):
            ua = get_user_agent()
            assert ua == "evo-cli/0.1.0 (agent=devin)"

    def test_user_agent_format_is_http_compliant(self) -> None:
        """Test that user-agent format follows HTTP standards."""
        with mock.patch.dict(os.environ, {"CLAUDE_CODE": "1"}, clear=True):
            ua = get_user_agent()
            # Should be: product/version (comment)
            parts = ua.split(" ")
            assert len(parts) == 2
            assert parts[0] == "evo-cli/0.1.0"
            assert parts[1].startswith("(")
            assert parts[1].endswith(")")


class TestBackwardCompatibility:
    """Test backward compatibility with existing behavior."""

    def test_legacy_env_var_still_works(self) -> None:
        """Test that EVO_CLI_AGENT_MODE still works (backward compat)."""
        with mock.patch.dict(os.environ, {"EVO_CLI_AGENT_MODE": "1"}, clear=True):
            assert is_agent_mode()

    def test_legacy_env_var_can_be_disabled(self) -> None:
        """Test that legacy env var can be disabled with NO flag."""
        env = {"EVO_CLI_AGENT_MODE": "1", "EVO_NO_AGENT_MODE": "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert not is_agent_mode()

    def test_all_agent_detectors_work_independently(self) -> None:
        """Test that each agent detector works as expected."""
        agents = [
            ("CLAUDECODE", "claude-code"),
            ("CLAUDE_CODE", "claude-code"),
            ("CURSOR_AGENT", "cursor"),
            ("CURSOR", "cursor"),
            ("CLINE", "cline"),
            ("GITHUB_COPILOT", "github-copilot"),
            ("GH_COPILOT", "github-copilot"),
            ("AMAZON_Q", "amazon-q"),
            ("AWS_Q", "amazon-q"),
            ("GEMINI_CODE", "gemini-code"),
            ("AIDER", "aider"),
            ("CODEX", "codex"),
            ("WINDSURF", "windsurf"),
            ("CODY", "sourcegraph-cody"),
        ]
        for env_var, agent_name in agents:
            with mock.patch.dict(os.environ, {env_var: "1"}, clear=True):
                info = detect_agent_info()
                assert info.detected, f"Failed to detect with {env_var}"
                assert info.name == agent_name, f"Wrong name for {env_var}"
