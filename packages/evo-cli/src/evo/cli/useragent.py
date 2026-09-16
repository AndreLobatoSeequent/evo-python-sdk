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

"""Agent detection and user-agent string generation.

This module provides automatic detection of AI coding assistants (Claude Code,
Cursor, Cline, GitHub Copilot, etc.) via environment variables, with priority-
based resolution for force flags and legacy environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import NamedTuple


class AgentDetector(NamedTuple):
    """Mapping of an AI agent to its environment variable markers."""

    name: str
    env_vars: list[str]


# Table-driven agent detection, checked in priority order.
# Each agent is identified by specific environment variables that are set
# by the agent when spawning evo-cli as a subprocess.
_AGENT_DETECTORS = [
    AgentDetector("claude-code", ["CLAUDECODE", "CLAUDE_CODE"]),
    AgentDetector("cursor", ["CURSOR_AGENT", "CURSOR"]),
    AgentDetector("cline", ["CLINE"]),
    AgentDetector("github-copilot", ["GITHUB_COPILOT", "GH_COPILOT"]),
    AgentDetector("amazon-q", ["AMAZON_Q", "AWS_Q"]),
    AgentDetector("gemini-code", ["GEMINI_CODE"]),
    AgentDetector("aider", ["AIDER"]),
    AgentDetector("codex", ["CODEX"]),
    AgentDetector("windsurf", ["WINDSURF"]),
    AgentDetector("sourcegraph-cody", ["CODY"]),
]


@dataclass
class AgentInfo:
    """Detected agent information.

    Attributes:
        name: Name of detected agent (e.g. "claude-code"), or empty string if not detected
        detected: Whether an agent was detected
        user_agent_suffix: String to append to user-agent (empty or "(agent=...)")
    """

    name: str
    detected: bool
    user_agent_suffix: str


def _is_env_truthy(key: str) -> bool:
    """Check if environment variable is set to a truthy value."""
    value = os.environ.get(key, "").lower()
    return value in ("1", "true", "yes")


def _is_env_present(key: str) -> bool:
    """Check if environment variable is set and non-empty."""
    return bool(os.environ.get(key))


def detect_agent_info() -> AgentInfo:
    """Auto-detect running AI agent via environment variables.

    Checks Devin (by session ID) first, then iterates through AGENT_DETECTORS
    in priority order, returning the first match.

    Returns:
        AgentInfo with detected agent name, detection status, and user-agent suffix
    """
    # Devin is detected via DEVIN_SESSION_ID rather than a boolean flag
    if _is_env_present("DEVIN_SESSION_ID"):
        return AgentInfo(
            name="devin",
            detected=True,
            user_agent_suffix="(agent=devin)",
        )

    # Check each known agent in priority order
    for detector in _AGENT_DETECTORS:
        for env_var in detector.env_vars:
            if _is_env_truthy(env_var):
                return AgentInfo(
                    name=detector.name,
                    detected=True,
                    user_agent_suffix=f"(agent={detector.name})",
                )

    return AgentInfo(name="", detected=False, user_agent_suffix="")


def is_agent_mode() -> bool:
    """Determine if agent mode should be enabled.

    Priority resolution (first match wins):
      1. EVO_FORCE_AGENT_MODE=1 → True
      2. EVO_NO_AGENT_MODE=1 → False (overrides everything including detection)
      3. EVO_CLI_AGENT_MODE=1 → True (legacy/backward compat)
      4. Auto-detection via environment variables → True if detected
      5. Default → False

    This allows users to:
      - Force agent mode on with EVO_FORCE_AGENT_MODE=1 (even without agent detection)
      - Force agent mode off with EVO_NO_AGENT_MODE=1 (even if agent is detected)
      - Fall back to auto-detection if no force flags are set
      - Use legacy EVO_CLI_AGENT_MODE for backward compatibility

    Returns:
        True if agent mode should be enabled, False otherwise
    """
    # Priority 1: Explicit force-on flag
    if _is_env_truthy("EVO_FORCE_AGENT_MODE"):
        return True

    # Priority 2: Explicit force-off flag (overrides everything)
    if _is_env_truthy("EVO_NO_AGENT_MODE"):
        return False

    # Priority 3: Legacy agent mode flag (backward compatibility)
    if _is_env_truthy("EVO_CLI_AGENT_MODE"):
        return True

    # Priority 4: Auto-detect via environment variables
    if detect_agent_info().detected:
        return True

    # Priority 5: Default to off
    return False


def get_user_agent() -> str:
    """Get user-agent string, optionally with detected agent suffix.

    Returns:
        "evo-cli/0.1.0" or "evo-cli/0.1.0 (agent=<name>)" when agent is detected
    """
    base = "evo-cli/0.1.0"
    info = detect_agent_info()
    if info.user_agent_suffix:
        return f"{base} {info.user_agent_suffix}"
    return base


__all__ = [
    "AgentDetector",
    "AgentInfo",
    "detect_agent_info",
    "get_user_agent",
    "is_agent_mode",
]
