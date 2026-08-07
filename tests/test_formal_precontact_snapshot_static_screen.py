from __future__ import annotations

import math

from utils import formal_precontact_event0_replay as replay
from utils import formal_precontact_event0_snapshot_replay as snapshot
from utils import formal_precontact_snapshot_static_screen as static_screen
from utils import formal_precontact_usd_dependency_closure as dependency_closure


ARM = "/World/Franka/panda_link7/geometry/panda_link7"
LEFT = "/World/Franka/panda_leftfinger/geometry/panda_leftfinger"
RIGHT = "/World/Franka/panda_rightfinger/geometry/panda_rightfinger"
MESH = "/World/beaker2/mesh"
WRAPPER = "/World/beaker2/FluidSafeWrapperCanonical/Wall_r0_00"
TABLE = "/World/table/surface/mesh"


def _scope() -> dict:
    return {
        "blocking_pairs": [
            sorted([ARM, MESH]),
            sorted([ARM, WRAPPER]),
            sorted([LEFT, TABLE]),
            sorted([RIGHT, TABLE]),
        ],
        "allowed_source_shell_pairs": [
            sorted([LEFT, MESH]),
            sorted([RIGHT, MESH]),
        ],
    }


def _projection(*, potential: bool = False) -> dict:
    target = [0.1] * 7 + [0.04, 0.04]
    results = [
        {
            "pair": pair,
            "classification": "BLOCKING",
            "status": "POTENTIAL_OVERLAP_OR_MARGIN" if potential and pair == sorted([ARM, MESH]) else "CLEAR",
            "lower_bound_m": 0.0 if potential and pair == sorted([ARM, MESH]) else 0.01,
        }
        for pair in _scope()["blocking_pairs"]
    ]
    results.extend(
        {
            "pair": pair,
            "classification": "ALLOWED_SOURCE_SHELL_FINGER",
            "status": "CLEAR",
            "lower_bound_m": 0.01,
        }
        for pair in _scope()["allowed_source_shell_pairs"]
    )
    return {
        "schema_version": 1,
        "authority": static_screen.PROJECTION_AUTHORITY,
        "controller_event": 0,
        "resolved_position_target": target,
        "resolved_position_target_sha256": replay.canonical_json_sha256(target),
        "source_collider_closure_sha256": "a" * 64,
        "aabb_numerical_margin_m": 1.0e-6,
        "pair_results": results,
    }


def test_event0_static_projection_accepts_all_clear_pairs():
    evaluation = static_screen.evaluate_event0_static_projection(_scope(), _projection())

    assert evaluation["decision"] == static_screen.CLEAR
    assert evaluation["required_pair_count"] == 6
    assert evaluation["potential_pair_result_count"] == 0


def test_event0_static_projection_reports_potential_overlap_as_no_go():
    evaluation = static_screen.evaluate_event0_static_projection(
        _scope(), _projection(potential=True)
    )

    assert evaluation["decision"] == static_screen.NO_GO
    assert evaluation["potential_pair_result_count"] == 1
    assert evaluation["first_potential_pair_result"]["pair"] == sorted([ARM, MESH])


def test_event0_static_projection_rejects_a_clear_status_below_margin():
    projection = _projection()
    projection["pair_results"][0]["lower_bound_m"] = 0.0

    evaluation = static_screen.evaluate_event0_static_projection(_scope(), projection)

    assert evaluation == {
        "decision": static_screen.SAFETY_ABORT,
        "validation_error": "formal_snapshot_static_projection_invalid",
    }


def test_fixed_mount_baseline_comparison_identifies_an_invariant_overlap():
    matrix = [
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        -0.4,
        0.0,
        0.71,
        1.0,
    ]
    comparison = {
        "schema_version": 1,
        "authority": static_screen.BASELINE_COMPARISON_AUTHORITY,
        "pair": sorted([ARM.replace("panda_link7", "panda_link0"), TABLE]),
        "aabb_numerical_margin_m": 1.0e-6,
        "baseline_lower_bound_m": 0.0,
        "event0_lower_bound_m": 0.0,
        "axis_signed_separation_m": [-0.1, -0.1, 0.0],
        "baseline_link0_collider_world_matrix": matrix,
        "event0_link0_collider_world_matrix": matrix,
    }

    evaluation = static_screen.evaluate_fixed_mount_baseline_comparison(comparison)

    assert evaluation["decision"] == static_screen.BASELINE_FIXED_MOUNT_SURFACE_TOUCH
    assert evaluation["link0_matrix_max_abs_difference"] == 0.0


