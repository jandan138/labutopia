from __future__ import annotations

import numpy as np

from tools.labutopia_fluid.run_wcsph_scaling_matrix import (
    _descendant_pids,
    _is_completed_result,
    _is_negligible_swiftshader_process,
    _runtime_parity,
    _summaries,
)


def test_descendant_pids_contains_current_process() -> None:
    import os

    assert os.getpid() in _descendant_pids(os.getpid())


def test_only_tiny_swiftshader_browser_is_negligible() -> None:
    assert _is_negligible_swiftshader_process(
        {
            "process_name": "/chrome --type=gpu-process --use-angle=swiftshader-webgl",
            "used_memory_mib": 24,
        }
    )
    assert not _is_negligible_swiftshader_process(
        {
            "process_name": "/chrome --type=gpu-process --use-angle=swiftshader-webgl",
            "used_memory_mib": 64,
        }
    )
    assert not _is_negligible_swiftshader_process(
        {"process_name": "/usr/bin/python CUDA", "used_memory_mib": 24}
    )


def _record(lane: str, path: str, positions: np.ndarray) -> dict:
    np.savez_compressed(path, particle_positions=positions)
    return {
        "lane": lane,
        "particle_count": positions.shape[1],
        "repeat_index": 0,
        "status": "completed",
        "result": {
            "particle_radius_m": 0.01,
            "quality": {
                "final_score": {
                    "target_fraction": 0.5,
                    "tabletop_spill_fraction": 0.4,
                }
            },
            "artifacts": {"all_particle_frames": {"path": path}},
        },
    }


def test_runtime_parity_accepts_identical_device_results(tmp_path) -> None:
    positions = np.zeros((3, 900, 3), dtype=np.float32)
    records = [
        _record("newton140", str(tmp_path / "newton.npz"), positions),
        _record("isaac601", str(tmp_path / "isaac.npz"), positions.copy()),
    ]
    parity = _runtime_parity(records)
    assert len(parity) == 1
    assert parity[0]["passed"] is True
    assert parity[0]["position_rmse_m"] == 0.0


def test_summaries_keep_solver_routes_separate() -> None:
    records = []
    for solver_id, mean_ms in (("labutopia_dfsph", 7.0), ("labutopia_wcsph", 9.0)):
        records.append(
            {
                "lane": "newton140",
                "solver_id": solver_id,
                "particle_count": 900,
                "status": "completed",
                "result": {
                    "timing": {
                        "physics_logical_frame": {"mean_ms": mean_ms},
                        "simulation_chain_frame": {"mean_ms": mean_ms},
                    },
                    "stability": {"passed": True},
                    "quality": {
                        "final_score": {
                            "target_fraction": 0.5,
                            "tabletop_spill_fraction": 0.4,
                        }
                    },
                },
            }
        )
    rows = _summaries(records)
    assert [row["solver_id"] for row in rows] == [
        "labutopia_dfsph",
        "labutopia_wcsph",
    ]
    assert [row["physics_mean_ms_across_repeats"] for row in rows] == [7.0, 9.0]


def test_failed_runtime_result_is_not_misclassified_as_completed() -> None:
    assert _is_completed_result({"status": "failed_runtime", "message": "compile failed"}) is False
    assert (
        _is_completed_result(
            {
                "status": "performance_valid_quality_unqualified",
                "timing": {},
                "stability": {},
                "quality": {},
                "artifacts": {},
            }
        )
        is True
    )
