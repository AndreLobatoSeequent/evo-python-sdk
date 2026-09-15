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

"""Pytest configuration: strip agent-detection env vars so tests run in plain mode."""

from __future__ import annotations

import os

import pytest

_AGENT_VARS = [
    "CLAUDECODE", "CLAUDE_CODE",
    "CURSOR_AGENT", "CURSOR",
    "CLINE",
    "GITHUB_COPILOT", "GH_COPILOT",
    "AMAZON_Q", "AWS_Q",
    "GEMINI_CODE",
    "AIDER",
    "CODEX",
    "WINDSURF",
    "CODY",
    "DEVIN_SESSION_ID",
    "EVO_FORCE_AGENT_MODE",
    "EVO_NO_AGENT_MODE",
    "EVO_CLI_AGENT_MODE",
]


@pytest.fixture(autouse=True)
def _clear_agent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all agent-detection env vars before each test.

    Tests that want agent mode can set EVO_FORCE_AGENT_MODE=1 explicitly.
    """
    for var in _AGENT_VARS:
        monkeypatch.delenv(var, raising=False)