def test_link0_table_geometry_audit_stays_unresolved_without_cooked_shape_export():
    audit = {
        "schema_version": 1,
        "authority": static_screen.LINK0_TABLE_GEOMETRY_AUDIT_AUTHORITY,
        "pair": sorted([ARM.replace("panda_link7", "panda_link0"), TABLE]),
        "authored_filtered_pair_paths": [],
        "colliders": [
            {
                "path": path,
                "type_name": "Mesh",
                "collision_enabled": True,
                "mesh_collision_api_applied": True,
                "physics_approximation": "none",
                "mesh_point_count": 8,
                "mesh_triangle_count": 12,
                "cooked_aabb_local_min_m": [-0.1, -0.1, -0.1],
                "cooked_aabb_local_max_m": [0.1, 0.1, 0.1],
                "cooked_volume_m3": 0.008,
                "cooked_aabb_volume_m3": 0.008,
                "world_aabb_min_m": [-0.1, -0.1, -0.1],
                "world_aabb_max_m": [0.1, 0.1, 0.1],
            }
            for path in sorted([ARM.replace("panda_link7", "panda_link0"), TABLE])
        ],
    }

    evaluation = static_screen.evaluate_link0_table_geometry_audit(audit)

    assert evaluation == {
        "decision": static_screen.LINK0_TABLE_GEOMETRY_UNRESOLVED,
        "pair": sorted([ARM.replace("panda_link7", "panda_link0"), TABLE]),
        "authored_filtered_pair_count": 0,
        "reason": "cooked_shape_representation_not_exported",
    }


def test_mounting_alignment_derives_contact_and_clearance_heights_from_authored_support():
    alignment = {
        "schema_version": 1,
        "authority": static_screen.LINK0_TABLE_MOUNTING_ALIGNMENT_AUTHORITY,
        "pair": sorted([ARM.replace("panda_link7", "panda_link0"), TABLE]),
        "configured_robot_position_m": [-0.4, 0.0, 0.71],
        "observed_link0_collider_origin_m": [-0.4, 0.0, 0.71],
        "link0_authored_mesh_world_bottom_z_m": 0.71,
        "link0_authored_mesh_world_xy_bounds_m": [-0.55, -0.1, -0.33, 0.1],
        "link0_mesh_point_count": 8,
        "table_mesh_triangle_count": 12,
        "table_support_samples": [
            {"xy_m": [x, y], "top_z_m": 0.773}
            for x in (-0.52, -0.48, -0.44, -0.4, -0.36)
            for y in (-0.07, -0.035, 0.0, 0.035, 0.07)
        ],
        "required_clearance_m": 0.005,
    }

    evaluation = static_screen.evaluate_link0_table_mounting_alignment(alignment)

    assert evaluation["decision"] == static_screen.LINK0_TABLE_MOUNTING_EMBEDDED
    assert evaluation["table_support_sample_count"] == 25
    assert math.isclose(evaluation["current_authored_mesh_penetration_m"], 0.063)
    assert math.isclose(evaluation["surface_contact_robot_position_z_m"], 0.773)
    assert math.isclose(evaluation["static_clearance_robot_position_z_m"], 0.778)


def test_mounting_alignment_does_not_call_subclearance_a_clear_mount():
    alignment = {
        "schema_version": 1,
        "authority": static_screen.LINK0_TABLE_MOUNTING_ALIGNMENT_AUTHORITY,
        "pair": sorted([ARM.replace("panda_link7", "panda_link0"), TABLE]),
        "configured_robot_position_m": [-0.4, 0.0, 0.71],
        "observed_link0_collider_origin_m": [-0.4, 0.0, 0.71],
        "link0_authored_mesh_world_bottom_z_m": 0.775,
        "link0_authored_mesh_world_xy_bounds_m": [-0.55, -0.1, -0.33, 0.1],
        "link0_mesh_point_count": 8,
        "table_mesh_triangle_count": 12,
        "table_support_samples": [
            {"xy_m": [x, y], "top_z_m": 0.773}
            for x in (-0.52, -0.48, -0.44, -0.4, -0.36)
            for y in (-0.07, -0.035, 0.0, 0.035, 0.07)
        ],
        "required_clearance_m": 0.005,
    }

    evaluation = static_screen.evaluate_link0_table_mounting_alignment(alignment)

    assert evaluation["decision"] == static_screen.LINK0_TABLE_MOUNTING_INSUFFICIENT_CLEARANCE


