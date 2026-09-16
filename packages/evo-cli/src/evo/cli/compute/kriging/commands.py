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

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer

from evo.cli import output
from evo.cli._connector import make_connector, make_environment, require_credentials

app = typer.Typer(help="Manage kriging computation tasks.")


def _emit_job_error(exc) -> None:
    content = exc.content or {}
    error = {"status": exc.status, "title": content.get("title"), "detail": content.get("detail")}
    output.emit_error(error["title"] or str(exc), status=error["status"], detail=error["detail"])


@app.command("build")
def build(
    source_object_id: str = typer.Option(..., "--source", help="UUID of PointSet object with sample data"),
    source_attribute: str = typer.Option(..., "--source-attr", help="Attribute name on source object"),
    target_object_id: str = typer.Option(..., "--target", help="UUID of target BlockModel or Grid"),
    target_attribute: str = typer.Option(..., "--target-attr", help="Attribute name to create on target"),
    variogram_object_id: str = typer.Option(..., "--variogram", help="UUID of Variogram object"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Build kriging computation parameters from objects in a workspace."""
    asyncio.run(
        _do_build(
            source_object_id, source_attribute, target_object_id, target_attribute, variogram_object_id, workspace
        )
    )


async def _do_build(
    source_id: str, source_attr: str, target_id: str, target_attr: str, variogram_id: str, workspace: str | None
) -> None:
    from evo.common import StaticContext
    from evo.compute.tasks.common import Source
    from evo.compute.tasks.geostatistics.kriging import KrigingParameters
    from evo.objects.typed import object_from_uuid

    creds = await require_credentials()
    env = make_environment(creds, workspace)

    async with make_connector(creds) as connector:
        context = StaticContext.from_environment(env, connector)
        try:
            source_obj = await object_from_uuid(context, source_id)
            target_obj = await object_from_uuid(context, target_id)
            variogram_obj = await object_from_uuid(context, variogram_id)
        except Exception as exc:
            output.emit_error(str(exc))

    try:
        source_attribute = source_obj.attributes[source_attr]
        target_attribute = target_obj.attributes[target_attr]

        params = KrigingParameters(
            source=Source(object=source_obj, attribute=source_attribute),
            target=target_attribute,
            variogram=variogram_obj,
        )
        payload = params.model_dump(mode="json")
    except Exception as exc:
        output.emit_error(str(exc))

    output.emit(
        payload,
        plain=f"Built kriging parameters\n  Source: {source_id} [{source_attr}]\n  Target: {target_id} [{target_attr}]\n  Variogram: {variogram_id}",
    )


@app.command("run")
def run(
    params_file: Path = typer.Option(
        ..., "--params-file", help="Path to kriging parameters JSON file (from kriging build)"
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for results (default: true)"),
    interval: float = typer.Option(0.5, "--interval", help="Polling interval in seconds"),
) -> None:
    """Run a kriging computation task."""
    parameters = json.loads(params_file.read_text())
    asyncio.run(_do_run(parameters, workspace, wait, interval))


async def _do_run(parameters: dict, workspace: str | None, wait_for_results: bool, interval: float) -> None:
    from evo.compute.client import JobClient
    from evo.compute.exceptions import JobError, JobPendingError

    creds = await require_credentials()
    async with make_connector(creds) as connector:
        try:
            job = await JobClient.submit(
                connector=connector,
                org_id=creds.org_id,
                topic="geostatistics",
                task="kriging",
                parameters=parameters,
                preview=False,
            )
            if wait_for_results:
                results = await job.wait_for_results(polling_interval_seconds=interval)
        except JobPendingError as exc:
            output.emit_error(str(exc))
        except JobError as exc:
            _emit_job_error(exc)
        except Exception as exc:
            output.emit_error(str(exc))
            return

    job_url = job.url
    output.emit(
        {"job_url": job_url, "status": "submitted"},
        plain=f"Kriging task submitted: {job_url}"
        + (f"\nResults:\n{json.dumps(results, indent=2, default=str)}" if wait_for_results else ""),
    )
