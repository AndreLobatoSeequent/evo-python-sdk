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

import unittest

from evo.cli.config import (
    DEFAULT_REDIRECT_URI,
    CliConfig,
    get_client_id,
    get_environment,
    get_redirect_uri,
    load_config,
    save_config,
)


class TestCliConfig(unittest.TestCase):
    def test_load_config_missing_file_returns_defaults(self):
        config = load_config()
        self.assertEqual(config, CliConfig())
        self.assertIsNone(config.client_id)
        self.assertEqual(config.redirect_uri, DEFAULT_REDIRECT_URI)
        self.assertEqual(config.env, "prod")

    def test_round_trip(self):
        config = CliConfig(client_id="my-client-id", redirect_uri="http://localhost:9999/cb", env="qa")
        save_config(config)
        self.assertEqual(load_config(), config)

    def test_load_config_corrupt_file_returns_defaults(self):
        from evo.cli import config as config_module

        config_module._CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        config_module._CONFIG_FILE.write_text("not-valid-json{{{")
        self.assertEqual(load_config(), CliConfig())

    def test_get_client_id_reflects_saved_config(self):
        self.assertIsNone(get_client_id())
        save_config(CliConfig(client_id="abc"))
        self.assertEqual(get_client_id(), "abc")

    def test_get_redirect_uri_defaults(self):
        self.assertEqual(get_redirect_uri(), DEFAULT_REDIRECT_URI)
        save_config(CliConfig(redirect_uri="http://localhost:1234/cb"))
        self.assertEqual(get_redirect_uri(), "http://localhost:1234/cb")


class TestGetEnvironment(unittest.TestCase):
    def test_defaults_to_prod(self):
        env = get_environment()
        self.assertEqual(env.name, "prod")
        self.assertEqual(env.ims_url, "https://ims.bentley.com")
        self.assertEqual(env.docs_url, "https://developer.seequent.com/docs/guides/getting-started/apps-and-tokens")

    def test_reads_persisted_env(self):
        save_config(CliConfig(env="qa"))
        env = get_environment()
        self.assertEqual(env.name, "qa")
        self.assertEqual(env.ims_url, "https://qa-ims.bentley.com")
        self.assertEqual(env.docs_url, "https://developer.int.seequent.com/docs/guides/getting-started/apps-and-tokens")

    def test_explicit_name_overrides_persisted_value(self):
        save_config(CliConfig(env="prod"))
        env = get_environment("qa")
        self.assertEqual(env.name, "qa")

    def test_unknown_env_raises(self):
        with self.assertRaises(ValueError):
            get_environment("staging")


if __name__ == "__main__":
    unittest.main()
