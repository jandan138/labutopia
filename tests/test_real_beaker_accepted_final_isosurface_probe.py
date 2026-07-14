from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest
from pxr import Sdf, Usd

from tools.labutopia_fluid import (
    run_real_beaker_accepted_final_isosurface_probe as probe,
)


def test_load_accepted_final_record_is_pinned() -> None:
    record = probe.load_accepted_final_record()

    assert record["trace_sha256"] == probe.EXPECTED_TRACE_SHA256
    assert record["step_index"] == 600
    assert record["particle_count"] == 4096
    assert len(record["positions"]) == 4096
    assert record["positions_sha256"] == (
        "8a1942e82b21d470fe873570bbfcc9056de813a7427e6e1293c5ceac12ab0033"
    )
    assert record["strict_visible_beaker_counts"][
        "inside_visible_interior_count"
    ] == 4096
    assert record["strict_visible_beaker_counts"][
        "strict_violating_point_count"
    ] == 0


def test_load_accepted_final_record_rejects_tampering(tmp_path: Path) -> None:
    original = probe.ACCEPTED_TRACE.read_bytes()
    tampered = tmp_path / "trace.jsonl"
    tampered.write_bytes(original.replace(b'"step_index": 600', b'"step_index": 599'))

    with pytest.raises(ValueError, match="accepted_trace_sha256_mismatch"):
        probe.load_accepted_final_record(tampered)

    digest = hashlib.sha256(tampered.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="accepted_final_step_missing"):
        probe.load_accepted_final_record(tampered, expected_sha256=digest)


def test_fixed_isosurface_contract_matches_accepted_offsets() -> None:
    contract = probe.build_fixed_isosurface_contract()

    assert contract["particle_width"] == 0.00045
    assert contract["particle_contact_offset"] == 0.000529254
    assert contract["particle_system_contact_offset"] == 0.000793881
    assert contract["solid_rest_offset"] == 0.0004455
    assert contract["fluid_rest_offset"] == 0.000264627
    assert contract["grid_spacing"] == pytest.approx(0.0002381643)
    assert contract["surface_distance"] == pytest.approx(0.00025139565)
    assert contract["grid_smoothing_radius"] == pytest.approx(0.000264627)
    assert contract["anisotropy"] == {"scale": 5.0, "min": 1.0, "max": 2.0}
    assert contract["smoothing_strength"] == 0.5
    assert contract["initialization_integration_steps"] == 1
    assert contract["initialization_dt"] == pytest.approx(1.0 / 600.0)


def test_disposable_wrapper_keeps_source_as_read_only_sublayer(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.usda"
    source_layer = Sdf.Layer.CreateNew(str(source))
    source_layer.defaultPrim = "World"
    source_layer.Save()
    source_before = source.read_bytes()
    wrapper = tmp_path / "wrapper.usda"

    contract = probe.create_disposable_wrapper_layer(source, wrapper)
    stage = Usd.Stage.Open(str(wrapper), Usd.Stage.LoadNone)

    assert contract["source_path"] == str(source.resolve())
    assert contract["wrapper_path"] == str(wrapper.resolve())
    assert contract["source_is_sublayer"] is True
    assert stage.GetRootLayer().realPath == str(wrapper.resolve())
    assert stage.GetRootLayer().subLayerPaths == [str(source.resolve())]
    assert source.read_bytes() == source_before


def test_validate_authored_positions_requires_exact_ordered_readback() -> None:
    expected = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]

    result = probe.validate_authored_positions(expected, expected)

    assert result["exact_ordered_match"] is True
    assert result["particle_count"] == 2
    assert result["positions_sha256"] == probe.positions_sha256(expected)
    with pytest.raises(ValueError, match="authored_positions_mismatch"):
        probe.validate_authored_positions(list(reversed(expected)), expected)


