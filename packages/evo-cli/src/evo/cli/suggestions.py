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

import difflib
from typing import Optional

__all__ = ["suggest_command", "suggest_flag", "get_suggestions"]


def get_suggestions(
    input_str: str,
    choices: list[str],
    max_suggestions: int = 1,
    cutoff: float = 0.6,
) -> list[str]:
    """Find close matches for input_str from choices using fuzzy matching.

    Args:
        input_str: The user's input (possibly misspelled)
        choices: List of valid options to match against
        max_suggestions: Maximum number of suggestions to return
        cutoff: Minimum similarity score (0-1) to consider a match

    Returns:
        List of close matches, sorted by similarity (best first)
    """
    if not input_str or not choices:
        return []

    matches = difflib.get_close_matches(
        input_str,
        choices,
        n=max_suggestions,
        cutoff=cutoff,
    )
    return matches


def suggest_command(entered: str, available_commands: list[str]) -> Optional[str]:
    """Suggest the best matching command if user entered an unknown one.

    Args:
        entered: The command the user tried to run
        available_commands: List of valid command names

    Returns:
        Best matching command, or None if no close match found
    """
    suggestions = get_suggestions(entered, available_commands, max_suggestions=1)
    return suggestions[0] if suggestions else None


def suggest_flag(entered: str, available_flags: list[str]) -> Optional[str]:
    """Suggest the best matching flag if user entered an unknown one.

    Args:
        entered: The flag the user tried to use (e.g., '--formatt')
        available_flags: List of valid flag names (e.g., ['--format', '--help'])

    Returns:
        Best matching flag, or None if no close match found
    """
    suggestions = get_suggestions(entered, available_flags, max_suggestions=1)
    return suggestions[0] if suggestions else None
