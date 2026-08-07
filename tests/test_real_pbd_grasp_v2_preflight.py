from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.labutopia_fluid import run_real_pbd_grasp_v2_preflight as preflight
from tools.labutopia_fluid import run_real_pbd_grasp_v2_g0_geometry as g0_geometry


REPO_ROOT = Path(__file__).resolve().parents[1]


def _grasp_topology(**changes):
    topology = {
        "source_root_path": "/World/beaker2",
        "source_external_shell_path": "/World/beaker2/mesh",
        "source_parent_dynamic": True,
        "source_parent_kinematic": False,
        "source_external_shell_collision_enabled": True,
        "source_mass_authority": "parent",
        "wrapper_path": "/World/beaker2/FluidSafeWrapperCanonical",
        "wrapper_collider_count": 145,
        "expected_wrapper_collider_count": 145,
        "source_robot_filtered_pairs": [],
        "finger_external_shell_pairs": [
            ["/World/Franka/panda_leftfinger", "/World/beaker2/mesh"],
            ["/World/Franka/panda_rightfinger", "/World/beaker2/mesh"],
        ],
        "finger_wrapper_pairs": [],
    }
    topology.update(changes)
    return topology


def test_grasp_topology_accepts_external_shell_and_particle_wrapper_split():
    result = preflight.evaluate_grasp_topology_contract(_grasp_topology())

    assert result["passed"] is True
    assert result["failures"] == []
    assert result["grasp_contact_surface"] == "/World/beaker2/mesh"
    assert result["particle_wrapper"] == "/World/beaker2/FluidSafeWrapperCanonical"


def test_grasp_topology_binds_composed_robot_asset_identity():
    result = preflight.evaluate_grasp_topology_contract(
        _grasp_topology(
            robot_asset_path="/repo/assets/robots/Franka.usd",
            robot_asset_sha256="a" * 64,
        )
    )

    assert result["passed"] is True
    assert result["robot_asset_path"] == "/repo/assets/robots/Franka.usd"
    assert result["robot_asset_sha256"] == "a" * 64


@pytest.mark.parametrize(
    ("changes", "failure"),
    [
        (
            {"source_external_shell_collision_enabled": False},
            "external_shell_collision_disabled",
        ),
        ({"source_parent_kinematic": True}, "source_parent_kinematic"),
        ({"wrapper_collider_count": 144}, "wrapper_collider_inventory_mismatch"),
        (
            {
                "finger_wrapper_pairs": [
                    ["/World/Franka/panda_leftfinger", "/World/beaker2/FluidSafeWrapperCanonical/Wall_r0_00"]
                ]
            },
            "finger_wrapper_contact_route",
        ),
        (
            {
                "source_robot_filtered_pairs": [
                    ["/World/beaker2/mesh", "/World/Franka/panda_leftfinger"]
                ]
            },
            "source_robot_collision_filter",
        ),
    ],
)
def test_grasp_topology_rejects_unsafe_routes(changes, failure):
    result = preflight.evaluate_grasp_topology_contract(_grasp_topology(**changes))

    assert result["passed"] is False
    assert failure in result["failures"]


def test_static_preflight_seals_authored_zero_particle_mass_as_g0_no_go():
    report = preflight.build_static_preflight_report(
        asset_path=preflight.DEFAULT_ASSET,
        fixture={
            "source_dry_mass_kg": 0.02,
            "particle_density_kg_m3": 0.0,
            "particle_mass_kg": 0.0,
            "particle_count": 3600,
            "wrapper_collider_count": 145,
            "wrapper_collider_paths": ["/World/beaker2/FluidSafeWrapperCanonical/panel_000"],
        },
    )

    assert report["asset_path"] == str(preflight.DEFAULT_ASSET.resolve())
    assert report["evaluation"]["g0_decision"] == "G0_NO_GO"
    assert report["evaluation"]["g3_g4_filled_load_authorized"] is False
    assert "authored_particle_mass_and_density_nonpositive" in report["evaluation"][
        "no_go_reasons"
    ]


def test_static_preflight_surfaces_grasp_topology_decision():
    report = preflight.build_static_preflight_report(
        asset_path=preflight.DEFAULT_ASSET,
        fixture={
            "source_dry_mass_kg": 0.02,
            "particle_density_kg_m3": 1.0,
            "particle_mass_kg": 0.001,
            "particle_count": 3600,
            "wrapper_collider_count": 145,
            "wrapper_collider_paths": [],
            "grasp_topology": _grasp_topology(),
        },
    )

    assert report["grasp_topology"]["passed"] is True