def test_validate_authored_zero_velocities_requires_exact_zero_state() -> None:
    velocities = [[0.0, 0.0, 0.0], [-0.0, 0.0, 0.0]]

    result = probe.validate_authored_zero_velocities(velocities, expected_count=2)

    assert result["particle_count"] == 2
    assert result["all_finite"] is True
    assert result["all_zero"] is True
    with pytest.raises(ValueError, match="authored_velocity_nonzero"):
        probe.validate_authored_zero_velocities(
            [[0.0, 0.0, 0.0], [0.0, 0.0, 0.001]],
            expected_count=2,
        )


def _isolated_legacy_graph_summary(
    *,
    synchronization_required: bool = False,
    synchronization_updates: int = 5,
) -> dict[str, object]:
    return {
        "ownership_isolation": {
            "sampler_targets_after": [],
            "particle_set_targets_after": [],
            "synchronization_required": synchronization_required,
            "synchronization_updates": synchronization_updates,
            "synchronization_verified": True,
            "verified": True,
        },
        probe.LEGACY_PARTICLE_SYSTEM_PATH: {
            "disabled_attrs": {"particleSystemEnabled": False},
        },
    }


def test_validate_legacy_graph_setup_accepts_already_isolated_source() -> None:
    sampler = {
        "api_present_after": False,
        "verified": True,
    }
    isolation = _isolated_legacy_graph_summary()
    checkpoints = {
        "before_legacy_graph_setup": {
            "physics_step_events": 0,
            "timeline_stopped": True,
        },
        "after_legacy_graph_setup": {
            "physics_step_events": 0,
            "timeline_stopped": True,
        },
    }

    result = probe.validate_legacy_graph_setup(sampler, isolation, checkpoints)

    assert result["verified"] is True
    assert result["synchronization_required"] is False
    assert result["synchronization_updates"] == 5
    with pytest.raises(RuntimeError, match="legacy_graph_setup_invalid"):
        probe.validate_legacy_graph_setup(
            sampler,
            _isolated_legacy_graph_summary(synchronization_updates=4),
            checkpoints,
        )
    with pytest.raises(RuntimeError, match="legacy_graph_setup_invalid"):
        probe.validate_legacy_graph_setup(
            sampler,
            isolation,
            {
                **checkpoints,
                "after_legacy_graph_setup": {
                    "physics_step_events": 1,
                    "timeline_stopped": True,
                },
            },
        )
    wrong_system = dict(isolation)
    wrong_system.pop(probe.LEGACY_PARTICLE_SYSTEM_PATH)
    wrong_system[probe.RUNTIME_PARTICLE_SYSTEM_PATH] = {
        "disabled_attrs": {"particleSystemEnabled": False},
    }
    with pytest.raises(RuntimeError, match="legacy_graph_setup_invalid"):
        probe.validate_legacy_graph_setup(sampler, wrong_system, checkpoints)


def test_validate_second_deactivation_requires_no_graph_change() -> None:
    result = probe.validate_second_deactivation(
        _isolated_legacy_graph_summary(synchronization_updates=0)
    )

    assert result["verified"] is True
    assert result["synchronization_required"] is False
    with pytest.raises(RuntimeError, match="second_deactivation_invalid"):
        probe.validate_second_deactivation(
            _isolated_legacy_graph_summary(
                synchronization_required=True,
                synchronization_updates=0,
            )
        )


def test_validate_strict_physics_scene_requires_600_hz_gpu_tgs() -> None:
    summary = {
        "physics_scene_path": "/World/PhysicsScene",
        "gpu_dynamics_enabled": True,
        "broadphase_type": "GPU",
        "solver_type": "TGS",
        "time_steps_per_second": 600,
        "effective_physics_dt": 1.0 / 600.0,
        "time_steps_per_second_authored": True,
        "strict_timestep_verified": True,
    }

    result = probe.validate_strict_physics_scene(summary)

    assert result["verified"] is True
    with pytest.raises(RuntimeError, match="strict_physics_scene_invalid"):
        probe.validate_strict_physics_scene(
            {**summary, "time_steps_per_second": 60}
        )


