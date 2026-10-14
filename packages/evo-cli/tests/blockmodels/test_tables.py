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

import tempfile
import unittest
from pathlib import Path

import pyarrow
import typer

from evo.cli.blockmodels._tables import parse_key_value_option, read_table_file, write_table_file


class TestReadWriteTableFile(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)
        self.table = pyarrow.table({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_parquet_round_trip(self) -> None:
        path = self.tmp_path / "data.parquet"
        write_table_file(self.table, path)
        result = read_table_file(path)
        self.assertEqual(result.to_pydict(), self.table.to_pydict())

    def test_csv_round_trip(self) -> None:
        path = self.tmp_path / "data.csv"
        write_table_file(self.table, path)
        result = read_table_file(path)
        self.assertEqual(result.column("col1").to_pylist(), [1, 2, 3])
        self.assertEqual(result.column("col2").to_pylist(), ["a", "b", "c"])

    def test_read_unsupported_suffix_exits(self) -> None:
        path = self.tmp_path / "data.txt"
        path.write_text("x")
        with self.assertRaises(typer.Exit):
            read_table_file(path)

    def test_write_unsupported_suffix_exits(self) -> None:
        path = self.tmp_path / "data.txt"
        with self.assertRaises(typer.Exit):
            write_table_file(self.table, path)


class TestParseKeyValueOption(unittest.TestCase):
    def test_parses_entries(self) -> None:
        result = parse_key_value_option(["a=1", "b=2"], "--flag")
        self.assertEqual(result, {"a": "1", "b": "2"})

    def test_malformed_entry_exits(self) -> None:
        with self.assertRaises(typer.Exit):
            parse_key_value_option(["no-equals"], "--flag")

    def test_missing_key_or_value_exits(self) -> None:
        with self.assertRaises(typer.Exit):
            parse_key_value_option(["=value"], "--flag")
