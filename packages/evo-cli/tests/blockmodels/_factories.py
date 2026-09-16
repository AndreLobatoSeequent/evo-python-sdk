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

"""Shared fixture factories for evo.cli.blockmodels tests."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from evo.blockmodels.data import (
    BlockModel,
    Column,
    ListingColumn,
    ListingGroup,
    ListingVersion,
    RegularGridDefinition,
    ResolvedGroup,
    Version,
)
from evo.blockmodels.endpoints.models import (
    BBoxXYZ,
    DataType,
    FloatRange,
    JobStatus,
    MissingColumnPolicy,
    PaginatedResponseReportResultSummary,
    PaginatedResponseWithUnitsReportSpecificationWithLastRunInfo,
    ReportAggregation,
    ReportCategory,
    ReportColumn,
    ReportComparison,
    ReportComparisonResultInfo,
    ReportComparisonResultSet,
    ReportComparisonRow,
    ReportComparisonValue,
    ReportComparisonWarnings,
    ReportResult,
    ReportResultCategory,
    ReportResultColumn,
    ReportResultSet,
    ReportResultSummary,
    ReportRow,
    ReportRunResult,
    ReportSpecificationWithJobUrl,
    ReportSpecificationWithLastRunInfo,
    ReportWarning,
    ReportWarningType,
    ReportingJobResult,
)
from evo.common.data import Environment, ServiceUser

ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
HUB_URL = "https://acme.api.seequent.com"
WORKSPACE_ID = UUID("11111111-2222-3333-4444-555555555555")
BM_ID = UUID("bbbbbbbb-0000-0000-0000-000000000001")
VERSION_UUID = UUID("cccccccc-0000-0000-0000-000000000001")
NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

ENVIRONMENT = Environment(hub_url=HUB_URL, org_id=ORG_ID, workspace_id=WORKSPACE_ID)
USER = ServiceUser(id=UUID("dddddddd-0000-0000-0000-000000000001"), name="Kim", email="kim@example.test")


def make_bbox() -> BBoxXYZ:
    return BBoxXYZ(
        x_minmax=FloatRange(min=0.0, max=10.0),
        y_minmax=FloatRange(min=0.0, max=10.0),
        z_minmax=FloatRange(min=0.0, max=10.0),
    )


def make_regular_grid() -> RegularGridDefinition:
    return RegularGridDefinition(
        model_origin=[0.0, 0.0, 0.0],
        rotations=[],
        n_blocks=[10, 10, 10],
        block_size=[1.0, 1.0, 1.0],
    )


def make_block_model(*, bm_id: UUID = BM_ID, name: str = "my_block_model") -> BlockModel:
    return BlockModel(
        environment=ENVIRONMENT,
        id=bm_id,
        name=name,
        created_at=NOW,
        created_by=USER,
        description="A test block model",
        grid_definition=make_regular_grid(),
        coordinate_reference_system="EPSG:3395",
        size_unit_id="m",
        bbox=make_bbox(),
        last_updated_at=NOW,
        last_updated_by=USER,
        geoscience_object_id=None,
        fill_subblocks=False,
    )


COL_DATA_ID = UUID("dddddddd-1111-0000-0000-000000000001")


def make_listing_column(*, title: str = "Cu") -> ListingColumn:
    return ListingColumn(col_id=str(COL_DATA_ID), data_type=DataType.Float64, group_uuid=None, title=title, unit_id="%[mass]")


def make_column(*, title: str = "Cu") -> Column:
    return Column(
        col_id=str(COL_DATA_ID), data_type=DataType.Float64, group_uuid=None, tags=None, title=title, unit_id="%[mass]"
    )


def make_listing_group() -> ListingGroup:
    return ListingGroup(
        group_uuid=UUID("eeeeeeee-0000-0000-0000-000000000001"),
        is_hidden=False,
        missing_column_policy=MissingColumnPolicy.INHERIT,
        parent_group_uuid=None,
        resolved_missing_column_policy=MissingColumnPolicy.USE_PREVIOUS,
        title="Assays",
    )


def make_resolved_group() -> ResolvedGroup:
    return ResolvedGroup(
        group_uuid=UUID("eeeeeeee-0000-0000-0000-000000000001"),
        is_hidden=False,
        missing_column_policy=MissingColumnPolicy.INHERIT,
        parent_group_uuid=None,
        resolved_missing_column_policy=MissingColumnPolicy.USE_PREVIOUS,
        tags=None,
        title="Assays",
    )


SPEC_ID = UUID("ffffffff-0000-0000-0000-000000000001")
COL_ID = UUID("cccccccc-1111-0000-0000-000000000001")
CAT_COL_ID = UUID("cccccccc-2222-0000-0000-000000000001")


def make_report_spec(*, name: str = "Gold Report", with_last_run: bool = True) -> ReportSpecificationWithLastRunInfo:
    return ReportSpecificationWithLastRunInfo(
        report_specification_uuid=SPEC_ID,
        bm_uuid=BM_ID,
        name=name,
        description="Grade report",
        revision=1,
        autorun=True,
        mass_unit_id="t",
        columns=[ReportColumn(col_id=COL_ID, label="Au Grade", aggregation=ReportAggregation.MASS_AVERAGE, output_unit_id="g/t")],
        categories=[ReportCategory(col_id=CAT_COL_ID, label="Domain", values=None)],
        density_value=2.7,
        density_unit_id="t/m3",
        density_col_id=None,
        cutoff_col_id=None,
        cutoff_values=[0.5, 1.0],
        last_result_version_id=3 if with_last_run else None,
        last_result_created_at=NOW if with_last_run else None,
    )


def make_report_spec_page(*specs: ReportSpecificationWithLastRunInfo) -> PaginatedResponseWithUnitsReportSpecificationWithLastRunInfo:
    return PaginatedResponseWithUnitsReportSpecificationWithLastRunInfo(
        results=list(specs),
        total=len(specs),
        count=len(specs),
        limit=50,
        offset=0,
        referenced_units=[],
    )


def make_listing_version(*, version_id: int = 1) -> ListingVersion:
    return ListingVersion(
        bm_uuid=BM_ID,
        version_id=version_id,
        version_uuid=VERSION_UUID,
        parent_version_id=version_id - 1,
        base_version_id=version_id - 1 if version_id > 1 else None,
        geoscience_version_id=None,
        created_at=NOW,
        created_by=USER,
        comment="initial version",
        bbox=None,
        columns=[make_listing_column()],
        groups=[make_listing_group()],
    )


RESULT_ID = UUID("eeeeeeee-0000-0000-0000-000000000001")
RESULT_ID2 = UUID("eeeeeeee-0000-0000-0000-000000000002")
JOB_ID = UUID("ffffffff-1111-0000-0000-000000000001")


def make_report_spec_with_job(*, run_now_job: bool = False) -> ReportSpecificationWithJobUrl:
    from pydantic import AnyUrl

    return ReportSpecificationWithJobUrl(
        report_specification_uuid=SPEC_ID,
        bm_uuid=BM_ID,
        name="Gold Report",
        description="Grade report",
        revision=2,
        autorun=True,
        mass_unit_id="t",
        columns=[ReportColumn(col_id=COL_ID, label="Au Grade", aggregation=ReportAggregation.MASS_AVERAGE, output_unit_id="g/t")],
        categories=[ReportCategory(col_id=CAT_COL_ID, label="Domain", values=None)],
        density_value=2.7,
        density_unit_id="t/m3",
        density_col_id=None,
        cutoff_col_id=None,
        cutoff_values=[0.5, 1.0],
        job_url=AnyUrl("https://acme.api.seequent.com/blockmodel/jobs/" + str(JOB_ID)) if run_now_job else None,
    )


def make_report_result(*, version_id: int = 5) -> ReportResult:
    return ReportResult(
        report_result_uuid=RESULT_ID,
        report_specification_uuid=SPEC_ID,
        report_specification_name="Gold Report",
        report_specification_revision=1,
        report_specification_description="Grade report",
        bm_uuid=BM_ID,
        version_id=version_id,
        version_uuid=VERSION_UUID,
        version_created_at=NOW,
        version_created_by={"name": "Kim"},
        version_comment="",
        report_result_created_at=NOW,
        categories=[ReportResultCategory(col_id=CAT_COL_ID, label="Domain")],
        value_columns=[
            ReportResultColumn(col_id=None, label="Mass", unit_id="t"),
            ReportResultColumn(col_id=COL_ID, label="Au Grade", unit_id="g/t"),
        ],
        referenced_columns=[],
        result_sets=[
            ReportResultSet(
                cutoff_value=0.0,
                rows=[
                    ReportRow(categories=["North"], values=[1250000.0, 1.80]),
                    ReportRow(categories=["South"], values=[980000.0, 2.10]),
                ],
            ),
            ReportResultSet(
                cutoff_value=0.5,
                rows=[
                    ReportRow(categories=["North"], values=[870000.0, 2.30]),
                ],
            ),
        ],
        cutoff_col_id=None,
        warnings=[],
    )


def make_result_summary(*, version_id: int = 5) -> ReportResultSummary:
    return ReportResultSummary(
        report_result_uuid=RESULT_ID,
        report_specification_uuid=SPEC_ID,
        version_id=version_id,
        version_uuid=VERSION_UUID,
        version_created_at=NOW,
        version_created_by={"name": "Kim"},
        report_result_created_at=NOW,
    )


def make_result_summary_page(*summaries: ReportResultSummary) -> PaginatedResponseReportResultSummary:
    return PaginatedResponseReportResultSummary(
        results=list(summaries),
        total=len(summaries),
        count=len(summaries),
        limit=50,
        offset=0,
    )


def make_reporting_job_result() -> ReportingJobResult:
    from pydantic import AnyUrl

    return ReportingJobResult(
        bm_uuid=BM_ID,
        report_specification_uuid=SPEC_ID,
        job_uuid=JOB_ID,
        job_url=AnyUrl("https://acme.api.seequent.com/blockmodel/jobs/" + str(JOB_ID)),
        version_id=5,
        version_uuid=VERSION_UUID,
    )


def make_report_run_result() -> ReportRunResult:
    return ReportRunResult(
        bm_uuid=BM_ID,
        report_specification_uuid=SPEC_ID,
        report_result_uuid=RESULT_ID,
        version_id=5,
        version_uuid=VERSION_UUID,
    )


def make_job_response(*, status: JobStatus = JobStatus.COMPLETE, payload=None):
    from evo.blockmodels.endpoints.models import JobResponse

    return JobResponse(job_status=status, payload=payload)


def make_report_comparison() -> ReportComparison:
    from pydantic import AnyUrl

    from_info = ReportComparisonResultInfo(
        report_result_uuid=RESULT_ID,
        report_result_created_at=NOW,
        version_id=3,
        version_uuid=VERSION_UUID,
        version_created_at=NOW,
        version_created_by={"name": "Kim"},
        referenced_columns=[],
    )
    to_info = ReportComparisonResultInfo(
        report_result_uuid=RESULT_ID2,
        report_result_created_at=NOW,
        version_id=5,
        version_uuid=UUID("cccccccc-0000-0000-0000-000000000002"),
        version_created_at=NOW,
        version_created_by={"name": "Kim"},
        referenced_columns=[],
    )
    return ReportComparison(
        report_specification_uuid=SPEC_ID,
        report_specification_name="Gold Report",
        report_specification_description="Grade report",
        report_specification_revision=1,
        bm_uuid=BM_ID,
        categories=[ReportResultCategory(col_id=CAT_COL_ID, label="Domain")],
        value_columns=[
            ReportResultColumn(col_id=None, label="Mass", unit_id="t"),
            ReportResultColumn(col_id=COL_ID, label="Au Grade", unit_id="g/t"),
        ],
        cutoff_col_id=None,
        from_result=from_info,
        to_result=to_info,
        result_sets=[
            ReportComparisonResultSet(
                cutoff_value=0.0,
                rows=[
                    ReportComparisonRow(
                        categories=["North"],
                        values=[
                            ReportComparisonValue(from_value=1000000.0, to_value=1250000.0, difference=250000.0, percent=25.0),
                            ReportComparisonValue(from_value=1.5, to_value=1.8, difference=0.3, percent=20.0),
                        ],
                    ),
                ],
            ),
        ],
        warnings=ReportComparisonWarnings(comparison=[], from_result=[], to_result=[]),
    )


def make_version(*, version_id: int = 1) -> Version:
    return Version(
        bm_uuid=BM_ID,
        version_id=version_id,
        version_uuid=VERSION_UUID,
        parent_version_id=version_id - 1,
        base_version_id=version_id - 1 if version_id > 1 else None,
        geoscience_version_id=None,
        created_at=NOW,
        created_by=USER,
        comment="initial version",
        bbox=None,
        columns=[make_column()],
        groups=[make_resolved_group()],
    )
