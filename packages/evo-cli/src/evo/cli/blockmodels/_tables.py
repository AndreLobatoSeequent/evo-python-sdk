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

from pathlib import Path

from evo.cli import output


def read_table_file(path: Path):
    """Read a local CSV or Parquet file into a pyarrow Table."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        import pyarrow.csv

        return pyarrow.csv.read_csv(path)
    elif suffix == ".parquet":
        import pyarrow.parquet

        return pyarrow.parquet.read_table(path)
    else:
        output.emit_error(f"Unsupported file extension {suffix!r} for {path}. Expected .csv or .parquet.")


def write_table_file(table, path: Path) -> None:
    """Write a pyarrow Table to a local CSV or Parquet file."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        import pyarrow.csv

        pyarrow.csv.write_csv(table, path)
    elif suffix == ".parquet":
        import pyarrow.parquet

        pyarrow.parquet.write_table(table, path)
    else:
        output.emit_error(f"Unsupported file extension {suffix!r} for {path}. Expected .csv or .parquet.")


def parse_key_value_option(entries: list[str], flag: str) -> dict[str, str]:
    """Parse a repeatable '--flag key=value' option into a dict."""
    result: dict[str, str] = {}
    for entry in entries:
        if "=" not in entry:
            output.emit_error(f"Invalid {flag} {entry!r}. Expected 'key=value'.")
        key, value = entry.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key or not value:
            output.emit_error(f"{flag} {entry!r} must include both a key and a value.")
        result[key] = value
    return result
