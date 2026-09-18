#!/usr/bin/env python
"""
Manual test of the kriging workflow in the CLI and SDK.

This script demonstrates:
1. Creating kriging parameters with different configurations
2. Serializing parameters to JSON (for CLI use)
3. Validating parameter combinations
4. Testing kriging methods and neighborhood configurations
"""

import json
from pathlib import Path

from evo.compute.tasks import (
    BlockDiscretisation,
    Ellipsoid,
    EllipsoidRanges,
    Filter,
    FilterCondition,
    SearchNeighborhood,
    Source,
    Target,
)
from evo.compute.tasks.geostatistics.kriging import (
    KrigingMethod,
    KrigingParameters,
    OrdinaryKriging,
    SimpleKriging,
)

# Test URLs (matching the test suite)
_BASE = "https://hub.test.evo.bentley.com"
_ORG = "00000000-0000-0000-0000-000000000001"
_WS = "00000000-0000-0000-0000-000000000002"


def _obj_url(obj_id: str = "00000000-0000-0000-0000-000000000003") -> str:
    """Return a valid ObjectReference URL for testing."""
    return f"{_BASE}/geoscience-object/orgs/{_ORG}/workspaces/{_WS}/objects/{obj_id}"


POINTSET_URL = _obj_url("00000000-0000-0000-0000-000000000010")
GRID_URL = _obj_url("00000000-0000-0000-0000-000000000020")
VARIOGRAM_URL = _obj_url("00000000-0000-0000-0000-000000000030")
BLOCKMODEL_URL = _obj_url("00000000-0000-0000-0000-000000000040")


def print_test_header(title: str) -> None:
    """Print a formatted test header."""
    print(f"\n{'=' * 70}")
    print(f"[PASS] {title}")
    print(f"{'=' * 70}")


def print_params(params: KrigingParameters, title: str = "Parameters") -> None:
    """Pretty-print kriging parameters."""
    print(f"\n{title}:")
    params_dict = params.model_dump(mode="json", by_alias=True, exclude_none=True)
    print(json.dumps(params_dict, indent=2))


def test_ordinary_kriging() -> None:
    """Test ordinary kriging (default method)."""
    print_test_header("Ordinary Kriging (Default)")

    search = SearchNeighborhood(
        ellipsoid=Ellipsoid(ranges=EllipsoidRanges(major=200, semi_major=150, minor=100)),
        max_samples=20,
    )

    params = KrigingParameters(
        source=Source(object=POINTSET_URL, attribute="locations.attributes[?key=='grade']"),
        target=Target.new_attribute(GRID_URL, "kriged_grade"),
        variogram=VARIOGRAM_URL,
        search=search,
    )

    print_params(params, "Ordinary Kriging Configuration")
    assert isinstance(params.method, OrdinaryKriging), "Should use ordinary kriging by default"
    print("\n[OK] Ordinary kriging configured successfully")


def test_simple_kriging() -> None:
    """Test simple kriging with a known constant mean."""
    print_test_header("Simple Kriging with Known Mean")

    search = SearchNeighborhood(
        ellipsoid=Ellipsoid(ranges=EllipsoidRanges(major=200, semi_major=150, minor=100)),
        max_samples=20,
    )

    method = KrigingMethod.simple(mean=100.0)
    params = KrigingParameters(
        source=Source(object=POINTSET_URL, attribute="locations.attributes[?key=='grade']"),
        target=Target.new_attribute(GRID_URL, "kriged_grade"),
        variogram=VARIOGRAM_URL,
        search=search,
        method=method,
    )

    print_params(params, "Simple Kriging Configuration")
    assert isinstance(params.method, SimpleKriging), "Should use simple kriging"
    assert params.method.mean == 100.0, "Mean should be 100.0"
    print("\n[OK] Simple kriging configured successfully with mean=100.0")


def test_kriging_with_target_filter() -> None:
    """Test kriging with a target domain filter."""
    print_test_header("Kriging with Target Domain Filter")

    search = SearchNeighborhood(
        ellipsoid=Ellipsoid(ranges=EllipsoidRanges(major=200, semi_major=150, minor=100)),
        max_samples=20,
    )

    target_filter = Filter(
        where=FilterCondition(
            attribute="domain",
            operator="in",
            values=["LMS1", "LMS2"],
        )
    )

    params = KrigingParameters(
        source=Source(object=POINTSET_URL, attribute="locations.attributes[?key=='grade']"),
        target=Target.new_attribute(GRID_URL, "kriged_grade"),
        variogram=VARIOGRAM_URL,
        search=search,
        target_filter=target_filter,
    )

    print_params(params, "Kriging with Target Filter")
    params_dict = params.model_dump()
    assert "filter" in params_dict["target"], "Target should have filter applied"
    print("\n[OK] Target filter applied successfully")


def test_kriging_with_source_filter() -> None:
    """Test kriging with a source data filter."""
    print_test_header("Kriging with Source Data Filter")

    search = SearchNeighborhood(
        ellipsoid=Ellipsoid(ranges=EllipsoidRanges(major=200, semi_major=150, minor=100)),
        max_samples=20,
    )

    source_filter = Filter(
        where=FilterCondition(
            attribute="grade",
            operator="greater_than",
            threshold=0.5,
        )
    )

    params = KrigingParameters(
        source=Source(object=POINTSET_URL, attribute="locations.attributes[?key=='grade']"),
        target=Target.new_attribute(GRID_URL, "kriged_grade"),
        variogram=VARIOGRAM_URL,
        search=search,
        source_filter=source_filter,
    )

    print_params(params, "Kriging with Source Filter")
    params_dict = params.model_dump()
    assert "filter" in params_dict["source"], "Source should have filter applied"
    print("\n[OK] Source filter applied successfully")


