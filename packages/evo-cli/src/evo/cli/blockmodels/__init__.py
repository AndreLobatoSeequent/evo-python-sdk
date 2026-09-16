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

from . import columns, reports, versions  # noqa: E402  (must follow `app` definition above)
from .commands import app

app.add_typer(versions.app, name="versions")
app.add_typer(columns.app, name="columns")
app.add_typer(reports.app, name="reports")

__all__ = ["app"]
