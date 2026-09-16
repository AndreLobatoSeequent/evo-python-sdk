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
from typing import TYPE_CHECKING, Optional

import typer

from evo.cli import output
from evo.cli._connector import make_connector, require_credentials

if TYPE_CHECKING:
    from evo.compute.data import JobProgress
    from evo.compute.exceptions import JobError

app = typer.Typer(help="Submit and manage compute jobs.")


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
    from evo.compute.client import JobClient
    from evo.compute.exceptions import JobError, JobPendingError

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
    job_url: str = typer.Argument(help="Job status URL, as printed by 'evo compute job submit'"),
    preview: bool = typer.Option(False, "--preview", help="Set the API-Preview: opt-in header"),
) -> None:
    """Get the status of a submitted job."""
    asyncio.run(_do_status(job_url, preview))


async def _do_status(job_url: str, preview: bool) -> None:
    from evo.compute.client import JobClient

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
    job_url: str = typer.Argument(help="Job status URL, as printed by 'evo compute job submit'"),
    preview: bool = typer.Option(False, "--preview", help="Set the API-Preview: opt-in header"),
) -> None:
    """Get the results of a completed job."""
    asyncio.run(_do_result(job_url, preview))


async def _do_result(job_url: str, preview: bool) -> None:
    from evo.compute.client import JobClient
    from evo.compute.exceptions import JobError, JobPendingError

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
    job_url: str = typer.Argument(help="Job status URL, as printed by 'evo compute job submit'"),
    preview: bool = typer.Option(False, "--preview", help="Set the API-Preview: opt-in header"),
) -> None:
    """Cancel a running job."""
    asyncio.run(_do_cancel(job_url, preview))


async def _do_cancel(job_url: str, preview: bool) -> None:
    from evo.compute.client import JobClient

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
    job_url: str = typer.Argument(help="Job status URL, as printed by 'evo compute job submit'"),
    preview: bool = typer.Option(False, "--preview", help="Set the API-Preview: opt-in header"),
    interval: float = typer.Option(0.5, "--interval", help="Polling interval in seconds"),
) -> None:
    """Wait for a job to complete and print the results."""
    asyncio.run(_do_wait(job_url, preview, interval))


async def _do_wait(job_url: str, preview: bool, interval: float) -> None:
    from evo.compute.client import JobClient
    from evo.compute.exceptions import JobError, JobPendingError

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
