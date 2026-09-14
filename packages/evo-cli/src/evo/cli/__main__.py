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

import typer

from evo.cli.auth import app as auth_app

app = typer.Typer(
    name="evo",
    help="Seequent Evo CLI — LLM-first interface to the Evo platform.",
    no_args_is_help=True,
)

app.add_typer(auth_app, name="auth")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
