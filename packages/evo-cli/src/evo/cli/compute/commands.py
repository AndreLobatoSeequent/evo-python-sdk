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
from evo.compute.client import JobClient
from evo.compute.data import JobProgress
from evo.compute.exceptions import JobError, JobPendingError
from evo.compute.tasks.geostatistics.kriging import KrigingParameters
from evo.compute.tasks.common import Source
from evo.compute.tasks import Ellipsoid, EllipsoidRanges, SearchNeighborhood, Target
from evo.objects.typed import object_from_uuid
from evo.common import StaticContext

app = typer.Typer(help="Submit and manage compute tasks (jobs).")


def _load_parameters(params: Optional[str], params_file: Optional[Path]) -> dict:
    if params and params_file:
        output.emit_error("provide only one of --params or --params-file")
    if not params and not params_file:
        output.emit_error("provide --params or --params-file")

    text = params if params is not None else params_file.read_text()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        output.emit_error(f"invalid JSON in parameters: {exc}")

    if not isinstance(parsed, dict):
        output.emit_error("parameters must be a JSON object")
    return parsed


def _progress_to_dict(progress: JobProgress) -> dict:
    data = {"status": progress.status.value, "progress": progress.progress, "message": progress.message}
    if progress.error is not None:
        data["error"] = _job_error_to_dict(progress.error)
    return data


def _job_error_to_dict(exc: JobError) -> dict:
    content = exc.content or {}
    return {"status": exc.status, "title": content.get("title"), "detail": content.get("detail")}


def _emit_job_error(exc: JobError) -> None:
    error = _job_error_to_dict(exc)
    output.emit_error(error["title"] or str(exc), status=error["status"], detail=error["detail"])


@app.command()
def submit(
    topic: str = typer.Option(..., "--topic", help="Compute topic, e.g. 'geostatistics'"),
    task: str = typer.Option(..., "--task", help="Task name within the topic, e.g. 'kriging'"),
    params: Optional[str] = typer.Option(None, "--params", help="Task parameters as a JSON object string"),
    params_file: Optional[Path] = typer.Option(
        None, "--params-file", help="Path to a JSON file containing the task parameters object"
    ),
    preview: bool = typer.Option(
        False, "--preview", help="Set the API-Preview: opt-in header (required for tasks still in preview)"
    ),
    wait: bool = typer.Option(
        False, "--wait", help="Poll until the job completes and print the results instead of the job URL"
    ),
    interval: float = typer.Option(0.5, "--interval", help="Polling interval in seconds, used with --wait"),
) -> None:
    """Submit a compute task."""
    parameters = _load_parameters(params, params_file)
    asyncio.run(_do_submit(topic, task, parameters, preview, wait, interval))


async def _do_submit(topic: str, task: str, parameters: dict, preview: bool, wait: bool, interval: float) -> None:
    creds = await require_credentials()
    async with make_connector(creds) as connector:
        try:
            job = await JobClient.submit(
                connector=connector,
                org_id=creds.org_id,
                topic=topic,
                task=task,
                parameters=parameters,
                preview=preview,
            )
            if wait:
                results = await job.wait_for_results(polling_interval_seconds=interval)
        except JobPendingError as exc:
            output.emit_error(str(exc))
        except JobError as exc:
            _emit_job_error(exc)
        except Exception as exc:
            output.emit_error(str(exc))

    if wait:
        output.emit(
            {"job_url": job.url, "status": "succeeded", "results": results},
            plain=f"Job succeeded: {job.url}\n{json.dumps(results, indent=2, default=str)}",
        )
    else:
        output.emit(
            {"job_url": job.url, "topic": topic, "task": task},
            plain=f"Submitted job: {job.url}",
        )


@app.command()
def status(
    job_url: str = typer.Argument(help="Job status URL, as printed by 'evo compute submit'"),
    preview: bool = typer.Option(False, "--preview", help="Set the API-Preview: opt-in header"),
) -> None:
    """Get the status of a submitted job."""
    asyncio.run(_do_status(job_url, preview))


async def _do_status(job_url: str, preview: bool) -> None:
    creds = await require_credentials()
    async with make_connector(creds) as connector:
        job = JobClient.from_url(connector, job_url, preview=preview)
        try:
            progress = await job.get_status()
        except Exception as exc:
            output.emit_error(str(exc))

    data = _progress_to_dict(progress)
    output.emit(data, plain=str(progress))


@app.command()
def result(
    job_url: str = typer.Argument(help="Job status URL, as printed by 'evo compute submit'"),
    preview: bool = typer.Option(False, "--preview", help="Set the API-Preview: opt-in header"),
) -> None:
    """Get the results of a completed job."""
    asyncio.run(_do_result(job_url, preview))


