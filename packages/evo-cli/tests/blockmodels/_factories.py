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
from evo.blockmodels.endpoints.models import BBoxXYZ, DataType, FloatRange, MissingColumnPolicy
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


def make_listing_column(*, title: str = "Cu") -> ListingColumn:
    return ListingColumn(col_id="col-1", data_type=DataType.Float64, group_uuid=None, title=title, unit_id="%[mass]")


def make_column(*, title: str = "Cu") -> Column:
    return Column(
        col_id="col-1", data_type=DataType.Float64, group_uuid=None, tags=None, title=title, unit_id="%[mass]"
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
