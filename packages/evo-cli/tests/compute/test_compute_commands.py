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

import json
import unittest
from unittest import mock
from uuid import UUID

from typer.testing import CliRunner

from evo.cli.__main__ import app
from evo.compute.data import JobProgress, JobStatusEnum
from evo.compute.exceptions import JobError, JobPendingError

runner = CliRunner()

_ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_JOB_URL = "https://acme.api.seequent.com/compute/orgs/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/geostatistics/kriging/11111111-2222-3333-4444-555555555555/status"


class _ComputeBase(unittest.TestCase):
    """Base class that patches the shared helpers and JobClient."""

    def setUp(self) -> None:
        self._patcher_creds = mock.patch("evo.cli.compute.commands.require_credentials", new_callable=mock.AsyncMock)
        self._patcher_conn = mock.patch("evo.cli.compute.commands.make_connector")
        self._patcher_job_client = mock.patch("evo.cli.compute.commands.JobClient")

        self.mock_creds = self._patcher_creds.start()
        self.mock_creds.return_value = mock.Mock(org_id=_ORG_ID)

        self.mock_conn_ctx = self._patcher_conn.start()
        self.mock_connector = mock.AsyncMock()
        self.mock_connector.__aenter__ = mock.AsyncMock(return_value=self.mock_connector)
        self.mock_connector.__aexit__ = mock.AsyncMock(return_value=False)
        self.mock_conn_ctx.return_value = self.mock_connector

        self.MockJobClient = self._patcher_job_client.start()
        self.mock_job = mock.AsyncMock()
        self.mock_job.url = _JOB_URL
        self.MockJobClient.submit = mock.AsyncMock(return_value=self.mock_job)
        self.MockJobClient.from_url = mock.Mock(return_value=self.mock_job)

    def tearDown(self) -> None:
        mock.patch.stopall()


# ---------------------------------------------------------------------------
# compute submit
# ---------------------------------------------------------------------------