def test_static_preflight_preserves_topology_no_go_reason():
    report = preflight.build_static_preflight_report(
        asset_path=preflight.DEFAULT_ASSET,
        fixture={
            "source_dry_mass_kg": 0.02,
            "particle_density_kg_m3": 1.0,
            "particle_mass_kg": 0.001,
            "particle_count": 3600,
            "wrapper_collider_count": 145,
            "wrapper_collider_paths": [],
            "grasp_topology": _grasp_topology(
                source_external_shell_collision_enabled=False
            ),
        },
    )

    assert report["grasp_topology"]["passed"] is False
    assert "external_shell_collision_disabled" in report["grasp_topology"]["failures"]


def test_preflight_create_only_writer_never_replaces_existing_results(tmp_path):
    output = tmp_path / "report.json"
    preflight.atomic_create_bytes(output, b'{"first":true}\n')

    with pytest.raises(FileExistsError, match="real_pbd_preflight_output_exists"):
        preflight.atomic_create_bytes(output, b'{"replacement":true}\n')
    assert json.loads(output.read_text(encoding="utf-8")) == {"first": True}


def test_preflight_failure_still_emits_a_typed_g0_no_go_artifact(tmp_path):
    out_dir = tmp_path / "missing-asset-output"

    assert preflight.run_preflight(
        asset_path=tmp_path / "missing.usda", out_dir=out_dir
    ) == 2

    report = json.loads((out_dir / preflight.REPORT_BASENAME).read_text(encoding="utf-8"))
    artifact = json.loads(
        (out_dir / preflight.G0_ARTIFACT_BASENAME).read_text(encoding="utf-8")
    )
    assert report["authority"] == "real_pbd_static_fixture_preflight_error_v1"
    assert report["decision"] == "G0_NO_GO"
    assert artifact["decision"] == "G0_NO_GO"


def test_preflight_runner_stays_outside_isaac_runtime():
    source = Path(preflight.__file__).read_text(encoding="utf-8")

    for forbidden in ("import isaacsim", "from isaacsim", "import omni", "from omni"):
        assert forbidden not in source


def test_g0_geometry_collapses_unexpected_hits_to_top_level_scene_roots():
    assert g0_geometry._top_level_collision_roots(
        [
            "/World/Cube",
            "/World/beaker1/FluidSafeWrapperCanonical/Wall_r0_07",
            "/World/beaker1/mesh",
            "/World/Cube",
        ]
    ) == ["/World/Cube", "/World/beaker1"]


def test_hidden_cube_collision_treatment_only_targets_cube_collision():
    overlay = g0_geometry.HIDDEN_CUBE_OVERLAY
    audit = g0_geometry.audit_hidden_cube_collision_treatment(overlay)

    assert overlay.is_file()
    assert audit["collision_disabled_path"] == "/World/Cube"
    assert audit["changed_paths"] == ["/World/Cube"]
    assert audit["changed_attributes"] == ["physics:collisionEnabled"]
    assert audit["removal_count"] == 0
    assert audit["visibility_opinion_count"] == 0


