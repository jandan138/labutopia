from __future__ import annotations

import pytest

from tools.labutopia_fluid import promote_visible_sync_rtx50_report as promotion


def _result() -> dict:
    return {
        "schema": "labutopia.isaac41.liquid0812_async_rtx_result.v3",
        "lane": "headless-product",
        "configuration": {
            "camera": {"policy": "trajectory-envelope"},
            "source_driver": "physx-kinematic-target",
        },
        "acceptance": {
            "physics": {"source_pose_tracking": True},
            "performance_passed": False,
            "physics_passed": False,
        },
        "artifacts": {"full_video": {"checks": {"frame_count": True}}},
    }


def _audit() -> dict:
    return {
        "lane": "headless-product",
        "status": "passed",
        "pose_sync": {"passed": True},
        "pixel_sync": {"passed": True},
    }


def test_promotion_allows_performance_and_fluid_no_go_after_sync_passes() -> None:
    promotion._eligible(_result(), _audit(), "headless-product")


@pytest.mark.parametrize("gate", ["pose", "pixel"])
def test_promotion_fails_closed_on_visible_sync_gate(gate: str) -> None:
    audit = _audit()
    audit[f"{gate}_sync"]["passed"] = False
    with pytest.raises(RuntimeError, match=f"audit_{gate}_failed"):
        promotion._eligible(_result(), audit, "headless-product")