def test_validate_operation_ledger_requires_exact_order_and_step_counts() -> None:
    records = [
        {
            "operation": operation,
            "physics_step_events": 1 if operation == "single_initialization_step" else 0,
            "timeline_stopped": True,
        }
        for operation in probe.EXPECTED_OPERATION_ORDER
    ]

    result = probe.validate_operation_ledger(records)

    assert result["verified"] is True
    assert result["operations"] == list(probe.EXPECTED_OPERATION_ORDER)
    with pytest.raises(RuntimeError, match="operation_ledger_invalid"):
        probe.validate_operation_ledger(list(reversed(records)))


def test_validate_single_step_checkpoints_requires_exact_lifecycle() -> None:
    checkpoints = {
        name: {
            "physics_step_events": 0 if index < 2 else 1,
            "timeline_stopped": True,
        }
        for index, name in enumerate(probe.SINGLE_STEP_CHECKPOINT_NAMES)
    }

    result = probe.validate_single_step_checkpoints(checkpoints)

    assert result["physics_steps_executed"] == 1
    assert result["single_initialization_step_verified"] is True
    checkpoints["after_final_capture"]["physics_step_events"] = 2
    with pytest.raises(RuntimeError, match="single_step_checkpoint_invalid"):
        probe.validate_single_step_checkpoints(checkpoints)


def test_validate_single_step_lifecycle_summary_requires_one_ordered_pair() -> None:
    summary = {
        "requested_logical_steps": 1,
        "executed_logical_steps": 1,
        "requested_integration_steps": 1,
        "executed_integration_steps": 1,
        "simulate_fetch_pair_count": 1,
        "simulated_seconds": 1.0 / 600.0,
        "exact_logical_step_count_verified": True,
        "exact_integration_step_count_verified": True,
        "exact_step_count_verified": True,
        "ordered_lifecycle_verified": True,
        "attach_verified": True,
        "detach_verified": True,
    }

    result = probe.validate_single_step_lifecycle_summary(summary)

    assert result["verified"] is True
    with pytest.raises(RuntimeError, match="single_step_lifecycle_invalid"):
        probe.validate_single_step_lifecycle_summary(
            {**summary, "simulate_fetch_pair_count": 0}
        )


def test_validate_post_step_presentation_readback_fails_closed() -> None:
    positions = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    counts = {
        "particle_count": 2,
        "finite_count": 2,
        "nonfinite_count": 0,
        "inside_visible_interior_count": 2,
        "strict_violating_point_count": 0,
    }

    result = probe.validate_post_step_presentation_readback(
        positions,
        counts,
        violating_indices=[],
        expected_count=2,
    )

    assert result["presentation_state_only"] is True
    assert result["particle_count"] == 2
    assert result["strict_visible_beaker_counts"] == counts
    assert result["violating_indices"] == []
    with pytest.raises(ValueError, match="post_step_presentation_containment_failed"):
        probe.validate_post_step_presentation_readback(
            positions,
            {**counts, "inside_visible_interior_count": 1, "strict_violating_point_count": 1},
            violating_indices=[1],
            expected_count=2,
        )
    with pytest.raises(ValueError, match="position_nonfinite"):
        probe.validate_post_step_presentation_readback(
            [[math.nan, 2.0, 3.0], [4.0, 5.0, 6.0]],
            counts,
            violating_indices=[],
            expected_count=2,
        )


