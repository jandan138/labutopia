from __future__ import annotations

import numpy as np
import pytest

from tools.labutopia_fluid.fluid_benchmark_contract import EXPECTED_OBSERVATION_COUNT
from tools.labutopia_fluid.newton_only_contract import (
    FAIR_PARTICLE_COUNT,
    SEARCH_EXPLORATION_PARTICLE_COUNT,
    SEARCH_CONFIGURATION_COUNT,
    SCENE_PACK_SCHEMA,
    SOLVER_CATALOG,
    VISUAL_REVIEW_CAMERA_IDS,
    VISUAL_REVIEW_FRAME_INDICES,
    VISUAL_REVIEW_SCHEMA,
    adaptive_cfl_step,
    build_search_schedule,
    residual_stop,
    validate_reoptimized_trajectory,
    validate_scene_pack_manifest,
    validate_visual_review,
)
from tools.labutopia_fluid.newton_trajectory_search import (
    QUALITY_TRAJECTORY_CANDIDATE_COUNT,
    generate_trajectory_candidate,
)
from tools.labutopia_fluid.run_newton_only_solver_search import (
    _resolve_refinement_row,
    _result_rank_key,
)


def _identity_trajectory() -> np.ndarray:
    poses = np.zeros((EXPECTED_OBSERVATION_COUNT, 7), dtype=np.float64)
    poses[:, 0] = np.linspace(0.0, 1.0, EXPECTED_OBSERVATION_COUNT)
    poses[:, 6] = 1.0
    return poses


def test_solver_catalog_contains_ten_distinct_liquid_routes() -> None:
    assert len(SOLVER_CATALOG) == 10
    assert len({solver.solver_id for solver in SOLVER_CATALOG}) == 10
    assert {solver.liquid_model for solver in SOLVER_CATALOG} >= {
        "continuum",
        "weakly_compressible",
        "divergence_free",
        "density_constraint",
        "incompressible_projection",
    }


@pytest.mark.parametrize("solver_id", [solver.solver_id for solver in SOLVER_CATALOG])
def test_every_solver_gets_exact_24_plus_8_search_budget(solver_id: str) -> None:
    schedule = build_search_schedule(solver_id)
    assert len(schedule) == SEARCH_CONFIGURATION_COUNT
    assert sum(row["phase"] == "explore_900" for row in schedule) == 24
    assert sum(row["phase"] == "resolution_refine" for row in schedule) == 8
    assert FAIR_PARTICLE_COUNT == 3600
    assert all(
        row["particle_count"] == SEARCH_EXPLORATION_PARTICLE_COUNT
        for row in schedule[:24]
    )
    assert [row["particle_count"] for row in schedule[24:]] == [
        900,
        1800,
        3600,
        7200,
        900,
        1800,
        3600,
        7200,
    ]


def test_adaptive_cfl_step_exactly_tiles_logical_frame() -> None:
    result = adaptive_cfl_step(
        maximum_speed_m_s=2.0,
        sound_speed_m_s=4.0,
        support_radius_m=0.02,
        cfl=0.4,
    )
    assert result["substeps"] == 25
    assert result["dt_s"] * result["substeps"] == pytest.approx(1.0 / 30.0)


def test_adaptive_cfl_step_fails_if_minimum_is_insufficient() -> None:
    with pytest.raises(ValueError, match="below_minimum"):
        adaptive_cfl_step(
            maximum_speed_m_s=1000.0,
            support_radius_m=0.001,
            minimum_dt_s=1.0 / 1000.0,
        )


def test_residual_stop_records_actual_iterations() -> None:
    result = residual_stop(
        [1.0, 0.1, 0.009, 0.001],
        tolerance=0.01,
        maximum_iterations=10,
        minimum_iterations=2,
    )
    assert result["converged"] is True
    assert result["actual_iterations"] == 3
    assert result["final_residual"] == pytest.approx(0.009)


def test_trajectory_reoptimization_keeps_endpoints_and_motion_envelope() -> None:
    reference = _identity_trajectory()
    result = validate_reoptimized_trajectory(reference.copy(), reference)
    assert result["passed"] is True
    changed = reference.copy()
    changed[-1, 0] += 0.01
    with pytest.raises(ValueError, match="end_changed"):
        validate_reoptimized_trajectory(changed, reference)