def test_g0_geometry_v7_cube_only_overlay_profile_is_explicit(tmp_path):
    default_args = g0_geometry.parse_args(["--out-dir", str(tmp_path / "legacy")])
    v7_args = g0_geometry.parse_args(
        [
            "--out-dir",
            str(tmp_path / "v7"),
            "--overlay-profile",
            g0_geometry.V7_CUBE_ONLY_OVERLAY_PROFILE,
        ]
    )

    assert default_args.overlay_profile == g0_geometry.LEGACY_OVERLAY_PROFILE
    assert v7_args.overlay_profile == g0_geometry.V7_CUBE_ONLY_OVERLAY_PROFILE

    legacy_profile = g0_geometry.resolve_overlay_profile(default_args.overlay_profile)
    assert [item["id"] for item in legacy_profile["overlay_stack"]] == [
        "explicit_contact_offsets",
        "hidden_cube_collision_disable",
    ]
    profile = g0_geometry.resolve_overlay_profile(v7_args.overlay_profile)
    assert profile["physics_scene_dt_reset_parity"] == "NOT_CLAIMED"
    assert [item["id"] for item in profile["overlay_stack"]] == [
        "hidden_cube_collision_disable"
    ]
    source_paths = g0_geometry._source_paths(profile)
    assert g0_geometry.OFFSET_OVERLAY.resolve() not in source_paths
    assert g0_geometry.HIDDEN_CUBE_OVERLAY.resolve() in source_paths
    assert g0_geometry.V9_DIAGNOSTIC_CONFIG.resolve() in source_paths
    assert g0_geometry.V9_DIAGNOSTIC_RUNNER.resolve() in source_paths

    binding = g0_geometry._v9_diagnostic_config_binding(profile)
    assert binding["native_pick_treatment"]["authority"] == "g0_native_expert_pick_v9"
    assert binding["asset_sha256"] == g0_geometry.sha256_file(g0_geometry.DEFAULT_ASSET)
    assert binding["robot_asset_sha256"] == g0_geometry.sha256_file(
        g0_geometry.ROBOT_ASSET
    )


def test_g0_geometry_rejects_child_overlay_profile_mismatch():
    expected = g0_geometry.resolve_overlay_profile(
        g0_geometry.V7_CUBE_ONLY_OVERLAY_PROFILE
    )
    expected_sha256 = g0_geometry.canonical_json_sha256(expected)

    assert g0_geometry.require_child_overlay_profile(
        {
            "fixture": {
                "overlay_profile": expected,
                "overlay_profile_sha256": expected_sha256,
            }
        },
        expected,
    ) == expected

    with pytest.raises(RuntimeError, match="g0_geometry_child_overlay_profile_mismatch"):
        g0_geometry.require_child_overlay_profile(
            {
                "fixture": {
                    "overlay_profile": g0_geometry.resolve_overlay_profile(
                        g0_geometry.LEGACY_OVERLAY_PROFILE
                    )
                }
            },
            expected,
        )

    with pytest.raises(RuntimeError, match="g0_geometry_child_overlay_profile_mismatch"):
        g0_geometry.require_child_overlay_profile(
            {
                "fixture": {
                    "overlay_profile": expected,
                    "overlay_profile_sha256": "0" * 64,
                }
            },
            expected,
        )


def test_g0_geometry_incomplete_full_robot_scope_produces_a_no_go_sweep_witness():
    witness = g0_geometry._swept_clearance_witness(
        app=None,
        stage=None,
        queries={},
        role_paths={
            "source_external_shell_paths": ["/World/beaker2/mesh"],
            "source_internal_wrapper_paths": [],
            "support_collider_paths": [],
            "hand_collider_paths": ["/World/Franka/panda_hand/collider"],
            "finger_pad_collider_paths": {
                "left": ["/World/Franka/panda_leftfinger/collider"],
                "right": ["/World/Franka/panda_rightfinger/collider"],
            },
        },
        offsets={"records": {}},
    )

    assert witness["authority"] == "real_pbd_g0_candidate_sweep_set_v1"
    assert witness["status"] == "NOT_RUN"
    assert witness["reason"] == "g0_geometry_full_robot_scope_invalid"
    assert witness["selected"] is None
    assert witness["candidates"] == []
    assert witness["passing_candidate_ids"] == []


def test_g0_full_robot_scope_blocks_wrapper_table_beaker1_and_nonfinger_mesh_pairs():
    role_paths = {
        "source_external_shell_paths": ["/World/beaker2/mesh"],
        "source_internal_wrapper_paths": ["/World/beaker2/wrapper"],
        "support_collider_paths": ["/World/table/surface/mesh"],
        "beaker1_collider_paths": ["/World/beaker1/mesh"],
        "full_robot_collider_paths": [
            "/World/Franka/panda_hand/collider",
            "/World/Franka/panda_leftfinger/collider",
            "/World/Franka/panda_link7/collider",
            "/World/Franka/panda_rightfinger/collider",
        ],
        "finger_pad_collider_paths": {
            "left": ["/World/Franka/panda_leftfinger/collider"],
            "right": ["/World/Franka/panda_rightfinger/collider"],
        },
    }

    scope = g0_geometry.build_full_robot_static_collision_scope(role_paths)

    assert scope["allowed_source_shell_pairs"] == [
        ["/World/Franka/panda_leftfinger/collider", "/World/beaker2/mesh"],
        ["/World/Franka/panda_rightfinger/collider", "/World/beaker2/mesh"],
    ]
    assert ["/World/Franka/panda_hand/collider", "/World/beaker2/mesh"] in scope[
        "blocking_pairs"
    ]
    assert ["/World/Franka/panda_link7/collider", "/World/beaker2/mesh"] in scope[
        "blocking_pairs"
    ]
    for target in (
        "/World/beaker2/wrapper",
        "/World/table/surface/mesh",
        "/World/beaker1/mesh",
    ):
        assert ["/World/Franka/panda_leftfinger/collider", target] in scope[
            "blocking_pairs"
        ]
        assert ["/World/Franka/panda_rightfinger/collider", target] in scope[
            "blocking_pairs"
        ]


