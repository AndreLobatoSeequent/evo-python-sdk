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

from typing import Optional

import typer

from evo.cli.admin import app as admin_app
from evo.cli.auth import app as auth_app
from evo.cli.instance import app as instance_app
from evo.cli.objects import app as objects_app
from evo.cli.output import OutputFormat, init as init_output
from evo.cli.workspace import app as workspace_app

app = typer.Typer(
    name="evo",
    help="Seequent Evo CLI — LLM-first interface to the Evo platform.",
    no_args_is_help=True,
)

app.add_typer(admin_app, name="admin")
app.add_typer(auth_app, name="auth")
app.add_typer(instance_app, name="instance")
app.add_typer(objects_app, name="objects")
app.add_typer(workspace_app, name="workspace")


@app.callback()
def callback(
    format: Optional[OutputFormat] = typer.Option(
        None,
        "--format",
        help="Output format. Overrides EVO_CLI_AGENT_MODE. [plain, json]",
        show_default=False,
    ),
) -> None:
    init_output(format)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