class TestComputeSubmit(_ComputeBase):
    def test_submit_prints_job_url_plain(self) -> None:
        result = runner.invoke(
            app, ["compute", "submit", "--topic", "geostatistics", "--task", "kriging", "--params", "{}"]
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(_JOB_URL, result.output)
        self.MockJobClient.submit.assert_called_once()
        _, kwargs = self.MockJobClient.submit.call_args
        self.assertEqual(kwargs["org_id"], _ORG_ID)
        self.assertEqual(kwargs["topic"], "geostatistics")
        self.assertEqual(kwargs["task"], "kriging")
        self.assertEqual(kwargs["parameters"], {})
        self.assertFalse(kwargs["preview"])

    def test_submit_json_output(self) -> None:
        result = runner.invoke(
            app,
            [
                "--format",
                "json",
                "compute",
                "submit",
                "--topic",
                "geostatistics",
                "--task",
                "kriging",
                "--params",
                "{}",
            ],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["job_url"], _JOB_URL)
        self.assertEqual(data["topic"], "geostatistics")
        self.assertEqual(data["task"], "kriging")

    def test_submit_passes_preview_flag(self) -> None:
        runner.invoke(
            app,
            ["compute", "submit", "--topic", "geostatistics", "--task", "kriging", "--params", "{}", "--preview"],
        )
        _, kwargs = self.MockJobClient.submit.call_args
        self.assertTrue(kwargs["preview"])

    def test_submit_with_params_file(self) -> None:
        with mock.patch("evo.cli.compute.commands.Path.read_text", return_value='{"a": 1}'):
            result = runner.invoke(
                app,
                [
                    "compute",
                    "submit",
                    "--topic",
                    "geostatistics",
                    "--task",
                    "kriging",
                    "--params-file",
                    "params.json",
                ],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        _, kwargs = self.MockJobClient.submit.call_args
        self.assertEqual(kwargs["parameters"], {"a": 1})

    def test_submit_wait_prints_results(self) -> None:
        self.mock_job.wait_for_results = mock.AsyncMock(return_value={"answer": 42})

        result = runner.invoke(
            app,
            ["compute", "submit", "--topic", "geostatistics", "--task", "kriging", "--params", "{}", "--wait"],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("42", result.output)

    def test_submit_wait_json_output(self) -> None:
        self.mock_job.wait_for_results = mock.AsyncMock(return_value={"answer": 42})

        result = runner.invoke(
            app,
            [
                "--format",
                "json",
                "compute",
                "submit",
                "--topic",
                "geostatistics",
                "--task",
                "kriging",
                "--params",
                "{}",
                "--wait",
            ],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["results"], {"answer": 42})

    def test_submit_requires_params_or_file(self) -> None:
        result = runner.invoke(app, ["compute", "submit", "--topic", "geostatistics", "--task", "kriging"])
        self.assertNotEqual(result.exit_code, 0)

    def test_submit_rejects_both_params_and_file(self) -> None:
        result = runner.invoke(
            app,
            [
                "compute",
                "submit",
                "--topic",
                "geostatistics",
                "--task",
                "kriging",
                "--params",
                "{}",
                "--params-file",
                "params.json",
            ],
        )
        self.assertNotEqual(result.exit_code, 0)

    def test_submit_rejects_invalid_json(self) -> None:
        result = runner.invoke(
            app, ["compute", "submit", "--topic", "geostatistics", "--task", "kriging", "--params", "not-json"]
        )
        self.assertNotEqual(result.exit_code, 0)

    def test_submit_rejects_non_object_json(self) -> None:
        result = runner.invoke(
            app, ["compute", "submit", "--topic", "geostatistics", "--task", "kriging", "--params", "[1, 2]"]
        )
        self.assertNotEqual(result.exit_code, 0)

    def test_submit_job_error(self) -> None:
        self.MockJobClient.submit = mock.AsyncMock(
            side_effect=JobError(
                status=422, reason=None, content={"title": "bad params", "detail": "oops"}, headers=None
            )
        )
        result = runner.invoke(
            app, ["compute", "submit", "--topic", "geostatistics", "--task", "kriging", "--params", "{}"]
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("bad params", result.output)


# ---------------------------------------------------------------------------
# compute status
# ---------------------------------------------------------------------------


class TestComputeStatus(_ComputeBase):
    def test_status_plain(self) -> None:
        self.mock_job.get_status = mock.AsyncMock(
            return_value=JobProgress(status=JobStatusEnum.in_progress, progress=42, message="working")
        )

        result = runner.invoke(app, ["compute", "status", _JOB_URL])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("in progress", result.output)
        self.assertIn("42", result.output)
        self.MockJobClient.from_url.assert_called_once_with(self.mock_connector, _JOB_URL, preview=False)

    def test_status_json(self) -> None:
        self.mock_job.get_status = mock.AsyncMock(
            return_value=JobProgress(status=JobStatusEnum.succeeded, progress=100, message=None)
        )

        result = runner.invoke(app, ["--format", "json", "compute", "status", _JOB_URL])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "succeeded")
        self.assertEqual(data["progress"], 100)

    def test_status_passes_preview(self) -> None:
        self.mock_job.get_status = mock.AsyncMock(
            return_value=JobProgress(status=JobStatusEnum.succeeded, progress=100, message=None)
        )
        runner.invoke(app, ["compute", "status", _JOB_URL, "--preview"])
        self.MockJobClient.from_url.assert_called_once_with(self.mock_connector, _JOB_URL, preview=True)


# ---------------------------------------------------------------------------
# compute result
# ---------------------------------------------------------------------------


class TestComputeResult(_ComputeBase):
    def test_result_json(self) -> None:
        self.mock_job.get_results = mock.AsyncMock(return_value={"answer": 42})

        result = runner.invoke(app, ["--format", "json", "compute", "result", _JOB_URL])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.output), {"answer": 42})

    def test_result_pending(self) -> None:
        self.mock_job.get_results = mock.AsyncMock(side_effect=JobPendingError(url=_JOB_URL, status="in progress"))

        result = runner.invoke(app, ["compute", "result", _JOB_URL])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("pending", result.output)

    def test_result_job_error(self) -> None:
        self.mock_job.get_results = mock.AsyncMock(
            side_effect=JobError(
                status=500, reason=None, content={"title": "boom", "detail": "server error"}, headers=None
            )
        )

        result = runner.invoke(app, ["compute", "result", _JOB_URL])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("boom", result.output)


# ---------------------------------------------------------------------------
# compute cancel
# ---------------------------------------------------------------------------


class TestComputeCancel(_ComputeBase):
    def test_cancel(self) -> None:
        self.mock_job.cancel = mock.AsyncMock(return_value=None)

        result = runner.invoke(app, ["compute", "cancel", _JOB_URL])

        self.assertEqual(result.exit_code, 0, result.output)
        self.mock_job.cancel.assert_called_once()

    def test_cancel_json(self) -> None:
        self.mock_job.cancel = mock.AsyncMock(return_value=None)

        result = runner.invoke(app, ["--format", "json", "compute", "cancel", _JOB_URL])

        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "cancelled")


# ---------------------------------------------------------------------------
# compute wait
# ---------------------------------------------------------------------------


class TestComputeWait(_ComputeBase):
    def test_wait_prints_results(self) -> None:
        self.mock_job.wait_for_results = mock.AsyncMock(return_value={"answer": 42})

        result = runner.invoke(app, ["compute", "wait", _JOB_URL])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("42", result.output)
        _, kwargs = self.mock_job.wait_for_results.call_args
        self.assertEqual(kwargs["polling_interval_seconds"], 0.5)

    def test_wait_custom_interval(self) -> None:
        self.mock_job.wait_for_results = mock.AsyncMock(return_value={})

        runner.invoke(app, ["compute", "wait", _JOB_URL, "--interval", "2.5"])

        _, kwargs = self.mock_job.wait_for_results.call_args
        self.assertEqual(kwargs["polling_interval_seconds"], 2.5)


# ---------------------------------------------------------------------------
# error cases: not logged in
# ---------------------------------------------------------------------------


class TestComputeErrorCases(unittest.TestCase):
    @mock.patch(
        "evo.cli.compute.commands.require_credentials",
        new_callable=mock.AsyncMock,
        side_effect=SystemExit(1),
    )
    def test_submit_not_logged_in_exits(self, _mock) -> None:
        result = runner.invoke(
            app, ["compute", "submit", "--topic", "geostatistics", "--task", "kriging", "--params", "{}"]
        )
        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