def test_validate_runtime_isosurface_bridge_and_clearwater_binding() -> None:
    summary = {
        "path": f"{probe.RUNTIME_PARTICLE_SYSTEM_PATH}/Isosurface",
        "prim_exists": True,
        "type_name": "Mesh",
        "usd_point_count": 1,
        "usd_face_count": 1,
        "usd_points_finite": False,
        "bound_material_path": probe.TREATMENT_MATERIAL_PATH,
        "mdl_source_asset_sha256": probe.EXPECTED_MDL_SOURCE_SHA256,
        "mdl_sub_identifier": probe.MDL_SUB_IDENTIFIER,
        "preview_fallback_used": False,
    }

    result = probe.validate_runtime_isosurface_bridge(
        summary,
        particle_system_path=probe.RUNTIME_PARTICLE_SYSTEM_PATH,
    )

    assert result["verified"] is True
    assert result["usd_geometry_classification"] == "USD_BRIDGE_PLACEHOLDER"
    with pytest.raises(ValueError, match="runtime_isosurface_bridge_invalid"):
        probe.validate_runtime_isosurface_bridge(
            {**summary, "bound_material_path": "/World/Looks/Wrong"},
            particle_system_path=probe.RUNTIME_PARTICLE_SYSTEM_PATH,
        )
    with pytest.raises(ValueError, match="runtime_isosurface_bridge_invalid"):
        probe.validate_runtime_isosurface_bridge(
            {
                **summary,
                "usd_point_count": 10,
                "usd_face_count": 8,
                "usd_points_finite": False,
            },
            particle_system_path=probe.RUNTIME_PARTICLE_SYSTEM_PATH,
        )


def test_validate_three_camera_capture_contract() -> None:
    assert probe.CAMERA_PATHS == (
        "context",
        "source_beaker_closeup",
        "native_table_context",
    )
    frames = {
        role: {
            "path": f"/{role}.png",
            "shape": [540, 960, 4],
            "dtype": "uint8",
            "mean": 100.0,
            "std": 12.0,
            "sha256": character * 64,
        }
        for role, character in zip(probe.CAMERA_PATHS, "abc")
    }

    result = probe.validate_camera_capture_contract({"frames": frames})

    assert result["verified"] is True
    assert result["camera_roles"] == list(probe.CAMERA_PATHS)
    frames["native_table_context"]["shape"] = [480, 640, 4]
    with pytest.raises(ValueError, match="camera_capture_contract_invalid"):
        probe.validate_camera_capture_contract({"frames": frames})
    frames["native_table_context"]["shape"] = [540, 960, 4]
    frames["native_table_context"]["dtype"] = "float32"
    with pytest.raises(ValueError, match="camera_capture_contract_invalid"):
        probe.validate_camera_capture_contract({"frames": frames})


def test_build_technical_status_fails_closed() -> None:
    gates = {
        "authority": True,
        "legacy_graph_setup": True,
        "strict_physics_scene": True,
        "operation_order": True,
        "authored_positions": True,
        "authored_zero_velocities": True,
        "single_initialization_step": True,
        "post_step_presentation_containment": True,
        "isosurface_bridge": True,
        "clearwater_material": True,
        "capture": True,
        "log": True,
        "source_integrity": True,
    }

    assert probe.build_technical_status(gates) == {
        "status": "CAPTURED_GRAPH_OWNED_ISOSURFACE_PENDING_VISUAL_REVIEW",
        "failed_gates": [],
        "technically_valid": True,
    }
    failed = probe.build_technical_status({**gates, "log": False})
    assert failed["status"] == "INVALID_GRAPH_OWNED_ISOSURFACE_PROBE"
    assert failed["failed_gates"] == ["log"]
    assert failed["technically_valid"] is False


def test_build_failure_manifest_preserves_runtime_error() -> None:
    failure = probe.build_failure_manifest(RuntimeError("particle_authoring_failed"))

    assert failure["probe_id"] == probe.PROBE_ID
    assert failure["status"] == "INVALID_GRAPH_OWNED_ISOSURFACE_PROBE"
    assert failure["technically_valid"] is False
    assert failure["fatal_error"]["type"] == "RuntimeError"
    assert failure["fatal_error"]["message"] == "particle_authoring_failed"


def test_write_json_does_not_leave_truncated_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "manifest.json"

    def fail_dump(*_args: object, **_kwargs: object) -> None:
        raise TypeError("serialization_failed")

    monkeypatch.setattr(probe.json, "dump", fail_dump)
    with pytest.raises(TypeError, match="serialization_failed"):
        probe._write_json(target, {"status": "test"})

    assert target.exists() is False
    assert list(tmp_path.iterdir()) == []