def test_fixed_mount_filter_derives_an_active_scope_with_only_link0_table_removed():
    profile = {
        "authority": snapshot.FIXED_MOUNT_PROFILE_AUTHORITY,
        "schema_version": 1,
        "profile_id": "v7_link0_table_surface_mount_filter_v1",
        "profile_path": "config/formal_precontact_fixed_mount_filter_v1.json",
        "profile_sha256": "a" * 64,
        "robot_position_m": [-0.4, 0.0, 0.772761],
        "filter": {
            "overlay_path": (
                "assets/chemistry_lab/lab_001_fluid_eval/"
                "lab_001_v7_link0_table_fixed_mount_filter_v1.usda"
            ),
            "overlay_sha256": "b" * 64,
            "author_collider_path": ARM.replace("panda_link7", "panda_link0"),
            "target_collider_path": TABLE,
        },
    }
    filter_record = {
        "authority": snapshot.FIXED_MOUNT_RUNTIME_FILTER_AUTHORITY,
        "profile_sha256": profile["profile_sha256"],
        "author_collider_path": profile["filter"]["author_collider_path"],
        "target_collider_path": profile["filter"]["target_collider_path"],
        "filtered_pair": sorted(
            [
                profile["filter"]["author_collider_path"],
                profile["filter"]["target_collider_path"],
            ]
        ),
        "authored_filtered_pair_paths": [
            [
                profile["filter"]["author_collider_path"],
                profile["filter"]["target_collider_path"],
            ]
        ],
        "robot_filtered_pair_paths": [
            [
                profile["filter"]["author_collider_path"],
                profile["filter"]["target_collider_path"],
            ]
        ],
        "collision_group_membership_paths": [],
    }
    full_scope = {
        "blocking_pairs": [
            sorted([ARM.replace("panda_link7", "panda_link0"), TABLE]),
            sorted([ARM, TABLE]),
        ],
        "allowed_source_shell_pairs": [sorted([LEFT, MESH])],
    }

    active_scope = static_screen.build_fixed_mount_filtered_screen_scope(
        full_scope,
        fixed_mount_profile=profile,
        fixed_mount_filter=filter_record,
    )

    assert active_scope["excluded_blocking_pairs"] == [
        sorted([ARM.replace("panda_link7", "panda_link0"), TABLE])
    ]
    assert active_scope["blocking_pairs"] == [sorted([ARM, TABLE])]
    assert active_scope["full_blocking_pair_count"] == 2
    assert active_scope["active_blocking_pair_count"] == 1


def test_fixed_mount_handoff_provenance_requires_the_preflight_binding():
    provenance = {
        "formal_decision": snapshot.PASS,
        "report_sha256": "1" * 64,
        "manifest_sha256": "2" * 64,
        "child_report_sha256": "3" * 64,
        "runtime_receipt_sha256": "4" * 64,
        "execution_request_sha256": "5" * 64,
        "trace_sha256": "6" * 64,
        "source_sha256": "7" * 64,
        "usd_dependency_preflight": dependency_closure.build_preflight_binding(
            preflight_run_dir="artifacts/runs/formal-usd-dependency-preflight-001",
            input_sha256="8" * 64,
            closure_manifest_sha256="9" * 64,
            closure_file_sha256="a" * 64,
            preflight_report_sha256="b" * 64,
            preflight_run_manifest_sha256="c" * 64,
            preflight_runtime_receipt_sha256="d" * 64,
        ),
    }

    normalized = static_screen._formal_provenance(provenance, fixed_mount=True)

    assert normalized["usd_dependency_preflight"] == provenance["usd_dependency_preflight"]
    try:
        static_screen._formal_provenance(
            {key: value for key, value in provenance.items() if key != "usd_dependency_preflight"},
            fixed_mount=True,
        )
    except ValueError as exc:
        assert str(exc) == "formal_snapshot_static_provenance_invalid"
    else:
        raise AssertionError("fixed-mount provenance unexpectedly accepted no preflight binding")