def test_g0_geometry_stops_before_invalid_tool_center_translation_for_full_robot_scope():
    role_paths = {
        "source_external_shell_paths": ["/World/beaker2/mesh"],
        "source_internal_wrapper_paths": ["/World/beaker2/wrapper"],
        "support_collider_paths": ["/World/table/surface/mesh"],
        "beaker1_collider_paths": ["/World/beaker1/mesh"],
        "full_robot_collider_paths": [
            "/World/Franka/panda_hand/collider",
            "/World/Franka/panda_leftfinger/collider",
            "/World/Franka/panda_rightfinger/collider",
        ],
        "finger_pad_collider_paths": {
            "left": ["/World/Franka/panda_leftfinger/collider"],
            "right": ["/World/Franka/panda_rightfinger/collider"],
        },
        "hand_collider_paths": ["/World/Franka/panda_hand/collider"],
    }

    witness = g0_geometry._swept_clearance_witness(
        app=None,
        stage=None,
        queries={},
        role_paths=role_paths,
        offsets={"records": {}},
    )

    assert witness["status"] == "NOT_RUN"
    assert witness["reason"] == "g0_geometry_full_robot_fk_sweep_required"
    assert witness["selected"] is None
    assert witness["full_robot_static_collision_scope"]["blocking_pairs"]


def test_g0_geometry_has_no_finger_only_semantics():
    source = Path(g0_geometry.__file__).read_text(encoding="utf-8")

    assert "finger_only_" not in source


def test_g0_geometry_keeps_raw_direct_contact_separate_from_static_geometry_verdict():
    summary = g0_geometry.raw_direct_contact_summary()

    assert summary == {
        "authority": "real_pbd_g0_raw_direct_contact_summary_v1",
        "status": "NOT_COLLECTED",
        "reason": "static_geometry_runner_has_no_runtime_contact_observer",
        "does_not_determine_geometry_verdict": True,
    }


def test_g0_geometry_raw_witness_never_claims_default_offset_clearance():
    sweep = {
        "candidates": [
            {
                "candidate": {
                    "id": "raw_candidate_01",
                    "lift_distance_m": 0.08,
                    "lateral_distance_m": 0.0,
                },
                "candidate_target_spec": {"candidate_id": "raw_candidate_01"},
                "failures": [],
                "witness": {
                    "movers": {
                        "left": {"unexpected_hit_paths": []},
                        "right": {"unexpected_hit_paths": []},
                        "hand": {"unexpected_hit_paths": []},
                    },
                    "target_hits_by_role": {
                        "left": [],
                        "right": [],
                        "hand": [],
                    },
                },
            }
        ]
    }
    role_paths = {
        "source_internal_wrapper_paths": ["/World/beaker2/wrapper"],
        "support_collider_paths": ["/World/table/surface/mesh"],
    }

    witness = g0_geometry._raw_geometry_no_inflation_witness(sweep, role_paths)

    assert witness["authority"] == "real_pbd_g0_raw_geometry_no_inflation_witness_v1"
    assert witness["status"] == "COMPLETE"
    assert witness["inflation_mode"] == "NONE"
    assert witness["effective_offset_clearance"] == "NOT_CLAIMED"
    assert witness["candidate_id"] == "raw_candidate_01"
    assert witness["unexpected_hit_paths"] == []
    assert witness["prohibited_hit_paths"] == []
    assert "minimum_signed_clearance_m" not in witness