async def _do_result(job_url: str, preview: bool) -> None:
    creds = await require_credentials()
    async with make_connector(creds) as connector:
        job = JobClient.from_url(connector, job_url, preview=preview)
        try:
            results = await job.get_results()
        except JobPendingError as exc:
            output.emit_error(str(exc))
        except JobError as exc:
            _emit_job_error(exc)
        except Exception as exc:
            output.emit_error(str(exc))

    output.emit(results, plain=json.dumps(results, indent=2, default=str))


@app.command()
def cancel(
    job_url: str = typer.Argument(help="Job status URL, as printed by 'evo compute submit'"),
    preview: bool = typer.Option(False, "--preview", help="Set the API-Preview: opt-in header"),
) -> None:
    """Cancel a running job."""
    asyncio.run(_do_cancel(job_url, preview))


async def _do_cancel(job_url: str, preview: bool) -> None:
    creds = await require_credentials()
    async with make_connector(creds) as connector:
        job = JobClient.from_url(connector, job_url, preview=preview)
        try:
            await job.cancel()
        except Exception as exc:
            output.emit_error(str(exc))

    output.emit({"status": "cancelled", "job_url": job_url}, plain=f"Cancelled job: {job_url}")


@app.command()
def wait(
    job_url: str = typer.Argument(help="Job status URL, as printed by 'evo compute submit'"),
    preview: bool = typer.Option(False, "--preview", help="Set the API-Preview: opt-in header"),
    interval: float = typer.Option(0.5, "--interval", help="Polling interval in seconds"),
) -> None:
    """Wait for a job to complete and print the results."""
    asyncio.run(_do_wait(job_url, preview, interval))


async def _do_wait(job_url: str, preview: bool, interval: float) -> None:
    creds = await require_credentials()
    async with make_connector(creds) as connector:
        job = JobClient.from_url(connector, job_url, preview=preview)
        try:
            results = await job.wait_for_results(polling_interval_seconds=interval)
        except JobPendingError as exc:
            output.emit_error(str(exc))
        except JobError as exc:
            _emit_job_error(exc)
        except Exception as exc:
            output.emit_error(str(exc))

    output.emit(
        {"job_url": job_url, "status": "succeeded", "results": results},
        plain=f"Job succeeded: {job_url}\n{json.dumps(results, indent=2, default=str)}",
    )


@app.command("kriging-build")
def kriging_build(
    source_object_id: str = typer.Option(..., "--source", help="UUID of PointSet object with sample data"),
    source_attribute: str = typer.Option(..., "--source-attr", help="Attribute name on source object"),
    target_object_id: str = typer.Option(..., "--target", help="UUID of target BlockModel or Grid"),
    target_attribute: str = typer.Option(..., "--target-attr", help="Attribute name to create on target"),
    variogram_object_id: str = typer.Option(..., "--variogram", help="UUID of Variogram object"),
    ellipsoid_major: float = typer.Option(..., "--ellipsoid-major", help="Search ellipsoid major (longest) range"),
    ellipsoid_semi_major: float = typer.Option(..., "--ellipsoid-semi-major", help="Search ellipsoid semi-major range"),
    ellipsoid_minor: float = typer.Option(..., "--ellipsoid-minor", help="Search ellipsoid minor (shortest) range"),
    max_samples: int = typer.Option(..., "--max-samples", help="Maximum number of samples to use per block"),
    min_samples: Optional[int] = typer.Option(None, "--min-samples", help="Minimum samples required to estimate a block"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
) -> None:
    """Build kriging computation parameters from objects in a workspace."""
    asyncio.run(_do_kriging_build(
        source_object_id, source_attribute,
        target_object_id, target_attribute,
        variogram_object_id,
        ellipsoid_major, ellipsoid_semi_major, ellipsoid_minor,
        max_samples, min_samples,
        workspace,
    ))


async def _do_kriging_build(
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
        plain=f"Built kriging parameters\n  Source: {source_id} [{source_attr}]\n  Target: {target_id} [{target_attr}]\n  Variogram: {variogram_id}",
    )


@app.command("kriging-run")
def kriging_run(
    params_file: Path = typer.Option(..., "--params-file", help="Path to kriging parameters JSON file (from kriging-build)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", help="Workspace UUID (overrides current selection)"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for results (default: true)"),
    interval: float = typer.Option(0.5, "--interval", help="Polling interval in seconds"),
    preview: bool = typer.Option(True, "--preview/--no-preview", help="Send API-Preview: opt-in header (default: true)"),
) -> None:
    """Run a kriging computation task."""
    parameters = json.loads(params_file.read_text())
    asyncio.run(_do_kriging_run(parameters, workspace, wait, interval, preview))


async def _do_kriging_run(parameters: dict, workspace: str | None, wait_for_results: bool, interval: float, preview: bool) -> None:
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
