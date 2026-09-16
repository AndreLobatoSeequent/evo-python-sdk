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
    ellipsoid_major: float = typer.Option(..., "--ellipsoid-major", help="Search ellipsoid major (longest) range"),
    ellipsoid_semi_major: float = typer.Option(..., "--ellipsoid-semi-major", help="Search ellipsoid semi-major range"),
    ellipsoid_minor: float = typer.Option(..., "--ellipsoid-minor", help="Search ellipsoid minor (shortest) range"),
    max_samples: int = typer.Option(..., "--max-samples", help="Maximum number of samples to use per block"),
    min_samples: int | None = typer.Option(None, "--min-samples", help="Minimum samples required to estimate a block"),
    workspace: str | None = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Build kriging computation parameters from objects in a workspace."""
    asyncio.run(
        _do_build(
            source_object_id, source_attribute,
            target_object_id, target_attribute,
            variogram_object_id,
            ellipsoid_major, ellipsoid_semi_major, ellipsoid_minor,
            max_samples, min_samples,
            workspace,
        )
    )


async def _do_build(
    source_id: str,
    source_attr: str,
    target_id: str,
    target_attr: str,
    variogram_id: str,
    ellipsoid_major: float,
    ellipsoid_semi_major: float,
    ellipsoid_minor: float,
    max_samples: int,
    min_samples: int | None,
    workspace: str | None,
) -> None:
    from evo.common import StaticContext
    from evo.compute.tasks import Ellipsoid, EllipsoidRanges, SearchNeighborhood, Target
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

        if source_attribute.attribute_type != "scalar":
            output.emit_error(
                f"attribute '{source_attr}' has type '{source_attribute.attribute_type}'; "
                "kriging requires a scalar (numeric) attribute"
            )

        search = SearchNeighborhood(
            ellipsoid=Ellipsoid(ranges=EllipsoidRanges(
                major=ellipsoid_major,
                semi_major=ellipsoid_semi_major,
                minor=ellipsoid_minor,
            )),
            max_samples=max_samples,
            min_samples=min_samples,
        )

        params = KrigingParameters(
            source=Source(object=source_obj, attribute=source_attribute),
            target=Target.new_attribute(target_obj, target_attr),
            variogram=variogram_obj,
            search=search,
        )
        payload = params.model_dump(mode="json", by_alias=True)
    except Exception as exc:
        output.emit_error(str(exc))

    output.emit(
        payload,
        plain=(
            f"Built kriging parameters\n  Source: {source_id} [{source_attr}]"
            f"\n  Target: {target_id} [{target_attr}]\n  Variogram: {variogram_id}"
        ),
    )


@app.command("run")
def run(
    params_file: Path = typer.Option(
        ..., "--params-file", help="Path to kriging parameters JSON file (from kriging build)"
    ),
    workspace: str | None = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for results (default: true)"),
    interval: float = typer.Option(0.5, "--interval", help="Polling interval in seconds"),
    preview: bool = typer.Option(True, "--preview/--no-preview", help="Send API-Preview: opt-in header"),
) -> None:
    """Run a kriging computation task."""
    parameters = json.loads(params_file.read_text())
    asyncio.run(_do_run(parameters, workspace, wait, interval, preview))


async def _do_run(
    parameters: dict, workspace: str | None, wait_for_results: bool, interval: float, preview: bool
) -> None:
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
                preview=preview,
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
    if wait_for_results:
        output.emit(
            {"job_url": job_url, "status": "succeeded", "results": results},
            plain=f"Kriging succeeded: {job_url}\nResults:\n{json.dumps(results, indent=2, default=str)}",
        )
    else:
        output.emit(
            {"job_url": job_url, "status": "submitted"},
            plain=f"Kriging task submitted: {job_url}",
        )