def test_visual_review_requires_exact_eight_by_two_review_set() -> None:
    value = {
        "schema": VISUAL_REVIEW_SCHEMA,
        "frame_indices": list(VISUAL_REVIEW_FRAME_INDICES),
        "camera_ids": list(VISUAL_REVIEW_CAMERA_IDS),
        "checks": {
            "no_explosion_or_nonfinite": True,
            "no_obvious_cup_or_table_penetration": True,
            "no_sustained_scattering_outside_region": True,
            "meaningful_fluid_in_target_at_end": True,
        },
        "passed": True,
    }
    assert validate_visual_review(value)["passed"] is True
    value["checks"]["meaningful_fluid_in_target_at_end"] = False
    with pytest.raises(ValueError, match="pass_inconsistent"):
        validate_visual_review(value)


@pytest.mark.parametrize("candidate_index", range(QUALITY_TRAJECTORY_CANDIDATE_COUNT))
def test_trajectory_candidates_preserve_exact_global_endpoints(candidate_index: int) -> None:
    reference = _identity_trajectory()
    candidate, record = generate_trajectory_candidate(reference, candidate_index)
    np.testing.assert_array_equal(candidate[0], reference[0])
    np.testing.assert_array_equal(candidate[-1], reference[-1])
    assert record["accepted_scale"] >= 0.0
    assert record["motion_envelope_validation"]["passed"] is True


def test_scene_pack_requires_observed_fixed_grasp_semantics() -> None:
    camera = {
        "fx": 100.0,
        "fy": 100.0,
        "cx": 64.0,
        "cy": 64.0,
        "resolution": [128, 128],
    }
    value = {
        "schema": SCENE_PACK_SCHEMA,
        "observation_count": EXPECTED_OBSERVATION_COUNT,
        "cameras": {camera_id: dict(camera) for camera_id in VISUAL_REVIEW_CAMERA_IDS},
        "fixed_grasp": {
            "semantics": (
                "row_matrix_source_world_equals_source_to_gripper_times_gripper_world"
            ),
            "fixed_grasp_start_observation_index": 419,
            "source_to_gripper_row_matrix": np.eye(4).tolist(),
        },
    }
    assert validate_scene_pack_manifest(value)["fixed_grasp_start_observation_index"] == 419
    value["fixed_grasp"]["fixed_grasp_start_observation_index"] = -1
    with pytest.raises(ValueError, match="fixed_grasp_index_invalid"):
        validate_scene_pack_manifest(value)


def test_search_ranking_prefers_quality_after_numeric_stability() -> None:
    def result(target: float, spill: float, mean_ms: float) -> dict:
        return {
            "stability": {"passed": True},
            "quality": {
                "numeric_passed": False,
                "final_score": {
                    "target_fraction": target,
                    "tabletop_spill_fraction": spill,
                    "below_table_fraction": 0.0,
                    "nonfinite_fraction": 0.0,
                },
            },
            "timing": {"physics_logical_frame": {"mean_ms": mean_ms}},
        }

    useful = result(0.6, 0.3, 20.0)
    fast_but_spilled = result(0.01, 0.98, 1.0)
    assert _result_rank_key(useful) > _result_rank_key(fast_but_spilled)


def test_search_ranking_rejects_unstable_speed_record() -> None:
    def result(*, stable: bool, mean_ms: float) -> dict:
        return {
            "stability": {"passed": stable},
            "quality": {
                "numeric_passed": False,
                "final_score": {
                    "target_fraction": 0.0,
                    "tabletop_spill_fraction": 1.0,
                    "below_table_fraction": 0.0 if stable else 0.1,
                    "nonfinite_fraction": 0.0,
                },
            },
            "timing": {"physics_logical_frame": {"mean_ms": mean_ms}},
        }

    assert _result_rank_key(result(stable=True, mean_ms=20.0)) > _result_rank_key(
        result(stable=False, mean_ms=1.0)
    )


def test_refinement_row_inherits_selected_exploration_configuration() -> None:
    refinement = build_search_schedule("labutopia_wcsph")[24]
    selected = {
        "configuration": {
            "configuration_id": "labutopia_wcsph.explore.07",
            "trajectory_candidate": 1,
            "substep_tier": 8,
            "iteration_tier": 1,
            "material_tier": 0,
        }
    }
    resolved = _resolve_refinement_row(refinement, selected)
    assert resolved["particle_count"] == 900
    assert resolved["trajectory_candidate"] == 1
    assert resolved["substep_tier"] == 8
    assert resolved["selected_from_explore_configuration_id"].endswith(".07")