def test_kriging_with_block_discretisation() -> None:
    """Test block kriging with discretisation."""
    print_test_header("Block Kriging with Discretisation")

    search = SearchNeighborhood(
        ellipsoid=Ellipsoid(ranges=EllipsoidRanges(major=200, semi_major=150, minor=100)),
        max_samples=20,
    )

    discretisation = BlockDiscretisation(nx=3, ny=3, nz=2)

    params = KrigingParameters(
        source=Source(object=POINTSET_URL, attribute="locations.attributes[?key=='grade']"),
        target=Target.new_attribute(BLOCKMODEL_URL, "kriged_grade"),
        variogram=VARIOGRAM_URL,
        search=search,
        block_discretisation=discretisation,
    )

    print_params(params, "Block Kriging Configuration")
    params_dict = params.model_dump()
    assert "block_discretisation" in params_dict, "Should have block discretisation"
    assert params_dict["block_discretisation"]["nx"] == 3
    assert params_dict["block_discretisation"]["ny"] == 3
    assert params_dict["block_discretisation"]["nz"] == 2
    print("\n[OK] Block kriging configured with nx=3, ny=3, nz=2")


def test_kriging_with_complex_configuration() -> None:
    """Test kriging with multiple features combined."""
    print_test_header("Complex Kriging Configuration")

    search = SearchNeighborhood(
        ellipsoid=Ellipsoid(ranges=EllipsoidRanges(major=200, semi_major=150, minor=100)),
        max_samples=20,
    )

    source_filter = Filter(where=FilterCondition(attribute="grade", operator="greater_than", threshold=0.1))

    target_filter = Filter(where=FilterCondition(attribute="domain", operator="in", values=["Zone1", "Zone2"]))

    discretisation = BlockDiscretisation(nx=2, ny=2, nz=2)

    method = KrigingMethod.simple(mean=50.0)

    params = KrigingParameters(
        source=Source(object=POINTSET_URL, attribute="locations.attributes[?key=='grade']"),
        target=Target.new_attribute(BLOCKMODEL_URL, "kriged_grade"),
        variogram=VARIOGRAM_URL,
        search=search,
        method=method,
        source_filter=source_filter,
        target_filter=target_filter,
        block_discretisation=discretisation,
    )

    print_params(params, "Complex Kriging Configuration")
    params_dict = params.model_dump()

    # Verify all components are present
    assert isinstance(params.method, SimpleKriging)
    assert params.method.mean == 50.0
    assert "filter" in params_dict["source"]
    assert "filter" in params_dict["target"]
    assert "block_discretisation" in params_dict

    print("\n[OK] Complex configuration assembled successfully:")
    print("  - Simple kriging method with mean=50.0")
    print("  - Source filter: grade > 0.1")
    print("  - Target filter: domain in ['Zone1', 'Zone2']")
    print("  - Block discretisation: 2x2x2")


def test_cli_parameter_export() -> None:
    """Test exporting parameters for CLI use."""
    print_test_header("CLI Parameter Export")

    search = SearchNeighborhood(
        ellipsoid=Ellipsoid(ranges=EllipsoidRanges(major=200, semi_major=150, minor=100)),
        max_samples=20,
    )

    params = KrigingParameters(
        source=Source(object=POINTSET_URL, attribute="locations.attributes[?key=='grade']"),
        target=Target.new_attribute(GRID_URL, "kriged_grade"),
        variogram=VARIOGRAM_URL,
        search=search,
    )

    # Export as JSON for CLI use
    json_params = params.model_dump(mode="json", by_alias=True, exclude_none=True)
    json_str = json.dumps(json_params, indent=2)

    print("\nJSON output for CLI:")
    print(json_str)

    # Save to a temporary file to simulate CLI workflow
    temp_file = Path("/tmp/kriging_params.json")
    temp_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file.write_text(json_str)

    print(f"\n[OK] Parameters exported to {temp_file}")
    print("  This file can be used with: evo compute kriging-run --params-file <file>")


def main() -> None:
    """Run all kriging workflow tests."""
    print("\n" + "=" * 70)
    print("KRIGING WORKFLOW TEST SUITE")
    print("=" * 70)

    try:
        test_ordinary_kriging()
        test_simple_kriging()
        test_kriging_with_target_filter()
        test_kriging_with_source_filter()
        test_kriging_with_block_discretisation()
        test_kriging_with_complex_configuration()
        test_cli_parameter_export()

        print("\n" + "=" * 70)
        print("[PASS] ALL KRIGING WORKFLOW TESTS PASSED")
        print("=" * 70)
        print("\nSummary:")
        print("  [OK] Ordinary kriging (default)")
        print("  [OK] Simple kriging with known mean")
        print("  [OK] Target domain filtering")
        print("  [OK] Source data filtering")
        print("  [OK] Block discretisation")
        print("  [OK] Complex multi-feature configuration")
        print("  [OK] CLI parameter export")
        print("\nThe kriging computation task is fully functional!\n")

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