def test_canonical_value_encodes_nonfinite_usd_placeholders() -> None:
    values = probe._canonical_value([math.nan, math.inf, -math.inf])

    assert values == [
        {"nonfinite_float": "nan"},
        {"nonfinite_float": "+inf"},
        {"nonfinite_float": "-inf"},
    ]
    json.dumps(values, allow_nan=False)


def test_discarded_warmup_allows_only_flat_frame_quality_failure() -> None:
    error = RuntimeError(
        "static_replicator_capture_near_black_or_flat:context:"
        "mean=254.98:std=0.15"
    )

    attempt = {"kind": "discarded_warmup", "outcome": "started"}
    summary = probe.finalize_discarded_warmup_failure_attempt(attempt, error)

    assert summary["discarded"] is True
    assert summary["frame_quality_valid"] is False
    assert summary["continued_to_strict_final_capture"] is True
    assert summary["error"] == str(error)
    assert attempt["outcome"] == "allowed_context_flat_failure"
    with pytest.raises(RuntimeError, match="unexpected_discarded_warmup_failure"):
        rejected_attempt = {"kind": "discarded_warmup", "outcome": "started"}
        probe.finalize_discarded_warmup_failure_attempt(
            rejected_attempt,
            RuntimeError("static_render_changed_scene")
        )
    assert rejected_attempt["outcome"] == "failed"
    with pytest.raises(RuntimeError, match="unexpected_discarded_warmup_failure"):
        probe.build_discarded_warmup_failure_summary(
            RuntimeError(
                "static_replicator_capture_near_black_or_flat:"
                "source_beaker_closeup:mean=255.0:std=0.0"
            )
        )


def test_terminal_capture_failure_requires_completed_evidence_chain() -> None:
    context = {
        "capture_attempts": [
            {
                "kind": "strict_final",
                "predeclared_discard": False,
                "outcome": "failed",
                "error": (
                    "static_replicator_capture_near_black_or_flat:context:"
                    "mean=254.98:std=0.15"
                ),
            }
        ],
        "operation_ledger": {"verified": True},
        "single_step_validation": {
            "single_initialization_step_verified": True,
            "physics_steps_executed": 1,
            "checkpoints": {
                "after_final_capture": {
                    "physics_step_events": 1,
                    "timeline_stopped": True,
                },
                "after_detach": {
                    "physics_step_events": 1,
                    "timeline_stopped": True,
                },
            },
        },
        "single_step_lifecycle": {"verified": True},
        "scene_hash_unchanged": True,
        "replicator_cleanup": {
            "cleanup_complete": True,
            "cleanup_failures": {},
        },
        "log": {"verified": True},
        "source_integrity": {"verified": True},
    }

    result = probe.validate_terminal_capture_failure_context(context)

    assert result["verified"] is True
    with pytest.raises(RuntimeError, match="terminal_capture_evidence_invalid"):
        probe.validate_terminal_capture_failure_context(
            {**context, "scene_hash_unchanged": False}
        )


def test_graph_owned_probe_identity_and_claim_boundary_are_explicit() -> None:
    assert probe.PROBE_ID == (
        "real_beaker_isosurface_graph_owned_final_probe_20260713"
    )
    assert probe.OUTPUT_ROOT.name == (
        "real_beaker_isosurface_graph_owned_final_probe_20260713"
    )
    assert probe.CLAIM_BOUNDARY == (
        "accepted_frame_600_positions_are_parent_authority;"
        "single_zero_velocity_init_step_state_is_presentation_only;"
        "not_frame_601;no_new_physics_authority"
    )


def test_single_step_log_gate_rejects_relevant_fatal_and_nonfinite() -> None:
    accepted = probe.validate_single_step_log_segment(
        "[Info] PhysX isosurface initialized\n[Info] ClearWater compiled\n"
    )

    assert accepted["verified"] is True
    with pytest.raises(RuntimeError, match="single_step_runtime_log_invalid"):
        probe.validate_single_step_log_segment(
            "[Error] omni.physx isosurface CUDA non-finite output\n"
        )
