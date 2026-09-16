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

"""Install AI agent skills that teach coding assistants to use the evo CLI.

A "skill" here is a `SKILL.md` file, following the same convention used by Claude Code,
Cursor, and other AI coding assistants: a markdown file with YAML frontmatter (name,
description) that an assistant loads to learn how and when to use this CLI. `evo skills
install` copies the skill bundled with this version of `evo` into the directory a given
assistant scans for skills.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Optional

import typer

from evo.cli import output

app = typer.Typer(help="Install AI agent skills that teach coding assistants to use the evo CLI.")

SKILL_NAME = "evo-cli"
SKILL_DESCRIPTION = "Discover and run Seequent Evo CLI commands for geoscience objects, block models, workspaces, files, and compute jobs."
_SKILL_CONTENT_PATH = Path(__file__).parent / "evo-cli" / "SKILL.md"


class Platform(str, Enum):
    claude = "claude"
    cursor = "cursor"
    copilot = "copilot"
    codex = "codex"
    opencode = "opencode"
    windsurf = "windsurf"
    gemini = "gemini"
    pi = "pi"
    devin = "devin"
    all = "all"


_ALL_PLATFORMS = [platform for platform in Platform if platform != Platform.all]

# Skills directory relative to a project root, keyed by platform.
_PROJECT_RELATIVE: dict[Platform, str] = {
    Platform.claude: ".claude/skills",
    Platform.cursor: ".cursor/skills",
    Platform.copilot: ".github/skills",
    Platform.codex: ".codex/skills",
    Platform.opencode: ".opencode/skills",
    Platform.windsurf: ".windsurf/skills",
    Platform.gemini: ".gemini/skills",
    Platform.pi: ".pi/skills",
    Platform.devin: ".agents/skills",
}

# Skills directory relative to the user's home directory, keyed by platform.
# Platform.claude is handled separately below since it also honors CLAUDE_CONFIG_DIR.
_USER_RELATIVE: dict[Platform, str] = {
    Platform.cursor: ".cursor/skills",
    Platform.copilot: ".copilot/skills",
    Platform.codex: ".codex/skills",
    Platform.opencode: ".config/opencode/skills",
    Platform.windsurf: ".windsurf/skills",
    Platform.gemini: ".gemini/skills",
    Platform.pi: ".pi/agent/skills",
    Platform.devin: ".agents/skills",
}

# Environment variables that mark the AI coding assistant currently running this CLI,
# checked in order. Kept separate from evo.cli.useragent's detectors, which serve a
# different purpose (user-agent strings / agent-mode output) and use different variables.
_DETECTORS: list[tuple[str, Platform]] = [
    ("CLAUDECODE", Platform.claude),
    ("CLAUDE_CODE", Platform.claude),
    ("CURSOR_AGENT", Platform.cursor),
    ("COPILOT_CLI", Platform.copilot),
    ("CODEX", Platform.codex),
    ("OPENAI_CODEX", Platform.codex),
    ("OPENCODE", Platform.opencode),
    ("WINDSURF_AGENT", Platform.windsurf),
    ("GEMINI_CODE_ASSIST", Platform.gemini),
    ("PI_CODING_AGENT", Platform.pi),
    ("DEVIN_SESSION_ID", Platform.devin),
]


def _skill_content() -> str:
    return _SKILL_CONTENT_PATH.read_text(encoding="utf-8")


def _detect_platform() -> Platform:
    for env_var, platform in _DETECTORS:
        if os.environ.get(env_var):
            return platform
    output.emit_error(
        "could not detect an AI coding assistant; specify one, for example 'evo skills install claude'.",
        code="platform_not_detected",
    )
    raise AssertionError("unreachable")  # emit_error always raises typer.Exit


def _platform_path(platform: Platform, project: bool) -> Path:
    if project:
        return Path.cwd() / _PROJECT_RELATIVE[platform]
    if platform == Platform.claude:
        config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
        base = Path(config_dir) if config_dir else Path.home() / ".claude"
        return base / "skills"
    return Path.home() / _USER_RELATIVE[platform]


@app.command("list")
def list_skills() -> None:
    """List the AI agent skills embedded in this version of evo."""
    output.emit(
        {"skills": [{"name": SKILL_NAME, "type": "skill", "description": SKILL_DESCRIPTION}]},
        plain=f"{SKILL_NAME}\tskill\t{SKILL_DESCRIPTION}",
    )


@app.command()
def install(
    platform: Optional[Platform] = typer.Argument(None, help="Target assistant; omit to detect the current assistant."),
    project: bool = typer.Option(
        False, "--project", help="Install in the current project instead of the user profile."
    ),
    name: Optional[str] = typer.Option(None, "--name", help="Install only this skill."),
    dir: Optional[Path] = typer.Option(
        None, "--dir", help="Install under a custom skills directory.", show_default=False
    ),
) -> None:
    """Install skills for an AI coding assistant."""
    if dir is not None and project:
        output.emit_error("--project and --dir cannot be used together.")
    if name is not None and name != SKILL_NAME:
        output.emit_error(f"unknown skill {name!r}; run 'evo skills list' to see available skills.")

    if dir is not None:
        bases = [dir]
    else:
        resolved_platform = platform or _detect_platform()
        if resolved_platform == Platform.all:
            bases = [_platform_path(p, project) for p in _ALL_PLATFORMS]
        else:
            bases = [_platform_path(resolved_platform, project)]

    content = _skill_content()
    installed: list[Path] = []
    seen: set[Path] = set()
    for base in bases:
        destination = base / SKILL_NAME / "SKILL.md"
        if destination in seen:
            continue
        seen.add(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        installed.append(destination)

    output.emit(
        {"installed": [str(p) for p in installed]},
        plain="\n".join(f"Installed {SKILL_NAME} to {p}." for p in installed),
    )


@app.command()
def path(
    platform: Platform = typer.Argument(..., help="Target assistant."),
    project: bool = typer.Option(
        False, "--project", help="Print the project-local path instead of the user-global path."
    ),
) -> None:
    """Print the skills directory for an AI coding assistant."""
    if platform == Platform.all:
        output.emit_error("'all' does not have a single skills path.")
    result = _platform_path(platform, project)
    output.emit({"path": str(result)}, plain=str(result))
