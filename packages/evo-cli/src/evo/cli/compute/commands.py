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

import typer

from evo.cli.compute.job import app as job_app
from evo.cli.compute.kriging import app as kriging_app

app = typer.Typer(help="Submit and manage compute tasks (jobs).")
app.add_typer(job_app, name="job")
app.add_typer(kriging_app, name="kriging")
