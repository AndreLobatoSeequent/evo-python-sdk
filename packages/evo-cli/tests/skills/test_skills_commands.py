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
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from typer.testing import CliRunner

from evo.cli.__main__ import app
from evo.cli.skills.commands import _ALL_PLATFORMS, SKILL_NAME, _skill_content

runner = CliRunner()


class _SkillsBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"
        self.cwd = Path(self._tmp.name) / "project"
        self.home.mkdir()
        self.cwd.mkdir()

        self._patcher_home = mock.patch("pathlib.Path.home", return_value=self.home)
        self._patcher_cwd = mock.patch("pathlib.Path.cwd", return_value=self.cwd)
        self._patcher_home.start()
        self._patcher_cwd.start()
        self.addCleanup(self._patcher_home.stop)
        self.addCleanup(self._patcher_cwd.stop)

        # Ensure a stray CLAUDE_CONFIG_DIR in the host environment can't leak into tests.
        self._patcher_env = mock.patch.dict("os.environ", {}, clear=False)
        self._patcher_env.start()
        self.addCleanup(self._patcher_env.stop)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)


class TestSkillsList(unittest.TestCase):
    def test_list_plain(self):
        result = runner.invoke(app, ["skills", "list"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(SKILL_NAME, result.output)
        self.assertIn("skill", result.output)

    def test_list_json(self):
        result = runner.invoke(app, ["--format", "json", "skills", "list"])
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["skills"][0]["name"], SKILL_NAME)


class TestSkillsPath(_SkillsBase):
    def test_user_path_claude(self):
        result = runner.invoke(app, ["--format", "json", "skills", "path", "claude"])
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(Path(data["path"]), self.home / ".claude" / "skills")

    def test_project_path_cursor(self):
        result = runner.invoke(app, ["--format", "json", "skills", "path", "cursor", "--project"])
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(Path(data["path"]), self.cwd / ".cursor" / "skills")

    def test_claude_config_dir_override(self):
        custom = Path(self._tmp.name) / "custom-claude-config"
        with mock.patch.dict("os.environ", {"CLAUDE_CONFIG_DIR": str(custom)}):
            result = runner.invoke(app, ["--format", "json", "skills", "path", "claude"])
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(Path(data["path"]), custom / "skills")

    def test_all_has_no_single_path(self):
        result = runner.invoke(app, ["skills", "path", "all"])
        self.assertNotEqual(result.exit_code, 0)


class TestSkillsInstall(_SkillsBase):
    def test_install_to_platform(self):
        result = runner.invoke(app, ["--format", "json", "skills", "install", "claude"])
        self.assertEqual(result.exit_code, 0, result.output)
        destination = self.home / ".claude" / "skills" / SKILL_NAME / "SKILL.md"
        self.assertTrue(destination.exists())
        self.assertEqual(destination.read_text(encoding="utf-8"), _skill_content())
        data = json.loads(result.output)
        self.assertEqual(data["installed"], [str(destination)])

    def test_install_project(self):
        result = runner.invoke(app, ["skills", "install", "cursor", "--project"])
        self.assertEqual(result.exit_code, 0, result.output)
        destination = self.cwd / ".cursor" / "skills" / SKILL_NAME / "SKILL.md"
        self.assertTrue(destination.exists())

    def test_install_custom_dir(self):
        custom = Path(self._tmp.name) / "custom"
        result = runner.invoke(app, ["skills", "install", "--dir", str(custom)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue((custom / SKILL_NAME / "SKILL.md").exists())

    def test_install_all_writes_every_platform(self):
        result = runner.invoke(app, ["--format", "json", "skills", "install", "all"])
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(len(data["installed"]), len(_ALL_PLATFORMS))

    def test_install_unknown_skill_name_errors(self):
        result = runner.invoke(app, ["skills", "install", "claude", "--name", "not-a-skill"])
        self.assertNotEqual(result.exit_code, 0)

    def test_install_project_and_dir_conflict(self):
        result = runner.invoke(app, ["skills", "install", "--project", "--dir", str(self.cwd)])
        self.assertNotEqual(result.exit_code, 0)

    def test_install_detects_platform_from_environment(self):
        with mock.patch.dict("os.environ", {"CLAUDECODE": "1"}):
            result = runner.invoke(app, ["--format", "json", "skills", "install"])
        self.assertEqual(result.exit_code, 0, result.output)
        destination = self.home / ".claude" / "skills" / SKILL_NAME / "SKILL.md"
        self.assertTrue(destination.exists())

    def test_install_no_platform_detected_errors(self):
        result = runner.invoke(app, ["skills", "install"])
        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
